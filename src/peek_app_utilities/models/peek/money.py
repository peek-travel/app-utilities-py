"""A monetary value as returned by the Peek API, shared across services and
resources (booking add-ons, availability prices, …).

``amount`` is intentionally a **string** (e.g. ``"50.00"``), never a number —
the API returns stringly-typed money to avoid floating-point precision loss.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Money:
    """A monetary value: decimal-string amount, currency code, display string."""

    amount: str
    """Numeric amount as a decimal string (e.g. ``"50.00"``)."""
    currency: str
    """ISO 4217 currency code (e.g. ``"USD"``)."""
    formatted: str
    """Human-formatted amount (e.g. ``"$50.00"``)."""
