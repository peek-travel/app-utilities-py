"""Authenticated root entry point to the CNG backoffice API.

The CNG sibling of :class:`PeekAccessService`. Configure one instance per
install; it owns the shared, authenticated transport (minting/caching tokens on
demand) and hands out the :class:`CngProductService`.

Auth mirrors the Peek access service: the same app JWT (``X-Peek-Auth: Bearer``)
minted from the Peek app credentials via the shared ``TokenManager``, routed
through the app-registry installations API with the ``cng_backoffice_api-v1``
slug and no ``pk-api-key`` header.
"""

from __future__ import annotations

from types import TracebackType
from typing import Final, Self

from peek_app_utilities.access_service_config import BaseAccessServiceConfig
from peek_app_utilities.errors import CngApiError
from peek_app_utilities.internal.cng.endpoints import CNG_API_ENDPOINTS, CNG_EXTENDABLE_SLUG
from peek_app_utilities.internal.cng.permissions import forbidden_error
from peek_app_utilities.internal.cng.products.product_service import CngProductService
from peek_app_utilities.internal.rest_access import OwnedHttpClient, build_rest_client

SERVICE_NAME: Final = "CngAccessService"
_PLATFORM_LABEL: Final = "CNG"

CngAccessServiceConfig = BaseAccessServiceConfig
"""Configuration for a :class:`CngAccessService`. CNG adds no fields beyond
:class:`BaseAccessServiceConfig` — it authenticates on the app JWT alone."""


class CngAccessService:
    """Authenticated root entry point to the CNG backoffice API.

    Example::

        async with CngAccessService(CngAccessServiceConfig(
            install_id="install-123",
            jwt_secret=os.environ["PEEK_APP_SECRET"],
            issuer=os.environ["PEEK_APP_ID"],
            api_url=install.api_url,
        )) as cng:
            activities = await cng.get_product_service().get_all_activities()

    :raises ValueError: from the constructor when any required config field
        (``install_id``, ``jwt_secret``, ``issuer``; ``app_id`` without
        ``api_url``) is empty, or ``api_url`` carries another platform's slug.
    """

    def __init__(self, config: CngAccessServiceConfig) -> None:
        self._http = OwnedHttpClient(config.http_client)
        self._client = build_rest_client(
            config,
            service_name=SERVICE_NAME,
            slug=CNG_EXTENDABLE_SLUG,
            endpoints=CNG_API_ENDPOINTS,
            platform_label=_PLATFORM_LABEL,
            api_error=CngApiError,
            on_forbidden=forbidden_error,
            http=self._http,
        )
        self._product_service: CngProductService | None = None

    def get_product_service(self) -> CngProductService:
        """Returns the :class:`CngProductService` for this install, bound to the
        shared authenticated transport. Created lazily and reused."""
        if self._product_service is None:
            self._product_service = CngProductService(self._client)
        return self._product_service

    async def aclose(self) -> None:
        """Closes the package-owned HTTP client (a caller-supplied one is left open)."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
