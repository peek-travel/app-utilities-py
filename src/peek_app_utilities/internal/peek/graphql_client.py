"""Thin GraphQL-over-HTTP transport built on :mod:`httpx`. Handles endpoint
construction, auth headers, query whitespace collapsing, and GraphQL-specific
response handling. The shared retry/backoff loop and 418/429 mapping live in
``internal/http_transport.py`` (used by the CNG/ACME REST transports too).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import httpx

from peek_app_utilities.errors import PeekGraphQLError, PeekHttpError
from peek_app_utilities.internal.api_endpoints import ApiEndpoints, join_url
from peek_app_utilities.internal.http_transport import (
    HttpRetryOptions,
    SleepFn,
    parse_body,
    request_with_retry,
)
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_NAME, SDK_HEADER_VALUE
from peek_app_utilities.logger import Logger

_WHITESPACE_RE: Final = re.compile(r"\s+")
_AUTH_HEADER: Final = "X-Peek-Auth"
_GATEWAY_KEY_HEADER: Final = "pk-api-key"
_CONTENT_TYPE_HEADER: Final = "Content-Type"
_JSON_CONTENT_TYPE: Final = "application/json"

GraphQLBody = dict[str, Any]
"""The raw body of a GraphQL HTTP response: ``{"data": ..., "errors": [...]}``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphQLClientOptions:
    base_api_url: str
    """The install's **base API URL** (no trailing slash, no routing slug). Every
    GraphQL call POSTs to ``base_api_url/<slug>``, where the slug comes from
    :attr:`endpoints` for the request's endpoint name."""
    endpoints: ApiEndpoints
    """Maps an endpoint name to the relative slug appended to :attr:`base_api_url`."""
    get_token: Callable[[], str]
    """Supplies a valid bearer token for each request."""
    retry_delays_ms: Sequence[int]
    """Backoff delays (ms) applied on successive HTTP 429 responses."""
    logger: Logger
    """Diagnostics sink."""
    http_client: httpx.AsyncClient
    """HTTP client to send requests through."""
    gateway_key: str | None = None
    """API gateway key sent as ``pk-api-key``. Omitted when absent (v2 mode)."""
    sleep: SleepFn | None = None
    """Override the retry sleep (tests)."""


class GraphQLClient:
    """Executes GraphQL operations against the Peek backoffice API."""

    def __init__(self, options: GraphQLClientOptions) -> None:
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

    async def request(
        self, endpoint_name: str, query: str, variables: Mapping[str, Any]
    ) -> GraphQLBody:
        """Executes a GraphQL query against the named endpoint and returns the raw
        response body (``{"data": ...}``). Retries on HTTP 429 per the configured
        backoff.

        :raises AdminAccountRequiredError: on HTTP 418
        :raises RateLimitError: on HTTP 429 after retries are exhausted
        :raises PeekGraphQLError: when the body carries an ``errors`` array
        :raises PeekHttpError: on any other non-2xx response
        """
        logger = self._options.logger
        url = self._endpoint(endpoint_name)
        collapsed_query = _WHITESPACE_RE.sub(" ", query).strip()

        logger.info("Making GraphQL request", {"url": url, "endpointName": endpoint_name})

        async def on_response(response: httpx.Response) -> GraphQLBody:
            # Parse the body defensively *before* branching on status: a non-JSON
            # error page must surface as a typed HTTP error, not a decode error
            # that hides the real status.
            raw = parse_body(response)
            body: GraphQLBody = raw if isinstance(raw, dict) else {}

            errors = body.get("errors")
            if errors:
                logger.error(
                    f"GraphQL errors for {endpoint_name}",
                    {"url": url, "graphqlErrors": json.dumps(errors)},
                )
                raise PeekGraphQLError(list(errors))

            if not response.is_success:
                logger.error(
                    f"GraphQL request failed with HTTP {response.status_code}", {"url": url}
                )
                raise PeekHttpError(response.status_code, url, raw)

            return body

        return await request_with_retry(
            self._retry,
            "POST",
            url,
            endpoint_name,
            on_response,
            headers=self._build_headers(),
            json_body={"query": collapsed_query, "variables": dict(variables)},
        )

    def _endpoint(self, endpoint_name: str) -> str:
        opts = self._options
        return join_url(opts.base_api_url, opts.endpoints.path_for(endpoint_name))

    def _build_headers(self) -> dict[str, str]:
        headers = {
            _AUTH_HEADER: f"Bearer {self._options.get_token()}",
            _CONTENT_TYPE_HEADER: _JSON_CONTENT_TYPE,
            SDK_HEADER_NAME: SDK_HEADER_VALUE,
        }
        if self._options.gateway_key:
            headers[_GATEWAY_KEY_HEADER] = self._options.gateway_key
        return headers
