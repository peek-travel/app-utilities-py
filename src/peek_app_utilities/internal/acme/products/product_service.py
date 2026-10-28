"""Product-related operations against the ACME platform.

Obtain an instance via ``AcmeAccessService.get_product_service()`` rather than
constructing it directly. Named ``AcmeProductService`` to disambiguate from the
Peek ``ProductService`` and the CNG ``CngProductService``.
"""

from __future__ import annotations

from collections.abc import Mapping

from peek_app_utilities.internal.acme.endpoints import ACME_TEMPLATES_ENDPOINT, TEMPLATES_PATH
from peek_app_utilities.internal.acme.products.product_converter import from_template_nodes
from peek_app_utilities.internal.rest_client import RestClient
from peek_app_utilities.models.acme.product import AcmeActivity


class AcmeProductService:
    def __init__(self, client: RestClient) -> None:
        self._client = client

    async def get_all_activities(self) -> list[AcmeActivity]:
        """Returns every published event template as a flat list of activities.

        Example::

            activities = await acme.get_product_service().get_all_activities()
        """
        body = await self._client.get(ACME_TEMPLATES_ENDPOINT, TEMPLATES_PATH)
        # Tolerate either a { list: [...] } envelope or a bare array.
        if isinstance(body, list):
            nodes = body
        elif isinstance(body, Mapping):
            nodes = body.get("list") or []
        else:
            nodes = []
        return from_template_nodes(nodes)
