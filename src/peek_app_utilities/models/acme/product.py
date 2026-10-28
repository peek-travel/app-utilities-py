"""The clean data model for an ACME event template.

The ACME sibling of ``models/cng/product.py``. Kept separate because ACME is a
distinct backoffice, but the shape mirrors the CNG ``Activity`` so consumers
can treat every brand uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

ACME_ACTIVITY_TYPE: Final = "standard"
""":attr:`AcmeActivity.type` fallback for templates missing a type."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AcmeActivityTicket:
    """A single bookable sub-option (ticket) of an :class:`AcmeActivity`."""

    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AcmeActivity:
    """A bookable activity in an ACME account (an event template).

    ``AcmeProductService.get_all_activities()`` returns these as a flat list,
    filtered to published templates only. ACME does not expose tickets today, so
    :attr:`tickets` is always empty.
    """

    product_id: str
    """Stable unique identifier for the activity."""
    name: str
    """Human-readable display name."""
    type: str
    """Product type reported by ACME (e.g. ``"standard"``)."""
    color: str
    """Display color as a hex string. Falls back to ``"#d1d1d1"`` when unset."""
    tickets: list[AcmeActivityTicket] = field(default_factory=list)
    """Always empty today."""
