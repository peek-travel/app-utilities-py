"""Aggregates a booking's raw order payments + payment sources into the clean
:class:`BookingPaymentsOnFile` model, grouping payments under their source. Pure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from peek_app_utilities.models.peek.booking_payment import (
    BookingPaymentsOnFile,
    Payment,
    PaymentAmount,
    PaymentSource,
)


def _amount(raw: Any) -> PaymentAmount:
    node: Mapping[str, Any] = raw or {}
    return PaymentAmount(amount=node.get("amount") or "", currency=node.get("currency") or "")


def _date_only(iso: str) -> str:
    return iso.split("T")[0]


def from_payments_on_file_response(
    response: Mapping[str, Any] | None, booking_id: str
) -> BookingPaymentsOnFile | None:
    """Maps a payments-on-file response into the aggregated result, or ``None``
    when the booking is not found."""
    sales = (response or {}).get("sales") or {}
    edges = sales.get("edges") or []
    if not edges:
        return None

    order: Mapping[str, Any] = ((edges[0] or {}).get("node") or {}).get("order") or {}
    order_id = order.get("id") or ""
    raw_payment_sources: list[Mapping[str, Any]] = order.get("paymentSources") or []
    raw_payments: list[Mapping[str, Any]] = order.get("payments") or []

    payments_by_source_id: dict[str, list[Payment]] = {}
    for payment in raw_payments:
        source_id = (payment.get("paymentSource") or {}).get("id")
        if not source_id:
            continue
        mapped = Payment(
            id=payment.get("id") or "",
            paid_at=_date_only(payment.get("appliedAt") or ""),
            current_amount=_amount(payment.get("currentAmount")),
            refundable_amount=_amount(payment.get("refundableAmount")),
        )
        payments_by_source_id.setdefault(source_id, []).append(mapped)

    payments_on_file = [
        PaymentSource(
            description=source.get("description") or "",
            id=source.get("id") or "",
            type=source.get("type") or "",
            payments=payments_by_source_id.get(source.get("id") or ""),
        )
        for source in raw_payment_sources
    ]

    return BookingPaymentsOnFile(
        booking_id=booking_id, order_id=order_id, payments_on_file=payments_on_file
    )
