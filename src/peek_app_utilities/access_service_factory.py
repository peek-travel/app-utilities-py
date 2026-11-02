"""Factory that turns a persisted install (or a parsed install webhook) into the
right access service for its platform, wired to the install's own app endpoint.

The install webhook is the only source of an install's ``platform`` and
``api_url``, and those two facts are exactly what's needed to target it:
``platform`` picks the service class, and ``api_url`` is that service's
endpoint. A consumer that persisted an install constructs its client in one
call instead of switching on the platform and hand-wiring the URL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Final, Protocol, runtime_checkable

import httpx

from peek_app_utilities.access_options import AccessOptions
from peek_app_utilities.access_service_config import BaseAccessServiceConfig
from peek_app_utilities.acme_access_service import AcmeAccessService
from peek_app_utilities.cng_access_service import CngAccessService
from peek_app_utilities.logger import Logger
from peek_app_utilities.models.peek.auth_token import PeekPlatform
from peek_app_utilities.peek_access_service import PeekAccessService, PeekAccessServiceConfig


@runtime_checkable
class InstallAccessTarget(Protocol):
    """The per-install facts needed to build an access service — a structural
    subset of :class:`~peek_app_utilities.models.peek.install.InstallWebhook`,
    so a persisted install record (or the webhook event itself) satisfies it."""

    @property
    def platform(self) -> PeekPlatform | None: ...

    @property
    def api_url(self) -> str: ...

    @property
    def install_id(self) -> str: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class InstallAccessConfig:
    """The per-app credentials/options shared by every access service —
    everything in :class:`PeekAccessServiceConfig` except the per-install
    ``install_id``/``api_url`` (supplied by the target) and the deprecated
    ``app_id``/``base_url``/``mode`` URL controls. ``gateway_key`` is accepted
    for Peek and ignored by CNG/ACME."""

    jwt_secret: str
    issuer: str
    gateway_key: str | None = None
    token_ttl_seconds: int | None = None
    token_refresh_leeway_seconds: int | None = None
    retry_delays_ms: Sequence[int] | None = None
    logger: Logger | None = None
    http_client: httpx.AsyncClient | None = None
    access_options: AccessOptions | None = None
    item_options_page_size: int | None = None


InstallAccessService = PeekAccessService | CngAccessService | AcmeAccessService
"""The union of access services the factory can return, narrowed by ``platform``."""

_PEEK_ONLY_FIELDS: Final = ("gateway_key", "item_options_page_size")


def create_access_service_for_install(
    install: InstallAccessTarget, config: InstallAccessConfig
) -> InstallAccessService:
    """Builds the access service for ``install.platform``, using
    ``install.api_url`` as the service's endpoint. Narrow the return by
    ``install.platform`` (or ``isinstance``) to reach a platform-specific surface.

    :raises ValueError: when ``install.platform`` is ``None`` or unrecognised — an
        install with an unknown platform has no service to route to, and
        silently defaulting would point it at the wrong platform.
    """
    shared = {f.name: getattr(config, f.name) for f in fields(config)}
    platform = install.platform
    if platform == "peek":
        return PeekAccessService(
            PeekAccessServiceConfig(
                install_id=install.install_id, api_url=install.api_url, **shared
            )
        )
    # CNG/ACME take the base config only: drop the Peek-only extras.
    for peek_only in _PEEK_ONLY_FIELDS:
        shared.pop(peek_only, None)
    base_config = BaseAccessServiceConfig(
        install_id=install.install_id, api_url=install.api_url, **shared
    )
    if platform == "cng":
        return CngAccessService(base_config)
    if platform == "acme":
        return AcmeAccessService(base_config)
    raise ValueError(
        "create_access_service_for_install: unknown or missing platform "
        f'"{platform}" for install "{install.install_id}"'
    )
