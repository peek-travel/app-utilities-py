"""Config shared by every access service in this package (Peek, CNG, ACME).

Each platform's access service extends :class:`BaseAccessServiceConfig` with
its own extras (e.g. Peek adds ``gateway_key``/``mode``), so the only real
difference between accessors is the transport they build and the services they
expose. The shared defaults and the token-manager builder live here too, so
that plumbing is written once.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

import httpx

from peek_app_utilities.access_options import AccessOptions
from peek_app_utilities.internal.token_manager import TokenManager, TokenManagerOptions
from peek_app_utilities.logger import Logger

DEFAULT_TOKEN_TTL_SECONDS: Final = 3600
"""Default JWT lifetime (1 hour)."""
DEFAULT_TOKEN_REFRESH_LEEWAY_SECONDS: Final = 60
"""Default leeway before expiry at which a cached token is re-minted."""
DEFAULT_RETRY_DELAYS_MS: Final[tuple[int, ...]] = (1000, 2000, 4000)
"""Default HTTP 429 retry backoff."""
DEFAULT_HTTP_TIMEOUT_SECONDS: Final = 30.0
"""Default per-request timeout for the package-owned HTTP client."""

GatewayMode = Literal["v2"]


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseAccessServiceConfig:
    """Fields common to every access service's config."""

    install_id: str
    """Install ID. Becomes the JWT subject."""
    jwt_secret: str
    """HMAC secret used to sign the JWT."""
    issuer: str
    """JWT issuer — the app name / app ID."""
    api_url: str | None = None
    """The install's **base API URL** — persist the install webhook's ``api_url``
    and pass it here. It is the app endpoint with no per-platform routing slug;
    each service class appends its own slug when it makes a call. If the URL
    still carries this platform's slug it is stripped back off; a URL carrying a
    *different* platform's slug makes the constructor raise. No app-id segment is
    inserted, so ``app_id`` is not required. Prefer this over
    ``base_url``/``app_id``, which are deprecated."""
    app_id: str | None = None
    """App ID, inserted into the gateway endpoint path.

    .. deprecated:: Required only in the legacy ``base_url`` mode. Prefer
       ``api_url`` (the install's app endpoint), which needs no app-id segment.
    """
    base_url: str | None = None
    """Override the gateway base URL. Default: per-service.

    .. deprecated:: Prefer ``api_url``. The hardcoded per-service default will be
       removed and a URL will become required.
    """
    token_ttl_seconds: int | None = None
    """JWT lifetime in seconds. Default: 3600."""
    token_refresh_leeway_seconds: int | None = None
    """Re-mint the cached token this many seconds before expiry. Default: 60."""
    retry_delays_ms: Sequence[int] | None = None
    """Backoff delays (ms) for HTTP 429 retries. Default: ``(1000, 2000, 4000)``."""
    logger: Logger | None = None
    """Optional logger. Default: no-op (silent)."""
    http_client: httpx.AsyncClient | None = None
    """Custom :class:`httpx.AsyncClient`. Default: one owned by the access service
    (closed by ``aclose()`` / the async context manager). A caller-supplied client
    is never closed by the package."""
    access_options: AccessOptions | None = None
    """Cross-cutting access options (PII exposure, …). When omitted, defaults are
    used (``full_customer_access`` ``False``)."""


def require_non_empty(value: str | None, name: str, service_name: str) -> None:
    """Raises when a required config field is empty, prefixing the message with
    the concrete service name (e.g. ``PeekAccessService: "install_id" is required``)."""
    if not value:
        raise ValueError(f'{service_name}: "{name}" is required')


# Matches a backoffice-API extendable slug and captures the platform prefix —
# e.g. `peek` from `peek_backoffice_api-v1` or `peek-backoffice-api-v1`. Dashes
# and underscores are interchangeable as separators. Anchored to the whole
# segment so an ordinary install-path segment never matches.
_EXTENDABLE_SLUG_RE: Final = re.compile(r"^([a-z0-9]+)[-_]backoffice[-_]api[-_]v1$", re.IGNORECASE)


def resolve_base_api_url(api_url: str, platform_slug: str, service_name: str) -> str:
    """Recovers the **base API URL** from the install's app endpoint (``api_url``).

    - **No slug present** → the URL is already the base; return it (trailing slash
      trimmed).
    - **This platform's slug present** → strip it off and return the base.
    - **A different platform's slug present** → raise, since the URL targets the
      wrong platform and silently stripping it would mask a wiring mistake.
    """
    trimmed = api_url.rstrip("/")
    last_segment = trimmed.rsplit("/", 1)[-1]
    found = _EXTENDABLE_SLUG_RE.match(last_segment)
    if found is None:
        return trimmed

    found_platform = found.group(1).lower()
    expected_match = _EXTENDABLE_SLUG_RE.match(platform_slug)
    assert expected_match is not None  # platform slugs are package constants
    expected_platform = expected_match.group(1).lower()
    if found_platform != expected_platform:
        raise ValueError(
            f'{service_name}: "api_url" carries a "{found_platform}" backoffice '
            f'slug but this service targets "{expected_platform}" — pass the '
            f"install's {expected_platform} app endpoint"
        )
    return trimmed[: trimmed.rfind("/")]


def create_token_manager(config: BaseAccessServiceConfig) -> TokenManager:
    """Builds the shared :class:`TokenManager` from the common config fields,
    applying the shared TTL/leeway defaults. Used by every access service."""
    return TokenManager(
        TokenManagerOptions(
            secret=config.jwt_secret,
            issuer=config.issuer,
            install_id=config.install_id,
            ttl_seconds=(
                config.token_ttl_seconds
                if config.token_ttl_seconds is not None
                else DEFAULT_TOKEN_TTL_SECONDS
            ),
            leeway_seconds=(
                config.token_refresh_leeway_seconds
                if config.token_refresh_leeway_seconds is not None
                else DEFAULT_TOKEN_REFRESH_LEEWAY_SECONDS
            ),
        )
    )


def resolve_retry_delays(config: BaseAccessServiceConfig) -> tuple[int, ...]:
    """The configured 429 backoff, or the shared default."""
    return (
        tuple(config.retry_delays_ms)
        if config.retry_delays_ms is not None
        else DEFAULT_RETRY_DELAYS_MS
    )


def create_http_client() -> httpx.AsyncClient:
    """The package-owned HTTP client used when the config supplies none."""
    return httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS)
