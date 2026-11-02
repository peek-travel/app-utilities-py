"""The clean, transport-agnostic data model for Peek Pro bookings.

This is the shape consumers of the package work with. It is intentionally
decoupled from the underlying Peek schema — the raw types and the conversion
logic live inside the package and are never exposed here. A booking is the
central resource: it carries the customer, the activity and slot, the ticket
lines, lifecycle flags, money totals, and (optionally) the guest list and full
price breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True, slots=True, kw_only=True)
class Price:
    """A formatted monetary value: a human display string plus its raw amount."""

    display: str
    """Human-formatted amount (e.g. ``"$25.00"``)."""
    amount: str
    """Numeric amount as a string (e.g. ``"25.00"``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Ticket:
    """A ticket line within a booking (one resource option and its quantity)."""

    name: str
    """Ticket (resource option) name, e.g. ``"Adult"``. Falls back to ``"Unknown"``."""
    quantity: int
    """How many of this ticket are on the booking."""
    ticket_id: str
    """The resource option id backing this ticket. Falls back to ``"unknown"``."""
    list_price: Price | None
    """Per-unit list price of the ticket — only populated when
    ``include_price_breakdown`` is requested."""
    total_value: Price | None
    """Total value for this ticket line — only populated when
    ``include_price_breakdown`` is requested."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Resource:
    """A resource pool used by a booking (e.g. a kayak or guide pool), with the
    quantity drawn from it."""

    quantity: int
    """How many units of the resource the booking uses."""
    name: str
    """Resource pool name."""
    short_name: str
    """Resource pool short name."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourcePoolAssignment:
    """A concrete resource assigned to a booking (a specific resource within a
    pool, as opposed to the pool-level :class:`Resource` count)."""

    id: str
    """Assigned resource id."""
    name: str
    """Assigned resource name."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomQuestionAnswer:
    """A custom question/answer captured on a booking or a guest. Location
    questions additionally carry a captured lat/long."""

    question: str
    """The question text as shown to the customer."""
    answer: str
    """The customer's answer."""
    latitude: str | None = None
    """Captured latitude, present only for location questions."""
    longitude: str | None = None
    """Captured longitude, present only for location questions."""


@dataclass(frozen=True, slots=True, kw_only=True)
class GuestMetadata:
    """A custom field response captured against a :class:`Guest`."""

    id: str
    """Field response id."""
    name: str
    """The field's name."""
    value: str
    """The captured value (empty string when none)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Guest:
    """A guest on a booking. Populated only when guests are requested
    (``include_guests``); the primary guest is included and flagged via
    :attr:`is_primary`."""

    id: str
    """Unique guest id."""
    name: str | None
    """Guest name, or ``None``."""
    country: str | None
    """Guest country, or ``None``."""
    date_of_birth: datetime | None
    """Date of birth, or ``None``."""
    phone: str | None
    """Phone number, or ``None``."""
    email: str | None
    """Email address, or ``None``."""
    is_gdpr: bool
    """Whether the guest is subject to GDPR handling."""
    is_participant: bool
    """Whether the guest is an actual participant (vs. a booker only)."""
    is_primary: bool
    """Whether this is the booking's primary guest."""
    optin_sms: bool
    """Whether the guest opted in to SMS."""
    optin_marketing: bool
    """Whether the guest opted in to marketing."""
    postal_code: str | None
    """Postal code, or ``None``."""
    metadata: list[GuestMetadata]
    """Custom field responses captured for this guest."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Booking:
    """A booking in Peek Pro."""

    booking_id: str
    """Stable unique booking id."""
    display_id: str
    """Human-facing display id shown in the Peek UI (e.g. ``"B-123456"``)."""

    source: str
    """Normalized booking source, e.g. ``"website"``, ``"app"``, ``"expedia"``.
    ``"unknown"`` when the origin can't be mapped."""
    source_app: str
    """Raw source app reported by Peek (e.g. ``"WIDGET"``). ``"unknown"`` if absent."""
    source_description: str
    """Human-readable source description (e.g. ``"Website Booking Flow"``).
    ``"unknown"`` when the origin can't be mapped."""
    source_details: str | None
    """Raw source actor name reported by Peek, when present. ``None`` when the
    origin actor carries no name."""

    customer_name: str | None
    """Primary guest's name, or ``""`` when unknown (never requested without
    ``full_customer_access``)."""
    customer_email: str | None
    """Primary guest's email, or ``None``."""
    customer_phone: str | None
    """Primary guest's phone, or ``None``."""

    product_id: str
    """The activity (product) id this booking is for. ``"unknown"`` if absent."""
    product_name: str
    """The activity (product) name. ``"unknown"`` if absent."""
    is_rental_product: bool
    """Whether the booked product is a rental (vs. a standard activity)."""

    timeslot_id: str | None
    """The timeslot's legacy id, or ``None`` when the booking has no timeslot."""
    total_tickets: int
    """Total number of tickets across all ticket lines."""
    ticket_description: str
    """Human-readable ticket summary (e.g. ``"2x Adult, 1x Child"``)."""
    tickets: list[Ticket]
    """The individual ticket lines on the booking."""

    is_canceled: bool
    """Whether the booking has been canceled."""
    is_no_show: bool
    """Whether the booking was marked a no-show."""
    is_checked_in: bool
    """Whether any guest on the booking has been checked in."""
    is_returned: bool
    """Whether the booking's rental has been returned."""

    purchased_at: str | None
    """Purchase time in the account's local zone (ISO datetime), or ``None``."""
    purchased_at_utc: str | None
    """Purchase time in UTC (ISO datetime), or ``None``."""
    starts_at: str | None
    """Activity start in the account's local zone (ISO datetime), or ``None``."""
    starts_at_utc: str | None
    """Activity start in UTC (ISO datetime), or ``None``."""
    ends_at: str | None
    """Activity end in the account's local zone (ISO datetime), or ``None``."""
    ends_at_utc: str | None
    """Activity end in UTC (ISO datetime), or ``None``."""
    duration_min: int
    """Activity duration in minutes (0 when start/end are unknown)."""
    availability_time_id: str | None
    """The availability time id for the booked slot, or ``None``."""

    portal_url: str | None
    """Customer booking-portal URL, or ``None`` (never requested without
    ``full_customer_access``)."""
    notes: str
    """Operator notes on the booking (``""`` when none)."""
    custom_status: str | None
    """Operator-facing custom status set on the booking (via
    ``BookingService.update_custom_status``), or ``None`` when none is set."""

    value_display: str
    """Total booking value, human-formatted (e.g. ``"$75.00"``). ``""`` if absent."""
    value_amount: str
    """Total booking value as a numeric string. ``""`` if absent."""

    outstanding_balance_amount: str
    """Outstanding balance as a numeric string. ``""`` if absent."""
    outstanding_balance_display: str
    """Outstanding balance, human-formatted. ``""`` if absent."""

    promo_codes: list[str]
    """Redemption codes of promo codes applied to the order."""
    tips: list[Price]
    """Tips left on the booking."""

    convenience_fee: Price | None
    """Convenience fee — only populated when ``include_price_breakdown`` is requested."""
    deposit: Price | None
    """Deposit — only populated when ``include_price_breakdown`` is requested."""
    discount: Price | None
    """Discount — only populated when ``include_price_breakdown`` is requested."""
    discounted_price: Price | None
    """Price after discount — only populated when ``include_price_breakdown`` is requested."""
    fees: Price | None
    """Fees — only populated when ``include_price_breakdown`` is requested."""
    flat_partner_fee: Price | None
    """Flat partner fee — only populated when ``include_price_breakdown`` is requested."""
    price: Price | None
    """Base price — only populated when ``include_price_breakdown`` is requested."""
    retail_price: Price | None
    """Retail price — only populated when ``include_price_breakdown`` is requested."""
    taxes: Price | None
    """Taxes — only populated when ``include_price_breakdown`` is requested."""
    tips_breakdown: Price | None
    """Tips total in the breakdown — only populated when ``include_price_breakdown``
    is requested."""

    resources: list[Resource]
    """Pool-level resource usage (quantity per resource pool)."""
    resource_pool_assignments: list[ResourcePoolAssignment]
    """Concrete resources assigned to the booking."""

    reseller_id: str | None
    """Reseller channel id, or ``None`` for a direct booking."""
    reseller_name: str | None
    """Reseller display name (channel name, plus ``" - <agent>"`` when an agent is
    set), or ``None`` for a direct booking."""

    order_id: str
    """The order id this booking belongs to. ``""`` if absent."""

    peek_pro_booking_deep_link: str
    """Deep link into the Peek Pro app for this booking, derived from the order id
    and booking id. ``""`` when either id is absent."""

    custom_question_answers: list[CustomQuestionAnswer]
    """Custom question answers captured at the booking level."""
    custom_guest_question_answers: list[CustomQuestionAnswer]
    """Custom question answers captured per guest/ticket."""

    guests: list[Guest] | None
    """Guests — only populated when ``include_guests`` is requested."""


BookingSearchBy = Literal["purchaseDate", "activityDate"]
"""How to interpret the start/end range when searching bookings."""

NoteMode = Literal["append", "overwrite"]
"""How an appended note should be applied."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingReadOptions:
    """Options shared by booking reads."""

    include_guests: bool | None = None
    """Include guests in the result."""
    include_price_breakdown: bool | None = None
    """Include the price breakdown fields."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingTimeRangeSearch(BookingReadOptions):
    """Parameters for searching bookings by a time range."""

    start: str
    """Range start (ISO datetime)."""
    end: str
    """Range end (ISO datetime)."""
    search_by: BookingSearchBy | None = None
    """Whether the range matches purchase date or activity date. Default: ``"purchaseDate"``."""
    product_id: str | None = None
    """Restrict to a product/activity id."""
    email: str | None = None
    """Filter by primary guest email."""
    search_string: str | None = None
    """Free-text search string."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBookingTicket:
    """A requested ticket (resource option) and quantity for a new booking."""

    resource_option_id: str
    """The resource option to book — this is the ``ProductTicket.id`` from the
    activity's ``tickets`` (also reported per slot by
    ``AvailabilityService.get_availability_times``)."""
    quantity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBookingGuest:
    """Guest details for a new booking."""

    name: str
    email: str | None = None
    phone: str | None = None
    postal_code: str | None = None
    country: str | None = None
    optin_marketing: bool | None = None
    optin_sms: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomQuestionAnswerInput:
    """An answer to one of an activity's custom questions, supplied when creating
    a booking. The question is identified by id **or** text, and the value is
    resolved against the question's type at create time (see
    :attr:`CreateBookingInput.custom_question_answers`)."""

    question_id_or_text: str
    """The question to answer — either its id (``cq_…``) or its question text. Text
    is matched leniently (lowercased, non-alphanumerics stripped); it must match
    exactly one question or creation fails."""
    value: str
    """The answer. How it is interpreted depends on the question's type:

    - **checkbox** — ``yes``/``no``/``true``/``false`` (case-insensitive).
    - **text** — used verbatim.
    - **select-one / location** — an option id (``cqao_…``) or the option's label,
      matched leniently the same way as :attr:`question_id_or_text`.

    For **location** questions you only select the option — Peek holds each
    option's configured lat/long and applies it, so no coordinates are (or can
    be) supplied here.

    Per-guest questions are **not yet supported**: answering one fails creation.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateBookingInput:
    """Input for creating a booking. IDs must already be resolved — the package
    does not do free-text product/ticket/time matching (that stays in the caller)."""

    activity_id: str
    """Activity (product) id."""
    availability_time_id: str
    """Availability time id for the slot."""
    tickets: list[CreateBookingTicket]
    """Tickets to book (each expanded to ``quantity`` seats)."""
    guest: CreateBookingGuest
    """Primary guest."""
    operator_notes: str | None = None
    """Operator notes to attach."""
    list_price: str | None = None
    """Total list price for the booking, as a positive number string (commas
    allowed — ``"100"``, ``"1,000"``, ``"10.00"``). When set, it is split evenly
    across the booking's tickets (each of the first n-1 tickets gets
    ``floor(total / n)``, the last ticket the remainder) and sent per ticket in
    the activity's currency (falling back to ``"USD"``). Omit to let Peek price
    the tickets from the activity's configured pricing."""
    custom_question_answers: list[CustomQuestionAnswerInput] | None = None
    """Answers to the activity's custom questions. When non-empty, the activity's
    custom questions are fetched and each answer is validated/resolved before
    the booking is created — an unmatched question, ambiguous text/option, or
    invalid checkbox value fails creation before any quote is made."""
    require_required_questions: bool | None = None
    """When ``True``, creation fails if any of the activity's required custom
    questions (per-guest questions excluded) is left unanswered. Because this
    enforces coverage against the activity's questions, it forces custom-question
    validation to run even when ``custom_question_answers`` is empty or omitted.
    Default: ``False``."""
    accept_all_custom_question_ids: bool | None = None
    """When ``True``, a ``custom_question_answers`` entry whose
    ``question_id_or_text`` is a ``cq_…`` id is accepted even if that id is
    **not** among the activity's custom questions — the answer is sent as-is (as
    a text answer). Entries given by question **name** are unaffected: they still
    must match a question, so the activity's questions are fetched only when a
    by-name answer (or ``require_required_questions``) needs them. Default: ``False``."""
    skip_customer_email: bool | None = None
    """Suppress the customer confirmation email. Default: ``False``."""
    parent_order_id: str | None = None
    """Clone the quote from an existing order."""
    mark_as_paid: bool | None = None
    """Mark the booking paid after creation (requires ``idempotency_key``)."""
    mark_as_paid_amount: str | None = None
    """Partial payment amount when marking paid; defaults to the full balance."""
    idempotency_key: str | None = None
    """Idempotency key for the mark-paid charge."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedBooking:
    """The result of creating a booking."""

    order_id: str
    """The order id the new booking belongs to."""
    booking_id: str
    """The new booking's id."""
    display_id: str
    """The new booking's human-facing display id."""
    balance_amount: str
    """Remaining balance as a numeric string."""
    balance_currency: str
    """3-letter uppercase ISO currency code of the balance."""
    balance_formatted: str
    """Balance, human-formatted (e.g. ``"$75.00"``)."""
    transaction_id: str | None = None
    """The charge transaction id — set only when the booking was marked paid."""
