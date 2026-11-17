"""Pure functions that map raw ACME template nodes into the clean
:class:`AcmeActivity` model. No I/O.

Only ``"published"`` templates are surfaced; ACME does not expose tickets, so
every activity carries an empty ``tickets`` list.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from peek_app_utilities.internal.acme.products.product_queries import (
    PUBLISHED_REVIEW_STATE,
    TemplateNode,
)
from peek_app_utilities.models.acme.product import ACME_ACTIVITY_TYPE, AcmeActivity

DEFAULT_COLOR: Final = "#d1d1d1"
"""Neutral gray used when a template has no color category."""


def from_template_nodes(nodes: Iterable[TemplateNode]) -> list[AcmeActivity]:
    """Converts raw template nodes into :class:`AcmeActivity` models, keeping only
    published templates."""
    return [
        _from_template_node(node)
        for node in nodes
        if isinstance(node, Mapping) and node.get("reviewState") == PUBLISHED_REVIEW_STATE
    ]


def _from_template_node(node: TemplateNode) -> AcmeActivity:
    color_category = node.get("colorCategory")
    background = (
        color_category.get("backgroundColor") if isinstance(color_category, Mapping) else None
    )
    return AcmeActivity(
        product_id=node.get("id") or "",
        name=node.get("name") or "",
        type=node.get("type") or ACME_ACTIVITY_TYPE,
        color=background or DEFAULT_COLOR,
        tickets=[],
    )
