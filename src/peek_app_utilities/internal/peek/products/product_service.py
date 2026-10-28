"""Product-related operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_product_service()`` rather than
constructing it directly — the access service wires in the authenticated,
shared transport. This class is where product-specific business logic lives.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Final

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.products.custom_question_converter import (
    from_question_configurations,
)
from peek_app_utilities.internal.peek.products.custom_question_queries import (
    CUSTOM_QUESTIONS_QUERY,
)
from peek_app_utilities.internal.peek.products.product_converter import (
    from_activities,
    from_item_option_nodes,
)
from peek_app_utilities.internal.peek.products.product_queries import (
    ITEM_OPTIONS_QUERY,
    PRODUCTS_QUERY,
    ActivityNode,
    ItemOptionNode,
)
from peek_app_utilities.models.peek.custom_question import CustomQuestion
from peek_app_utilities.models.peek.product import (
    ACTIVITY_PRODUCT_TYPE,
    RENTAL_PRODUCT_TYPE,
    Product,
)

ERROR_PRODUCT_ID_REQUIRED: Final = "A non-empty product id is required."
"""Raised-error message when a product id is missing or blank."""

DEFAULT_ITEM_OPTIONS_PAGE_SIZE: Final = 50
"""Default page size for cursor-paginated item options."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductServiceOptions:
    """Tuning options for a :class:`ProductService`."""

    item_options_page_size: int | None = None
    """Page size for cursor-paginated item options. Default: 50."""


class ProductService:
    """Product reads for one install. Obtain via
    ``PeekAccessService.get_product_service()``."""

    def __init__(self, client: GraphQLClient, options: ProductServiceOptions | None = None) -> None:
        self._client = client
        resolved = options or ProductServiceOptions()
        self._item_options_page_size = (
            resolved.item_options_page_size
            if resolved.item_options_page_size is not None
            else DEFAULT_ITEM_OPTIONS_PAGE_SIZE
        )

    async def get_all_products(self) -> list[Product]:
        """Returns every product as a single flat list: activities plus add-ons
        (the latter tagged with the add-on type). Add-ons are gathered across all
        cursor-paginated pages.

        Example — split activities from add-ons::

            from peek_app_utilities import ADD_ON_PRODUCT_TYPE

            products = await peek.get_product_service().get_all_products()
            activities = [p for p in products if p.type != ADD_ON_PRODUCT_TYPE]
            addons = [p for p in products if p.type == ADD_ON_PRODUCT_TYPE]
        """
        activities, item_option_nodes = await asyncio.gather(
            self._fetch_activities(), self._fetch_all_item_option_nodes()
        )
        return [*from_activities(activities), *from_item_option_nodes(item_option_nodes)]

    async def get_all_activities(self) -> list[Product]:
        """Returns products with type :data:`ACTIVITY_PRODUCT_TYPE`."""
        return await self._fetch_activities_of_type(ACTIVITY_PRODUCT_TYPE)

    async def get_all_rentals(self) -> list[Product]:
        """Returns products with type :data:`RENTAL_PRODUCT_TYPE`."""
        return await self._fetch_activities_of_type(RENTAL_PRODUCT_TYPE)

    async def get_all_addons(self) -> list[Product]:
        """Returns only add-on products."""
        return from_item_option_nodes(await self._fetch_all_item_option_nodes())

    async def get_custom_questions(self, product_id: str) -> list[CustomQuestion]:
        """Returns every custom question configured on a single activity, in the
        order Peek reports them. Choice-style questions (``SELECT_ONE``,
        ``LOCATION``, …) carry their selectable :attr:`CustomQuestion.options`;
        free-text/checkbox questions return an empty option list.

        These are question **definitions**, not customer answers — no PII is
        involved, so the result is unaffected by ``full_customer_access``.

        :param product_id: The activity's id.
        :returns: The activity's custom questions, or an empty list when the
            activity has none or is not found.
        :raises ValueError: when ``product_id`` is missing or blank.
        """
        if not product_id or not product_id.strip():
            raise ValueError(ERROR_PRODUCT_ID_REQUIRED)

        body = await self._client.request(
            SALES_ENDPOINT, CUSTOM_QUESTIONS_QUERY, {"id": product_id}
        )
        activity = (body.get("data") or {}).get("activity") or {}
        configs = activity.get("questionActivityConfigurations") or []
        return from_question_configurations(configs)

    async def _fetch_activities_of_type(self, product_type: str) -> list[Product]:
        activities = await self._fetch_activities()
        return [p for p in from_activities(activities) if p.type == product_type]

    async def _fetch_activities(self) -> list[ActivityNode]:
        body = await self._client.request(SALES_ENDPOINT, PRODUCTS_QUERY, {})
        activities: list[ActivityNode] = (body.get("data") or {}).get("activities") or []
        return activities

    async def _fetch_all_item_option_nodes(self) -> list[ItemOptionNode]:
        # Cursor pagination is inherently sequential: each page yields the next cursor.
        all_nodes: list[ItemOptionNode] = []
        after: str | None = None

        while True:
            body = await self._client.request(
                SALES_ENDPOINT,
                ITEM_OPTIONS_QUERY,
                {"first": self._item_options_page_size, "after": after},
            )
            connection: dict[str, Any] = (body.get("data") or {}).get("itemOptions") or {}
            all_nodes.extend(edge["node"] for edge in connection.get("edges") or [])

            page_info: dict[str, Any] = connection.get("pageInfo") or {}
            end_cursor = page_info.get("endCursor")
            if page_info.get("hasNextPage") and end_cursor:
                after = end_cursor
            else:
                break

        return all_nodes
