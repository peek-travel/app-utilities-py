"""The clean data model for Peek Pro memberships."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Membership:
    """A flat representation of a Peek Pro membership variant.

    A membership can expose multiple variants; this model flattens each variant
    into its own record, carrying the parent membership's stable id and display
    name alongside the variant-level details. Memberships with no variants
    produce no records.
    """

    id: str
    """Parent membership id."""
    membership_variant_id: str
    """Variant id."""
    description: str | None
    """Variant description, or ``None``."""
    external_name: str
    """Variant external (customer-facing) name."""
    image_url: str | None
    """Variant image URL, or ``None``."""
    internal_name: str
    """Variant internal name."""
    display_name: str
    """Parent membership display name."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipPurchaseInput:
    """Input for purchasing a membership."""

    membership_variant_id: str
    """The membership variant to purchase."""
    email: str
    """Member email (required)."""
    country: str | None = None
    """ISO country code (optional)."""
    formatted_address: str | None = None
    """Formatted address (optional)."""
    membership_code: str | None = None
    """Membership code (optional)."""
    phone: str | None = None
    """Member phone (optional)."""
    name: str | None = None
    """Member name (optional)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchasedMembership:
    """The result of purchasing a membership."""

    order_id: str
    membership_id: str
    display_id: str
    primary_member_id: str | None
    primary_member_name: str | None
    balance_amount: str
    balance_currency: str
    balance_formatted: str
