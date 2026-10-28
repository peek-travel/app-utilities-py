"""Product-related operations against the CNG platform.

Obtain an instance via ``CngAccessService.get_product_service()`` rather than
constructing it directly — the access service wires in the authenticated,
shared transport. Named ``CngProductService`` to disambiguate from the Peek
``ProductService`` in the same package.
"""

from __future__ import annotations

from collections.abc import Mapping

from peek_app_utilities.internal.cng.endpoints import CNG_PRODUCTS_ENDPOINT, PRODUCTS_PATH
from peek_app_utilities.internal.cng.products.product_converter import from_product_nodes
from peek_app_utilities.internal.rest_client import RestClient
from peek_app_utilities.models.cng.product import Activity


class CngProductService:
    def __init__(self, client: RestClient) -> None:
        self._client = client

    async def get_all_activities(self) -> list[Activity]:
        """Returns every activity as a single flat list.

        Example::

            activities = await cng.get_product_service().get_all_activities()
        """
        body = await self._client.get(CNG_PRODUCTS_ENDPOINT, PRODUCTS_PATH)
        data = body.get("data") if isinstance(body, Mapping) else None
        return from_product_nodes(data or [])
