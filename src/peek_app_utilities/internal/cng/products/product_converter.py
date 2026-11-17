"""Pure functions that map raw CNG product nodes into the clean
:class:`Activity` model. No I/O — straightforward, testable transformations.
"""

from __future__ import annotations

from collections.abc import Iterable

from peek_app_utilities.internal.cng.products.product_queries import ProductNode
from peek_app_utilities.models.cng.product import ACTIVITY_PRODUCT_TYPE, Activity


def from_product_nodes(nodes: Iterable[ProductNode]) -> list[Activity]:
    """Converts a list of raw product nodes into :class:`Activity` models."""
    return [_from_product_node(node) for node in nodes]


def _from_product_node(node: ProductNode) -> Activity:
    raw_id = node.get("id")
    return Activity(
        product_id="" if raw_id is None else str(raw_id),
        name=node.get("name") or "",
        type=ACTIVITY_PRODUCT_TYPE,
        color=node.get("access_control_color_hex") or "",
        tickets=[],
    )
