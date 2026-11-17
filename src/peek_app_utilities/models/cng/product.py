"""The clean data model for a CNG product.

The CNG sibling of ``models/peek/product.py``. Kept as a separate model because
CNG is a distinct backoffice, but the shape deliberately mirrors the Peek
``Product`` so consumers can treat both brands uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

ACTIVITY_PRODUCT_TYPE: Final = "ACTIVITY"
""":attr:`Activity.type` for standard bookable activities."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivityTicket:
    """A single bookable sub-option (ticket) of an :class:`Activity`."""

    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Activity:
    """A bookable activity in a CNG account.

    ``CngProductService.get_all_activities()`` returns these as a flat list. The
    CNG products payload carries no product-type discriminator and no
    sub-options, so :attr:`type` is always :data:`ACTIVITY_PRODUCT_TYPE` and
    :attr:`tickets` is always empty.
    """

    product_id: str
    """Stable unique identifier for the activity."""
    name: str
    """Human-readable display name."""
    type: str
    """Product type. Always :data:`ACTIVITY_PRODUCT_TYPE`."""
    color: str
    """Display color as a hex string (e.g. ``"#1A2B3C"``). Empty when unset."""
    tickets: list[ActivityTicket] = field(default_factory=list)
    """Always empty — CNG exposes no tickets on the products endpoint today."""
