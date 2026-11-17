"""The clean data model for a booking's payments on file."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentAmount:
    """A money amount on a payment (numeric string + ISO currency code)."""

    amount: str
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Payment:
    """A single payment applied to a booking's order."""

    id: str
    """Payment id (``pmt_…``)."""
    paid_at: str
    """Date the payment was applied (``YYYY-MM-DD``)."""
    current_amount: PaymentAmount
    """The payment's current (net of refunds) amount."""
    refundable_amount: PaymentAmount
    """How much of the payment can still be refunded."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentSource:
    """A payment source on the order, with any payments made against it."""

    description: str
    """Human-readable description of the source (e.g. a card summary)."""
    id: str
    """Payment source id (``ps_…``, or a synthetic id like ``cash/cash``)."""
    type: str
    """Source type reported by Peek (e.g. card/cash/custom)."""
    payments: list[Payment] | None = None
    """Payments made against this source, when any exist."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingPaymentsOnFile:
    """The payments-on-file result for a booking."""

    booking_id: str
    """The booking these payments belong to."""
    order_id: str
    """The order id the payments live on."""
    payments_on_file: list[PaymentSource]
    """The order's payment sources, each with its payments grouped under it."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MakePaymentInput:
    """Input for charging a booking."""

    booking_id: str
    """Booking id (normalized internally)."""
    payment_source_id: str
    """Payment source id (``ps_…``, or one of ``cash/cash``, ``custom/other``,
    ``custom/voucher``)."""
    amount: str
    """Amount as a numeric string."""
    currency: str
    """3-letter uppercase ISO currency code."""
    idempotency_key: str
    """Idempotency key passed through to Peek."""
    customer_message: str | None = None
    """Optional message appended to the default customer message."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MakePaymentResult:
    """Result of charging a booking."""

    transaction_id: str
    """The transaction id for the charge."""
    booking_id: str
    """The booking that was charged."""
    order_id: str
    """The order the charge was applied to."""
    amount: str
    """Amount charged, as a numeric string."""
    currency: str
    """3-letter uppercase ISO currency code of the charge."""
    payment_source_id: str
    """The payment source that was charged."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundInput:
    """Input for refunding a booking payment."""

    booking_id: str
    """Booking id (normalized internally)."""
    payment_id: str
    """Payment id to refund (``pmt_…``)."""
    amount: str
    """Amount as a numeric string."""
    currency: str
    """3-letter uppercase ISO currency code."""
    idempotency_key: str
    """Idempotency key passed through to Peek."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundResult:
    """Result of refunding a booking payment."""

    transaction_id: str
    """The transaction id for the refund."""
    booking_id: str
    """The booking that was refunded."""
    order_id: str
    """The order the refund was applied to."""
    amount: str
    """Amount refunded, as a numeric string."""
    currency: str
    """3-letter uppercase ISO currency code of the refund."""
    payment_id: str
    """The payment that was refunded (``pmt_…``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceLinkResult:
    """Result of creating an invoice link."""

    booking_id: str
    """The booking the invoice is for."""
    order_id: str
    """The order the invoice is for."""
    invoice_link: str
    """The customer-facing URL where the invoice can be paid."""
