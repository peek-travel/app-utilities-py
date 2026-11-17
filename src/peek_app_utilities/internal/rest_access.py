"""Shared wiring for the REST-platform access services (CNG, ACME).

Both validate the same four config fields, build the same :class:`TokenManager`
and :class:`RestClient`, default to the app-registry base URL, and own (or
borrow) one :class:`httpx.AsyncClient`. The only differences — the slug, the
endpoint lookup, the log label, and the error types — are parameters here, so
each access service is a thin, declarative shell.
"""

from __future__ import annotations

from typing import Final

import httpx

from peek_app_utilities.access_service_config import (
    BaseAccessServiceConfig,
    create_http_client,
    create_token_manager,
    require_non_empty,
    resolve_base_api_url,
    resolve_retry_delays,
)
from peek_app_utilities.internal.api_endpoints import ApiEndpoints
from peek_app_utilities.internal.rest_client import (
    ApiErrorFactory,
    ForbiddenHandler,
    RestClient,
    RestClientOptions,
)
from peek_app_utilities.logger import noop_logger

DEFAULT_REGISTRY_BASE_URL: Final = "https://app-registry.peeklabs.com/installations-api"
"""Default base URL — the app-registry installations API."""


class OwnedHttpClient:
    """Tracks whether the access service owns its HTTP client, and closes it only
    then. Gives every access service ``aclose()`` plus ``async with`` support."""

    def __init__(self, provided: httpx.AsyncClient | None) -> None:
        self.client: httpx.AsyncClient = provided if provided is not None else create_http_client()
        self._owned = provided is None

    async def aclose(self) -> None:
        if self._owned:
            await self.client.aclose()


def validate_rest_config(config: BaseAccessServiceConfig, service_name: str) -> None:
    """The four required fields every REST access service checks (``app_id`` only
    in the deprecated ``base_url`` mode)."""
    require_non_empty(config.install_id, "install_id", service_name)
    require_non_empty(config.jwt_secret, "jwt_secret", service_name)
    require_non_empty(config.issuer, "issuer", service_name)
    if not config.api_url:
        require_non_empty(config.app_id, "app_id", service_name)


def resolve_rest_base_api_url(config: BaseAccessServiceConfig, service_name: str, slug: str) -> str:
    """``api_url`` (slug stripped) when given, else ``base_url/app_id`` with the
    app-registry default base."""
    if config.api_url:
        return resolve_base_api_url(config.api_url, slug, service_name)
    return f"{config.base_url or DEFAULT_REGISTRY_BASE_URL}/{config.app_id}"


def build_rest_client(
    config: BaseAccessServiceConfig,
    *,
    service_name: str,
    slug: str,
    endpoints: ApiEndpoints,
    platform_label: str,
    api_error: ApiErrorFactory,
    http: OwnedHttpClient,
    on_forbidden: ForbiddenHandler | None = None,
) -> RestClient:
    """Validates ``config`` and builds the authenticated :class:`RestClient`."""
    validate_rest_config(config, service_name)
    tokens = create_token_manager(config)
    return RestClient(
        RestClientOptions(
            base_api_url=resolve_rest_base_api_url(config, service_name, slug),
            endpoints=endpoints,
            get_token=tokens.get_token,
            retry_delays_ms=resolve_retry_delays(config),
            logger=config.logger or noop_logger,
            http_client=http.client,
            platform_label=platform_label,
            api_error=api_error,
            on_forbidden=on_forbidden,
        )
    )
