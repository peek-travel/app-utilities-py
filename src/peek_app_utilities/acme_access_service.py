"""Authenticated root entry point to the ACME backoffice API.

The ACME sibling of :class:`PeekAccessService` / :class:`CngAccessService`.
Configure one instance per install; it owns the shared, authenticated transport
and hands out the :class:`AcmeProductService`. Routing uses the
``acme_backoffice_api-v1`` slug; there is no ``pk-api-key`` header.
"""

from __future__ import annotations

from types import TracebackType
from typing import Final, Self

from peek_app_utilities.access_service_config import BaseAccessServiceConfig
from peek_app_utilities.errors import AcmeApiError
from peek_app_utilities.internal.acme.endpoints import ACME_API_ENDPOINTS, ACME_EXTENDABLE_SLUG
from peek_app_utilities.internal.acme.products.product_service import AcmeProductService
from peek_app_utilities.internal.rest_access import OwnedHttpClient, build_rest_client

SERVICE_NAME: Final = "AcmeAccessService"
_PLATFORM_LABEL: Final = "ACME"

AcmeAccessServiceConfig = BaseAccessServiceConfig
"""Configuration for an :class:`AcmeAccessService`. ACME adds no fields beyond
:class:`BaseAccessServiceConfig`."""


class AcmeAccessService:
    """Authenticated root entry point to the ACME backoffice API.

    Example::

        async with AcmeAccessService(AcmeAccessServiceConfig(
            install_id="install-123",
            jwt_secret=os.environ["PEEK_APP_SECRET"],
            issuer=os.environ["PEEK_APP_ID"],
            api_url=install.api_url,
        )) as acme:
            activities = await acme.get_product_service().get_all_activities()

    :raises ValueError: from the constructor when any required config field is
        empty, or ``api_url`` carries another platform's slug.
    """

    def __init__(self, config: AcmeAccessServiceConfig) -> None:
        self._http = OwnedHttpClient(config.http_client)
        self._client = build_rest_client(
            config,
            service_name=SERVICE_NAME,
            slug=ACME_EXTENDABLE_SLUG,
            endpoints=ACME_API_ENDPOINTS,
            platform_label=_PLATFORM_LABEL,
            api_error=AcmeApiError,
            http=self._http,
        )
        self._product_service: AcmeProductService | None = None

    def get_product_service(self) -> AcmeProductService:
        """Returns the :class:`AcmeProductService` for this install, bound to the
        shared authenticated transport. Created lazily and reused."""
        if self._product_service is None:
            self._product_service = AcmeProductService(self._client)
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
