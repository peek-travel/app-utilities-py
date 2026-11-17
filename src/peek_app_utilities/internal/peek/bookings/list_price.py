"""Pure helpers for splitting a booking's total list price across its tickets.
I/O-free; validation raises ``ValueError`` on a malformed amount.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

ERROR_LIST_PRICE_INVALID: Final = (
    "listPrice must be a positive number string, e.g. '100', '1,000', or '10.00'"
)

_AMOUNT_RE: Final = re.compile(r"\d+(\.\d+)?")
_CENTS_PER_UNIT: Final = Decimal(100)


def _parse_list_price_to_cents(list_price: Any) -> int:
    """Parses a list-price string into a positive integer number of cents. Commas
    (thousands separators) are stripped; the value is rounded to the nearest cent.
    Raises ``ValueError`` when the input is not a positive number string."""
    if not isinstance(list_price, str):
        raise ValueError(ERROR_LIST_PRICE_INVALID)
    cleaned = list_price.replace(",", "").strip()
    if not _AMOUNT_RE.fullmatch(cleaned):
        raise ValueError(ERROR_LIST_PRICE_INVALID)
    cents = int((Decimal(cleaned) * _CENTS_PER_UNIT).to_integral_value(rounding=ROUND_HALF_UP))
    if cents <= 0:
        raise ValueError(ERROR_LIST_PRICE_INVALID)
    return cents


def _cents_to_amount(cents: int) -> str:
    """Formats an integer number of cents as a 2-decimal string (e.g. 334 → ``"3.34"``)."""
    return f"{Decimal(cents) / _CENTS_PER_UNIT:.2f}"


def distribute_list_price(list_price: str, ticket_count: int) -> list[str]:
    """Splits a total list price evenly across ``ticket_count`` tickets, as
    2-decimal amount strings. Each of the first ``n-1`` tickets gets
    ``floor(total / n)``; the last ticket gets the remainder, so the amounts
    always sum back to the exact total. For example ``"10.00"`` over 3 tickets →
    ``["3.33", "3.33", "3.34"]``.

    ``ticket_count`` must be a positive integer (the caller guarantees at least
    one ticket). Raises ``ValueError`` when ``list_price`` is not a positive
    number string."""
    total_cents = _parse_list_price_to_cents(list_price)
    per_ticket_cents = total_cents // ticket_count
    amounts = [_cents_to_amount(per_ticket_cents) for _ in range(ticket_count - 1)]
    amounts.append(_cents_to_amount(total_cents - per_ticket_cents * (ticket_count - 1)))
    return amounts
