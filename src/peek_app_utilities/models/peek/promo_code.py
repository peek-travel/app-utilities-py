"""The clean data model for Peek Pro promo codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PROMO_DISCOUNT_TYPES: Final[tuple[str, ...]] = ("percent", "fixed")
"""Every discount type :attr:`CreatePromoCodeInput.discount_type` accepts."""

PromoDiscountType = Literal["percent", "fixed"]
"""Whether a promo-code amount is a percentage or a fixed monetary value."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PromoCodeFixedAmount:
    """A fixed monetary discount on a :class:`PromoCode`."""

    amount: float
    """Amount in the currency's minor/major unit as reported by Peek."""
    currency: str
    """ISO currency code."""
    formatted: str
    """Human-formatted amount (e.g. ``"$10.00"``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PromoCode:
    """A promo code on a Peek Pro account."""

    id: str
    """Unique identifier."""
    name: str
    """Display name."""
    percent_amount: float | None
    """Percentage discount (0 to 100), or ``None`` for a fixed-amount code."""
    per_ticket_discount: bool
    """Whether the discount applies per ticket."""
    redemption_code: str
    """The code guests redeem."""
    fixed_amount: PromoCodeFixedAmount | None
    """Fixed-amount discount, or ``None`` for a percentage code."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatePromoCodeInput:
    """Input for creating a promo code."""

    name: str
    """Display name."""
    code: str
    """The redemption code."""
    amount: str
    """Discount amount as a string (percentage or fixed value)."""
    discount_type: PromoDiscountType
    """Whether ``amount`` is a percentage or a fixed monetary value."""
    max_redemptions: int | None = None
    """Optional cap on total redemptions."""
    currency: str | None = None
    """ISO currency code for fixed discounts. Defaults to ``"USD"``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedPromoCode:
    """The result of creating a promo code (the mutation returns id + name)."""

    id: str
    name: str
