"""Thin REST-over-HTTP transport shared by the CNG and ACME platform APIs, built
on :mod:`httpx`. Handles endpoint construction, auth headers, and REST-specific
response handling. The shared retry/backoff loop and 418/429 mapping live in
``http_transport.py`` (used by the Peek GraphQL transport too).

The REST sibling of ``peek/graphql_client.py``, minus the GraphQL specifics:
requests are plain GETs (no ``{query, variables}`` envelope, no GraphQL
``errors`` array), and there is no ``pk-api-key`` header — the REST platforms
authenticate on the app JWT (``X-Peek-Auth``) alone.

The two platforms differ only in their log label, the error raised on a
non-2xx response, and (CNG only) a special-cased HTTP 403 — so those are
supplied per instance via :class:`RestClientOptions` rather than cloned.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import httpx

from peek_app_utilities.errors import FORBIDDEN_STATUS
from peek_app_utilities.internal.api_endpoints import ApiEndpoints, join_url
from peek_app_utilities.internal.http_transport import (
    HttpRetryOptions,
    SleepFn,
    parse_body,
    request_with_retry,
)
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_NAME, SDK_HEADER_VALUE
from peek_app_utilities.logger import Logger

_AUTH_HEADER: Final = "X-Peek-Auth"
_CONTENT_TYPE_HEADER: Final = "Content-Type"
_JSON_CONTENT_TYPE: Final = "application/json"

ApiErrorFactory = Callable[[int, Any], Exception]
"""Builds the platform's generic non-2xx error from ``(status_code, body)``."""

ForbiddenHandler = Callable[[Any], tuple[Exception, dict[str, Any]]]
"""Builds the platform's HTTP 403 error from the parsed body, returning the
error plus the context mapping to log at ``warn`` level."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RestClientOptions:
    base_api_url: str
    """The install's **base API URL** (no trailing slash, no routing slug). Each
    request builds ``base_api_url/<slug>/<path>``."""
    endpoints: ApiEndpoints
    """Maps an endpoint key to the relative slug appended to :attr:`base_api_url`."""
    get_token: Callable[[], str]
    """Supplies a valid bearer token for each request."""
    retry_delays_ms: Sequence[int]
    """Backoff delays (ms) applied on successive HTTP 429 responses."""
    logger: Logger
    """Diagnostics sink."""
    http_client: httpx.AsyncClient
    """HTTP client to send requests through."""
    platform_label: str
    """Short platform name used in log lines (``"CNG"`` / ``"ACME"``)."""
    api_error: ApiErrorFactory
    """Error raised for a non-2xx response that is not 418/429 (or a handled 403)."""
    on_forbidden: ForbiddenHandler | None = None
    """When set, HTTP 403 is logged at ``warn`` and raised via this handler."""
    sleep: SleepFn | None = None
    """Override the retry sleep (tests)."""


class RestClient:
    """GETs REST paths on a platform API and returns the parsed JSON body."""

    def __init__(self, options: RestClientOptions) -> None:
        self._options = options
        retry_kwargs: dict[str, Any] = {}
        if options.sleep is not None:
            retry_kwargs["sleep"] = options.sleep
        self._retry = HttpRetryOptions(
            retry_delays_ms=options.retry_delays_ms,
            logger=options.logger,
            http_client=options.http_client,
            **retry_kwargs,
        )

    async def get(self, endpoint: str, path: str) -> Any:
        """Issues a GET against the named REST path and returns the parsed body.
        Retries on HTTP 429 per the configured backoff.

        :raises AdminAccountRequiredError: on HTTP 418
        :raises RateLimitError: on HTTP 429 after retries are exhausted
        :raises Exception: the platform's 403 error when ``on_forbidden`` is set,
            else the platform's API error on any non-2xx response
        """
        opts = self._options
        logger = opts.logger
        url = self._endpoint(endpoint, path)

        logger.info(f"Making {opts.platform_label} request", {"url": url, "path": path})

        async def on_response(response: httpx.Response) -> Any:
            body = parse_body(response)

            if opts.on_forbidden is not None and response.status_code == FORBIDDEN_STATUS:
                error, context = opts.on_forbidden(body)
                # Expected for a misconfigured install — warn, don't error.
                logger.warn(f"Missing permission for {path} (HTTP 403)", {"url": url, **context})
                raise error

            if not response.is_success:
                logger.error(
                    f"{opts.platform_label} request failed with HTTP {response.status_code}",
                    {"url": url},
                )
                raise opts.api_error(response.status_code, body)

            return body

        return await request_with_retry(
            self._retry, "GET", url, path, on_response, headers=self._build_headers()
        )

    def _endpoint(self, endpoint: str, path: str) -> str:
        opts = self._options
        return join_url(opts.base_api_url, opts.endpoints.path_for(endpoint), path)

    def _build_headers(self) -> dict[str, str]:
        return {
            _AUTH_HEADER: f"Bearer {self._options.get_token()}",
            _CONTENT_TYPE_HEADER: _JSON_CONTENT_TYPE,
            SDK_HEADER_NAME: SDK_HEADER_VALUE,
        }
