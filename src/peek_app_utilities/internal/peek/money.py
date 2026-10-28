"""Shared, pure helper for mapping a raw money node
(``{amount, currency, formatted}``) into the clean :class:`PricingMoney` model.

Internal only — never re-exported from the public barrel. Converters across
resources (products, pricing overrides) reuse this so the ``formatted →
display_price`` mapping lives in exactly one place.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from peek_app_utilities.models.peek.pricing import PricingMoney


class RawMoney(TypedDict, total=False):
    """A raw money node as returned by the API."""

    amount: str
    currency: str
    formatted: str | None
    """Human-formatted display string (e.g. ``"$50.00"``)."""


def to_pricing_money(raw: Mapping[str, Any] | None) -> PricingMoney | None:
    """Maps a raw money node into a :class:`PricingMoney`, carrying the API's
    ``formatted`` string across as ``display_price``. Returns ``None`` for an
    absent/``None`` input so callers can pass an optional wire field straight
    through."""
    if not raw:
        return None
    return PricingMoney(
        amount=raw.get("amount") or "",
        currency=raw.get("currency") or "",
        display_price=raw.get("formatted"),
    )
