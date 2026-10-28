"""Pure functions that map raw Peek GraphQL nodes into the clean :class:`Product`
model. No I/O — straightforward, testable transformations.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from peek_app_utilities.internal.peek.money import to_pricing_money
from peek_app_utilities.internal.peek.products.product_queries import (
    ActivityNode,
    ItemOptionNode,
    ResourceOptionNode,
)
from peek_app_utilities.models.peek.product import (
    ADD_ON_PRODUCT_TYPE,
    Product,
    ProductMeetingLocation,
    ProductTicket,
)

ADD_ON_COLOR: Final = "#FFFFFF"
"""Default display color applied to add-on products."""


def _to_meeting_location(activity: ActivityNode) -> ProductMeetingLocation | None:
    """Builds a :class:`ProductMeetingLocation` from the flat activity fields,
    collapsing to ``None`` when Peek reports no location detail at all. Each
    field is independently nullable."""
    summary = activity.get("infoMeetingLocation")
    address = activity.get("meetingLocationFormattedAddress")
    url = activity.get("meetingLocationUrl")
    if summary is None and address is None and url is None:
        return None
    return ProductMeetingLocation(summary=summary, address=address, url=url)


def _to_ticket(option: ResourceOptionNode) -> ProductTicket:
    price_range = option.get("priceRange") or {}
    return ProductTicket(
        id=option.get("id") or "",
        name=option.get("name") or "",
        min_price=to_pricing_money(price_range.get("min")),
        max_price=to_pricing_money(price_range.get("max")),
    )


def from_activities(activities: Iterable[ActivityNode]) -> list[Product]:
    """Converts the activities from a products response into :class:`Product` s."""
    return [_from_activity(activity) for activity in activities]


def _from_activity(activity: ActivityNode) -> Product:
    """Converts a single activity node into a :class:`Product`."""
    return Product(
        # Prefer the primary GraphQL ID for stable product identity.
        product_id=activity.get("id") or activity.get("legacyId") or "",
        name=activity.get("name") or "",
        type=activity.get("type") or "",
        color=activity.get("colorHex") or "",
        currency=activity.get("currency") or "",
        image_url=activity.get("imageUrl"),
        description=activity.get("description"),
        meeting_location=_to_meeting_location(activity),
        tickets=[_to_ticket(option) for option in activity.get("resourceOptions") or []],
    )


def from_item_option_nodes(nodes: Iterable[ItemOptionNode]) -> list[Product]:
    """Converts a flat list of item option nodes into add-on :class:`Product` s by
    grouping each option under its parent item. The parent item id becomes the
    ``product_id`` and its name becomes the product ``name``; each option
    becomes a ticket. Nodes without a parent item id are skipped."""
    grouped: dict[str, Product] = {}

    for node in nodes:
        item = node.get("item") or {}
        item_id = item.get("id")
        if not item_id:
            continue

        product = grouped.get(item_id)
        if product is None:
            product = Product(
                product_id=item_id,
                name=item.get("name") or "",
                type=ADD_ON_PRODUCT_TYPE,
                color=ADD_ON_COLOR,
                currency="",
                image_url=None,
                description=None,
                meeting_location=None,
                tickets=[],
            )
            grouped[item_id] = product
        product.tickets.append(
            ProductTicket(
                id=node.get("id") or "",
                name=node.get("name") or "",
                min_price=None,
                max_price=None,
            )
        )

    return list(grouped.values())
