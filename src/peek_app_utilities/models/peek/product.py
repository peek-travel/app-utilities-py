"""The clean, transport-agnostic data model for a Peek Pro product.

This is the shape consumers of the package work with. It is intentionally
decoupled from the underlying Peek schema — the raw types and the conversion
logic live inside the package and are never exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from peek_app_utilities.models.peek.pricing import PricingMoney

ACTIVITY_PRODUCT_TYPE: Final = "ACTIVITY"
""":attr:`Product.type` for standard bookable activities."""

RENTAL_PRODUCT_TYPE: Final = "RENTAL"
""":attr:`Product.type` for rental products."""

ADD_ON_PRODUCT_TYPE: Final = "ADD-ON"
"""The :attr:`Product.type` value assigned to add-on products.

Exposed so callers can filter add-ons out of (or in to) the combined list
returned by ``ProductService.get_all_products()`` without hard-coding the string.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductMeetingLocation:
    """The meeting point for a bookable experience. Every field is nullable."""

    summary: str | None
    """Free-text summary / instructions for the meeting point."""
    address: str | None
    """Formatted postal address of the meeting point."""
    url: str | None
    """Map/link URL for the meeting point."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductTicket:
    """A single bookable sub-option (resource option or add-on item option)."""

    id: str
    """Unique identifier of the ticket / option. This is also the
    **``resource_option_id``** — the id passed as a ticket's ``resource_option_id``
    when creating a booking and reported per slot by
    ``AvailabilityService.get_availability_times``."""
    name: str
    """Human-readable name of the ticket / option."""
    min_price: PricingMoney | None
    """Lowest price this ticket can be sold at, across its price range.

    Populated for activity/rental resource options that expose a price range;
    ``None`` for add-on options (which carry no range) and when Peek reports none.
    """
    max_price: PricingMoney | None
    """Highest price this ticket can be sold at, across its price range.

    Populated for activity/rental resource options that expose a price range;
    ``None`` for add-on options (which carry no range) and when Peek reports none.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class Product:
    """A bookable product in a Peek Pro account.

    ``ProductService.get_all_products()`` returns a single flat list that combines
    two distinct Peek concepts into one uniform shape:

    - **Activities** — the primary bookable experiences (tours, rentals, classes,
      etc.). Their :attr:`type` is whatever Peek reports for the activity.
    - **Add-ons** — optional item options offered alongside activities. They are
      grouped under their parent item and always carry the
      :data:`ADD_ON_PRODUCT_TYPE` (``"ADD-ON"``) type, so callers can tell the two
      apart with a single field check.
    """

    product_id: str
    """Stable unique identifier for the product.

    - Activities: the primary ``id`` (falls back to the ``legacyId``).
    - Add-ons: the id of the parent item the options belong to.
    """
    name: str
    """Human-readable display name."""
    type: str
    """Product type. For activities this is the type reported by Peek; for
    add-ons it is always :data:`ADD_ON_PRODUCT_TYPE`."""
    color: str
    """Display color as a hex string (e.g. ``"#1A2B3C"``). Add-ons default to
    white (``"#FFFFFF"``). Empty string when no color is set."""
    currency: str
    """ISO 4217 currency code the activity prices in (e.g. ``"USD"``).

    Populated for activities and rentals; empty string for add-ons (which carry
    no currency of their own) and when Peek reports none. Consumers building
    pricing overrides use this to set the currency on fixed-price adjustments.
    """
    image_url: str | None
    """URL of the product's primary display image, or ``None`` when Peek reports
    none. Populated for activities/rentals; always ``None`` for add-ons."""
    description: str | None
    """Long-form product description (may contain HTML), or ``None`` when Peek
    reports none. Populated for activities/rentals; always ``None`` for add-ons."""
    meeting_location: ProductMeetingLocation | None
    """Where the experience meets, or ``None`` when Peek reports no location
    detail. Populated for activities/rentals; always ``None`` for add-ons. Each
    field inside is independently nullable."""
    tickets: list[ProductTicket]
    """The bookable sub-options of this product.

    - Activities: the activity's resource options.
    - Add-ons: each individual item option grouped under the parent item.
    """
