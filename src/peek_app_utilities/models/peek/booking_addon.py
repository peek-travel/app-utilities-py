"""Clean, public data models for a booking's add-ons.

These are the only add-on shapes a consumer sees. The detailed per-option
model used to build add/cancel mutations (refids, reservation statuses) is
an internal implementation detail and is intentionally not exported.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingAddonMoney:
    """Money amount for an add-on line, as returned by the API."""

    amount: str
    """Numeric amount as a string (e.g. ``"10.00"``)."""
    currency: str
    """ISO currency code (e.g. ``"USD"``)."""
    formatted: str
    """Human-formatted amount (e.g. ``"$10.00"``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingAddonOption:
    """A single add-on option with the quantity attached to the booking."""

    addon_option_id: str
    """The item option id (``itemOptionSnapshot.id``)."""
    addon_option_name: str
    """The item option name (``itemOptionSnapshot.name``)."""
    quantity: int
    """How many live (non-canceled) units of this option are on the booking."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingAddon:
    """An add-on attached to a booking, grouped by add-on item."""

    addon_id: str
    """The add-on item id (``itemSnapshot.id``)."""
    addon_name: str
    """The add-on item name (``itemSnapshot.name``)."""
    total: BookingAddonMoney | None
    """The booking line-item total for this add-on, when present."""
    addon_options: list[BookingAddonOption]
    """Live options on this add-on, combined by option id with a count."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingAddons:
    """A booking's add-ons."""

    booking_id: str
    """The booking id these add-ons belong to."""
    display_id: str
    """The booking's human-facing display id."""
    order_id: str
    """The order id the add-ons live on."""
    addons: list[BookingAddon]
    """Add-ons with at least one live option; fully-canceled add-ons are omitted."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingAddonsMutationResult:
    """Result of an add-on mutation (add or remove). Both operations finish by
    re-listing the booking's add-ons and returning the post-change state rather
    than echoing quote details."""

    updated_booking_addons: BookingAddons
