"""Booking operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_booking_service()``.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.errors import PiiAccessDisabledError
from peek_app_utilities.internal.peek.bookings.addon_converter import (
    AddonItem,
    parse_sale_node,
    to_booking_addon,
)
from peek_app_utilities.internal.peek.bookings.addon_queries import (
    ADDON_OPTION_STATUS_CANCELED,
    RESERVATION_STATUS_CONFIRMED,
    SALES_ADDONS_QUERY,
    build_sales_addons_variables,
)
from peek_app_utilities.internal.peek.bookings.booking_converter import from_booking_node
from peek_app_utilities.internal.peek.bookings.booking_guest_converter import (
    from_booking_guests_response,
)
from peek_app_utilities.internal.peek.bookings.booking_queries import (
    AMEND_ORDER_MUTATION,
    APPLY_PAYMENT_TO_ORDER_MUTATION,
    APPLY_REFUND_TO_ORDER_MUTATION,
    BOOKING_PAYMENTS_ON_FILE_QUERY,
    CANCEL_BOOKING_MUTATION,
    CREATE_INVOICE_LINK_MUTATION,
    CREATE_ORDER_FROM_QUOTE_MUTATION,
    CREATE_QUOTE_FROM_ORDER_MUTATION,
    CREATE_QUOTE_V2_MUTATION,
    SEARCH_BY_PURCHASE_DATE,
    UPDATE_BOOKING_CHECKIN_MUTATION,
    UPDATE_OPERATOR_NOTES_MUTATION,
    UPDATE_OPERATOR_STATUS_MUTATION,
    UPDATE_QUOTE_V2_MUTATION,
    build_booking_guests_query,
    build_bookings_listing_query,
    build_bookings_variables,
    normalize_booking_id,
)
from peek_app_utilities.internal.peek.bookings.custom_question_answer import (
    ResolveCustomQuestionOptions,
    is_custom_question_id,
    resolve_custom_question_answers,
    resolved_answer_to_wire,
)
from peek_app_utilities.internal.peek.bookings.list_price import distribute_list_price
from peek_app_utilities.internal.peek.bookings.metadata_converter import (
    filter_meta_data_by_integrator,
    from_booking_meta_data_node,
    to_set_meta_data_result,
)
from peek_app_utilities.internal.peek.bookings.metadata_queries import (
    UPSERT_BOOKING_FIELD_RESPONSES_MUTATION,
    build_booking_meta_data_query,
)
from peek_app_utilities.internal.peek.bookings.payments_on_file_converter import (
    from_payments_on_file_response,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLBody, GraphQLClient
from peek_app_utilities.models.peek.booking import (
    Booking,
    BookingReadOptions,
    BookingTimeRangeSearch,
    CreateBookingInput,
    CreatedBooking,
    Guest,
    NoteMode,
)
from peek_app_utilities.models.peek.booking_addon import (
    BookingAddons,
    BookingAddonsMutationResult,
)
from peek_app_utilities.models.peek.booking_metadata import (
    MetaData,
    SetMetaDataAttachmentInput,
    SetMetaDataGuestInput,
    SetMetaDataResult,
)
from peek_app_utilities.models.peek.booking_payment import (
    BookingPaymentsOnFile,
    InvoiceLinkResult,
    MakePaymentInput,
    MakePaymentResult,
    RefundInput,
    RefundResult,
)
from peek_app_utilities.models.peek.product import ADD_ON_PRODUCT_TYPE

if TYPE_CHECKING:
    from peek_app_utilities.internal.peek.products.product_service import ProductService

DEFAULT_PAGE_SIZE: Final = 50
"""Default page size for cursor-paginated bookings."""
DEFAULT_CANCEL_NOTE: Final = "Canceled"
"""Default note used when cancelling without an explicit reason."""
DEFAULT_CUSTOMER_MESSAGE: Final = "Charge initiated via API"
"""Default customer message attached to a charge."""
DEFAULT_CURRENCY: Final = "USD"
"""Currency used when the activity's own currency can't be resolved."""

NOTE_MODE_APPEND: Final[NoteMode] = "append"
NOTE_MODE_OVERWRITE: Final[NoteMode] = "overwrite"

# Booking/order ids come in two forms: a lowercase db id with `_`
# (`b_abc123` / `o_abc123`) and an uppercase display id with `-`
# (`B-ABC123` / `O-ABC123`). Bookings are prefixed `b`, orders `o`.
_BOOKING_DB_ID_RE: Final = re.compile(r"b_[a-z0-9]+")
_BOOKING_DISPLAY_ID_RE: Final = re.compile(r"B-[A-Z0-9]+")
_ORDER_DB_ID_RE: Final = re.compile(r"o_[a-z0-9]+")
_ORDER_DISPLAY_ID_RE: Final = re.compile(r"O-[A-Z0-9]+")
_PAYMENT_SOURCE_PREFIX: Final = "ps_"
_PAYMENT_ID_PREFIX: Final = "pmt_"
_ALLOWED_PAYMENT_SOURCE_IDS: Final = ("cash/cash", "custom/other", "custom/voucher")
_CURRENCY_CODE_RE: Final = re.compile(r"[A-Z]{3}")
_QUANTITY_RE: Final = re.compile(r"\d+")
_LEADING_FLOAT_RE: Final = re.compile(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")

# Mark-as-paid defaults for a freshly created booking.
_MARK_AS_PAID_SOURCE_ID: Final = "custom/other"
_MARK_AS_PAID_MESSAGE: Final = "Marked as paid"
_DEFAULT_BALANCE_AMOUNT: Final = "0.00"
_DEFAULT_BALANCE_FORMATTED: Final = "$0.00"

# Operation names reported on `PiiAccessDisabledError`.
_OP_GET_PAYMENTS_ON_FILE: Final = "get_payments_on_file"
_OP_MAKE_PAYMENT: Final = "make_payment"
_OP_REFUND: Final = "refund"
_OP_CREATE_INVOICE_LINK: Final = "create_invoice_link"
_OP_ADD_ADDON: Final = "add_addon"
_OP_REMOVE_ADDON: Final = "remove_addon"

ERROR_ADDON_OPTION_ID_REQUIRED: Final = "addonOptionId is required"
ERROR_QUANTITY_INVALID: Final = "quantity must be a positive integer string"
ERROR_INVALID_BOOKING_ID: Final = (
    "bookingId is required and must be a valid booking id, e.g. 'b_abc123' or 'B-ABC123'"
)
ERROR_INVALID_ORDER_ID: Final = (
    "orderId is required and must be a valid order id, e.g. 'o_abc123' or 'O-ABC123'"
)
ERROR_CUSTOM_STATUS_REQUIRED: Final = "customStatus is required and must be a non-empty string"
ERROR_GUESTS_REQUIRED: Final = "at least one guest is required"
ERROR_ATTACHMENTS_REQUIRED: Final = "at least one attachment is required"
ERROR_INSURANCE_PURCHASED_REQUIRED: Final = "insurancePurchased is required and must be a boolean"
ERROR_BOOKING_NOT_FOUND: Final = "Booking not found"
ERROR_MULTIPLE_BOOKINGS_FOUND: Final = "Expected exactly one booking for the provided bookingId"
ERROR_NO_ADDON_OPTION_TO_REMOVE: Final = (
    "No confirmed add-on option matching addonOptionId was found on the booking"
)
ERROR_CREATE_QUOTE_FAILED: Final = "Failed to create quote from order"
ERROR_UPDATE_QUOTE_FAILED: Final = "Failed to update quote with add-on"
ERROR_AMEND_ORDER_FAILED: Final = "Failed to amend order with add-on"
ERROR_ADDON_NOT_FOUND: Final = "Add-on not found for the provided addonOptionId"
ERROR_NO_CANCEL_DATA: Final = "No booking data returned from cancelBooking"
ERROR_PAYMENT_SOURCE_NOT_FOUND: Final = "paymentSourceId not found for this booking"
ERROR_PAYMENT_NOT_FOUND: Final = "paymentId not found for this booking"
ERROR_PAYMENT_FAILED_PREFIX: Final = "Payment failed: "
ERROR_REFUND_FAILED_PREFIX: Final = "Refund failed: "
ERROR_INVOICE_LINK_FAILED: Final = "Failed to create invoice link"
ERROR_CREATE_QUOTE_V2_FAILED: Final = "Failed to create quote"
ERROR_CREATE_ORDER_FAILED: Final = "Failed to create order from quote"
ERROR_ORDER_NO_SALES: Final = "Order created but no sales found"
ERROR_MARK_PAID_FAILED: Final = "Failed to mark booking as paid"
ERROR_PAYMENT_SOURCE_INVALID: Final = (
    "paymentSourceId is required and must start with 'ps_' or be one of "
    "'cash/cash', 'custom/other', 'custom/voucher'"
)
ERROR_PAYMENT_ID_INVALID: Final = "paymentId is required and must start with 'pmt_'"
ERROR_AMOUNT_INVALID: Final = "amount is required and must be a valid number"
ERROR_CURRENCY_INVALID: Final = "currency is required and must be a 3-letter uppercase code"
ERROR_IDEMPOTENCY_KEY_REQUIRED: Final = "idempotencyKey is required"
ERROR_ACTIVITY_ID_REQUIRED: Final = "activityId is required"
ERROR_AVAILABILITY_TIME_ID_REQUIRED: Final = "availabilityTimeId is required"
ERROR_TICKETS_REQUIRED: Final = "at least one ticket is required"
ERROR_TICKET_INVALID: Final = "each ticket requires a resourceOptionId and a positive quantity"
ERROR_GUEST_NAME_REQUIRED: Final = "guest name is required"
ERROR_IDEMPOTENCY_KEY_REQUIRED_FOR_PAID: Final = "idempotencyKey is required when markAsPaid is set"
_ERROR_NON_EMPTY_STRING_SUFFIX: Final = " is required and must be a non-empty string"

# The fixed `fieldName` values the metadata upsert accepts — one per setter.
META_FIELD_GUEST: Final = "guest"
META_FIELD_ATTACHMENT: Final = "attachment"
META_FIELD_MANIFEST_URL: Final = "manifest_url"
META_FIELD_RESERVATION_ID: Final = "reservation_id"
META_FIELD_BOOKING_STATUS: Final = "booking_status"
META_FIELD_ASSIGNED_PRODUCT: Final = "assigned_product"
META_FIELD_ASSIGNED_EMPLOYEE: Final = "assigned_employee"
META_FIELD_INSURANCE_PURCHASED: Final = "insurance_purchased"

WirePayload = dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelBookingResult:
    """Result of cancelling a booking."""

    id: str
    display_id: str
    reservation_status: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingServiceOptions:
    """Tuning options for a :class:`BookingService`."""

    access_options: ResolvedAccessOptions
    """Cross-cutting access options (PII exposure), already resolved."""
    integrator: str
    """Integrator id used to scope ``get_meta_data`` results — only fields whose
    slug starts with ``integrators:<integrator>:`` are returned (set by the access
    service to the install's issuer)."""
    page_size: int | None = None
    """Page size for cursor pagination. Default: 50."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AddAddonInput:
    """Input for adding or removing an add-on on a booking."""

    quantity: str
    """Quantity as a positive integer string."""
    addon_option_id: str | None = None
    """The add-on (item option) id."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _BookingSale:
    """The parsed sales add-ons response for one booking."""

    items: list[AddonItem]
    display_id: str
    order_id: str
    normalized_booking_id: str


def _data(body: GraphQLBody) -> Mapping[str, Any]:
    return body.get("data") or {}


def _sales_edges(body: GraphQLBody) -> list[Mapping[str, Any]]:
    sales = _data(body).get("sales") or {}
    return list(sales.get("edges") or [])


def _has_errors(result: Mapping[str, Any]) -> bool:
    return bool(result.get("errors"))


def _now_iso() -> str:
    """The current UTC time as an ISO-8601 string with millisecond precision and a ``Z``."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class BookingService:
    """Booking reads and operations for one install. Obtain via
    ``PeekAccessService.get_booking_service()``."""

    def __init__(
        self,
        client: GraphQLClient,
        *,
        product_service: ProductService,
        options: BookingServiceOptions,
    ) -> None:
        self._client = client
        self._product_service = product_service
        self._page_size = options.page_size if options.page_size is not None else DEFAULT_PAGE_SIZE
        # Whether customer PII is requested and payment operations are allowed.
        self._full_customer_access = options.access_options.full_customer_access
        # Integrator id scoping `get_meta_data` results.
        self._integrator = options.integrator

    def _assert_pii_enabled(self, operation: str) -> None:
        """Raises :class:`PiiAccessDisabledError` for ``operation`` when this
        service was created without ``full_customer_access`` — used to gate
        payment and booking-modification operations that touch customer financial
        data."""
        if not self._full_customer_access:
            raise PiiAccessDisabledError(operation)

    async def _request(self, query: str, variables: Mapping[str, Any]) -> GraphQLBody:
        return await self._client.request(SALES_ENDPOINT, query, variables)

    def _single_booking_variables(self, booking_id: str) -> dict[str, Any]:
        return build_bookings_variables(
            page_size=self._page_size, after=None, booking_id=normalize_booking_id(booking_id)
        )

    async def get_by_id(
        self, booking_id: str, options: BookingReadOptions | None = None
    ) -> Booking | None:
        """Returns a single booking by id, or ``None`` when not found. The
        ``booking_id`` is normalized internally (lowercased, ``-`` → ``_``), so
        ``B-ABC123`` and ``b_abc123`` resolve to the same booking.

        :raises ValueError: when ``booking_id`` is not a valid booking id (``b_…``/``B-…``)
        """
        assert_booking_id(booking_id)
        include_guests = bool(options and options.include_guests)
        include_price_breakdown = bool(options and options.include_price_breakdown)

        body = await self._request(
            build_bookings_listing_query(
                include_guests, include_price_breakdown, self._full_customer_access
            ),
            self._single_booking_variables(booking_id),
        )
        edges = _sales_edges(body)
        if not edges:
            return None
        return from_booking_node(edges[0].get("node"), include_guests, include_price_breakdown)

    async def search_by_time_range(self, search: BookingTimeRangeSearch) -> list[Booking]:
        """Returns all bookings matching a time range (paginated)."""
        include_guests = bool(search.include_guests)
        include_price_breakdown = bool(search.include_price_breakdown)
        return await self._fetch_paginated(
            build_bookings_listing_query(
                include_guests, include_price_breakdown, self._full_customer_access
            ),
            {
                "start_date_time": search.start,
                "end_date_time": search.end,
                "search_by": search.search_by or SEARCH_BY_PURCHASE_DATE,
                "product_id": search.product_id,
                "email": search.email,
                "search_string": search.search_string,
            },
            include_guests,
            include_price_breakdown,
        )

    async def search_by_timeslot(
        self, timeslot_id: str, options: BookingReadOptions | None = None
    ) -> list[Booking]:
        """Returns all bookings on a timeslot (paginated)."""
        include_guests = bool(options and options.include_guests)
        include_price_breakdown = bool(options and options.include_price_breakdown)
        return await self._fetch_paginated(
            build_bookings_listing_query(
                include_guests, include_price_breakdown, self._full_customer_access
            ),
            {"timeslot_id": timeslot_id},
            include_guests,
            include_price_breakdown,
        )

    async def get_guests(self, booking_id: str) -> list[Guest]:
        """Returns the guests on a booking (primary guest included). Without
        ``full_customer_access`` only ids and participation/opt-in flags are
        populated — the identity fields come back ``None``."""
        assert_booking_id(booking_id)
        body = await self._request(
            build_booking_guests_query(self._full_customer_access),
            self._single_booking_variables(booking_id),
        )
        return from_booking_guests_response(_data(body))

    async def get_meta_data(self, booking_id: str) -> list[MetaData]:
        """Returns a booking's custom-field metadata (its ``fieldResponses``),
        scoped to this service's integrator. Only fields whose slug starts with
        ``integrators:<integrator>:`` are returned, and that prefix is stripped
        from each returned ``slug``. Returns ``[]`` when the booking is not found
        or has no matching fields."""
        assert_booking_id(booking_id)
        body = await self._request(
            build_booking_meta_data_query(self._full_customer_access),
            self._single_booking_variables(booking_id),
        )
        edges = _sales_edges(body)
        if not edges:
            return []
        return filter_meta_data_by_integrator(
            from_booking_meta_data_node(edges[0].get("node")), self._integrator
        )

    async def set_meta_data_guest(
        self, booking_id: str, guests: Sequence[SetMetaDataGuestInput]
    ) -> SetMetaDataResult:
        """Sets the booking's ``guest`` metadata field. Each guest requires a
        ``name`` and ``email``; ``date_of_birth``/``waiver_signed``/``notes`` are optional."""
        if not guests:
            raise ValueError(ERROR_GUESTS_REQUIRED)
        built: list[WirePayload] = []
        for guest in guests:
            assert_non_empty_string(guest.name, "guest name")
            assert_non_empty_string(guest.email, "guest email")
            out: WirePayload = {"name": guest.name, "email": guest.email}
            if guest.date_of_birth is not None:
                out["dateOfBirth"] = guest.date_of_birth
            if guest.waiver_signed is not None:
                out["waiverSigned"] = guest.waiver_signed
            if guest.notes is not None:
                out["notes"] = guest.notes
            built.append(out)
        return await self._upsert_field_response(
            booking_id, {"fieldName": META_FIELD_GUEST, "guests": built}
        )

    async def set_meta_data_attachment(
        self, booking_id: str, attachments: Sequence[SetMetaDataAttachmentInput]
    ) -> SetMetaDataResult:
        """Sets the booking's ``attachment`` metadata field. Each attachment
        requires a ``name`` and ``attachment_url``."""
        if not attachments:
            raise ValueError(ERROR_ATTACHMENTS_REQUIRED)
        built: list[WirePayload] = []
        for attachment in attachments:
            assert_non_empty_string(attachment.name, "attachment name")
            assert_non_empty_string(attachment.attachment_url, "attachment attachmentUrl")
            built.append({"name": attachment.name, "attachmentUrl": attachment.attachment_url})
        return await self._upsert_field_response(
            booking_id, {"fieldName": META_FIELD_ATTACHMENT, "attachments": built}
        )

    async def set_meta_data_manifest_url(self, booking_id: str, url: str) -> SetMetaDataResult:
        """Sets the booking's ``manifest_url`` metadata field."""
        assert_non_empty_string(url, "url")
        return await self._upsert_field_response(
            booking_id, {"fieldName": META_FIELD_MANIFEST_URL, "url": url}
        )

    async def set_meta_data_reservation_id(
        self, booking_id: str, reservation_id: str
    ) -> SetMetaDataResult:
        """Sets the booking's ``reservation_id`` metadata field."""
        return await self._set_short_text_field(
            booking_id, META_FIELD_RESERVATION_ID, reservation_id, "reservationId"
        )

    async def set_meta_data_booking_status(self, booking_id: str, status: str) -> SetMetaDataResult:
        """Sets the booking's ``booking_status`` metadata field."""
        return await self._set_short_text_field(
            booking_id, META_FIELD_BOOKING_STATUS, status, "status"
        )

    async def set_meta_data_assigned_product(
        self, booking_id: str, product_name: str
    ) -> SetMetaDataResult:
        """Sets the booking's ``assigned_product`` metadata field."""
        return await self._set_short_text_field(
            booking_id, META_FIELD_ASSIGNED_PRODUCT, product_name, "productName"
        )

    async def set_meta_data_assigned_employee(
        self, booking_id: str, employee_name: str
    ) -> SetMetaDataResult:
        """Sets the booking's ``assigned_employee`` metadata field."""
        return await self._set_short_text_field(
            booking_id, META_FIELD_ASSIGNED_EMPLOYEE, employee_name, "employeeName"
        )

    async def set_meta_data_insurance_purchased(
        self, booking_id: str, insurance_purchased: bool
    ) -> SetMetaDataResult:
        """Sets the booking's ``insurance_purchased`` metadata field."""
        if not isinstance(insurance_purchased, bool):
            raise ValueError(ERROR_INSURANCE_PURCHASED_REQUIRED)
        return await self._upsert_field_response(
            booking_id,
            {"fieldName": META_FIELD_INSURANCE_PURCHASED, "boolean": insurance_purchased},
        )

    async def _set_short_text_field(
        self, booking_id: str, field_name: str, value: str, arg_name: str
    ) -> SetMetaDataResult:
        """Validates a non-empty ``shortText`` value and upserts it under ``field_name``."""
        assert_non_empty_string(value, arg_name)
        return await self._upsert_field_response(
            booking_id, {"fieldName": field_name, "shortText": value}
        )

    async def _upsert_field_response(
        self, booking_id: str, field_response: WirePayload
    ) -> SetMetaDataResult:
        """Validates the booking id and upserts a single field response (scoped to
        this service's integrator), mapping the result union into a
        :class:`SetMetaDataResult`."""
        assert_booking_id(booking_id)
        normalized = normalize_booking_id(booking_id)
        body = await self._request(
            UPSERT_BOOKING_FIELD_RESPONSES_MUTATION,
            {
                "input": {
                    "bookingId": normalized,
                    "integrator": self._integrator,
                    "fieldResponses": [field_response],
                }
            },
        )
        return to_set_meta_data_result(_data(body).get("upsertBookingFieldResponses"), normalized)

    async def get_payments_on_file(self, booking_id: str) -> BookingPaymentsOnFile | None:
        """Returns the payments on file for a booking, or ``None`` when not found.

        :raises PiiAccessDisabledError: when the access service was created
            without ``full_customer_access`` (raised before any request)
        """
        self._assert_pii_enabled(_OP_GET_PAYMENTS_ON_FILE)
        assert_booking_id(booking_id)
        normalized = normalize_booking_id(booking_id)
        body = await self._request(
            BOOKING_PAYMENTS_ON_FILE_QUERY, self._single_booking_variables(normalized)
        )
        return from_payments_on_file_response(_data(body), normalized)

    async def append_note(
        self, booking_id: str, note: str, mode: NoteMode = NOTE_MODE_APPEND
    ) -> Booking | None:
        """Appends to (or overwrites) a booking's operator notes. Returns the
        updated booking, or ``None`` when the booking is not found."""
        assert_booking_id(booking_id)
        normalized = normalize_booking_id(booking_id)
        booking = await self.get_by_id(normalized)
        if booking is None:
            return None

        new_note = (
            note if mode == NOTE_MODE_OVERWRITE or not booking.notes else f"{booking.notes}\n{note}"
        )

        await self._request(
            UPDATE_OPERATOR_NOTES_MUTATION, {"input": {"id": normalized, "operatorNotes": new_note}}
        )
        return replace(booking, notes=new_note)

    async def set_checkin_status(self, booking_id: str, checked_in: bool) -> Booking | None:
        """Sets a booking's check-in status. Returns the refreshed booking, or
        ``None`` when not found."""
        assert_booking_id(booking_id)
        normalized = normalize_booking_id(booking_id)
        checked_in_at = _now_iso() if checked_in else None

        await self._request(
            UPDATE_BOOKING_CHECKIN_MUTATION,
            {"input": {"id": normalized, "checkedInAt": checked_in_at}},
        )
        return await self.get_by_id(normalized)

    async def update_custom_status(self, booking_id: str, custom_status: str) -> bool:
        """Sets a booking's operator-facing custom status. Returns ``True`` when
        the API confirms the stored ``operatorStatus`` equals the requested
        ``custom_status``, ``False`` otherwise.

        :raises ValueError: when ``booking_id`` is not a valid booking id
            (``b_…``/``B-…``) or when ``custom_status`` is not a non-empty string
        """
        assert_booking_id(booking_id)
        assert_custom_status(custom_status)
        normalized = normalize_booking_id(booking_id)

        body = await self._request(
            UPDATE_OPERATOR_STATUS_MUTATION,
            {"input": {"id": normalized, "operatorStatus": custom_status}},
        )
        update = _data(body).get("updateOperatorStatusForBooking") or {}
        booking = update.get("booking") or {}
        return bool(booking.get("operatorStatus") == custom_status)

    async def cancel(
        self, booking_id: str, notes: str = DEFAULT_CANCEL_NOTE
    ) -> CancelBookingResult:
        """Cancels a booking and returns its id/display id/status."""
        assert_booking_id(booking_id)
        body = await self._request(
            CANCEL_BOOKING_MUTATION,
            {"input": {"bookingId": normalize_booking_id(booking_id), "notes": notes}},
        )
        booking = (_data(body).get("cancelBooking") or {}).get("booking")
        if not booking:
            raise ValueError(ERROR_NO_CANCEL_DATA)
        return CancelBookingResult(
            id=booking.get("id") or "",
            display_id=booking.get("displayId") or "",
            reservation_status=booking.get("reservationStatus") or "",
        )

    async def make_payment(self, payment: MakePaymentInput) -> MakePaymentResult:
        """Charges a booking. Validates input, resolves the order + payment source
        via payments-on-file, then applies the payment. The ``idempotency_key`` is
        passed through to Peek.

        :raises PiiAccessDisabledError: without ``full_customer_access`` (before any request)
        :raises ValueError: when ``payment_source_id`` is missing or not a ``ps_…``
            id / one of ``cash/cash``, ``custom/other``, ``custom/voucher``; when
            ``amount`` is not a valid number; when ``currency`` is not a 3-letter
            uppercase code; when ``idempotency_key`` is empty; when ``booking_id``
            is not a valid booking id; when the booking or payment source is not
            found; or when the charge fails
        """
        self._assert_pii_enabled(_OP_MAKE_PAYMENT)
        _validate_payment_input(payment)
        normalized = normalize_booking_id(payment.booking_id)

        on_file = await self.get_payments_on_file(normalized)
        if on_file is None:
            raise ValueError(ERROR_BOOKING_NOT_FOUND)
        if not any(source.id == payment.payment_source_id for source in on_file.payments_on_file):
            raise ValueError(ERROR_PAYMENT_SOURCE_NOT_FOUND)

        customer_message = (
            f"{DEFAULT_CUSTOMER_MESSAGE} ({payment.customer_message})"
            if payment.customer_message
            else DEFAULT_CUSTOMER_MESSAGE
        )

        body = await self._request(
            APPLY_PAYMENT_TO_ORDER_MUTATION,
            {
                "input": {
                    "amount": {"amount": payment.amount, "currency": payment.currency},
                    "orderId": on_file.order_id,
                    "paymentSourceId": payment.payment_source_id,
                    "idempotencyKey": payment.idempotency_key,
                    "customerMessage": customer_message,
                    "scopedTo": [normalized],
                }
            },
        )

        result = _data(body).get("applyPaymentToOrder") or {}
        if _has_errors(result):
            raise ValueError(f"{ERROR_PAYMENT_FAILED_PREFIX}{result['errors'][0].get('detail')}")

        return MakePaymentResult(
            transaction_id=result.get("transactionId") or "",
            booking_id=normalized,
            order_id=on_file.order_id,
            amount=payment.amount,
            currency=payment.currency,
            payment_source_id=payment.payment_source_id,
        )

    async def refund(self, refund: RefundInput) -> RefundResult:
        """Refunds a booking payment. Validates input, resolves the order + payment
        via payments-on-file, then applies the refund.

        :raises PiiAccessDisabledError: without ``full_customer_access`` (before any request)
        :raises ValueError: on invalid input, an unknown booking/payment, or a failed refund
        """
        self._assert_pii_enabled(_OP_REFUND)
        _validate_refund_input(refund)
        normalized = normalize_booking_id(refund.booking_id)

        on_file = await self.get_payments_on_file(normalized)
        if on_file is None:
            raise ValueError(ERROR_BOOKING_NOT_FOUND)
        payment_exists = any(
            payment.id == refund.payment_id
            for source in on_file.payments_on_file
            for payment in source.payments or []
        )
        if not payment_exists:
            raise ValueError(ERROR_PAYMENT_NOT_FOUND)

        body = await self._request(
            APPLY_REFUND_TO_ORDER_MUTATION,
            {
                "input": {
                    "amount": {"amount": refund.amount, "currency": refund.currency},
                    "orderId": on_file.order_id,
                    "paymentId": refund.payment_id,
                    "idempotencyKey": refund.idempotency_key,
                    "scopedTo": [normalized],
                }
            },
        )

        result = _data(body).get("applyRefundToOrder") or {}
        if _has_errors(result):
            raise ValueError(f"{ERROR_REFUND_FAILED_PREFIX}{result['errors'][0].get('detail')}")

        return RefundResult(
            transaction_id=result.get("transactionId") or "",
            booking_id=normalized,
            order_id=on_file.order_id,
            amount=refund.amount,
            currency=refund.currency,
            payment_id=refund.payment_id,
        )

    async def create_invoice_link(self, booking_id: str) -> InvoiceLinkResult:
        """Creates an invoice link for a booking's order.

        :raises PiiAccessDisabledError: without ``full_customer_access`` (before any request)
        :raises ValueError: on an invalid id, an unknown booking, or when no URL is returned
        """
        self._assert_pii_enabled(_OP_CREATE_INVOICE_LINK)
        assert_booking_id(booking_id)
        normalized = normalize_booking_id(booking_id)

        booking = await self.get_by_id(normalized)
        if booking is None or not booking.order_id:
            raise ValueError(ERROR_BOOKING_NOT_FOUND)
        order_id = normalize_booking_id(booking.order_id)

        body = await self._request(CREATE_INVOICE_LINK_MUTATION, {"input": {"orderId": order_id}})

        invoice_link = (_data(body).get("createInvoiceLink") or {}).get("invoiceLink") or {}
        url = invoice_link.get("url")
        if not url:
            raise ValueError(ERROR_INVOICE_LINK_FAILED)
        return InvoiceLinkResult(booking_id=normalized, order_id=order_id, invoice_link=url)

    async def list_addons(self, booking_id: str) -> BookingAddons:
        """Returns the add-ons on a booking, grouped by add-on item (clean model)."""
        assert_booking_id(booking_id)
        sale = await self._fetch_booking_sale(booking_id)

        addons = [addon for addon in map(to_booking_addon, sale.items) if addon is not None]
        first = sale.items[0] if sale.items else None

        return BookingAddons(
            booking_id=(first.booking_id if first else "") or sale.normalized_booking_id,
            display_id=(first.display_id if first else "") or sale.display_id,
            order_id=(first.order_id if first else "") or sale.order_id,
            addons=addons,
        )

    async def add_addon(self, booking_id: str, addon: AddAddonInput) -> BookingAddonsMutationResult:
        """Adds an add-on to a booking via ``createQuoteFromOrder`` →
        ``updateQuoteV2`` → ``amendOrder``. Lists the booking's add-ons first to
        derive the order id and reuse an existing add-on refid; resolves the
        add-on's parent item via the product service. Returns the booking's
        add-ons after the change.

        ``quantity`` is a **positive-integer string** (``"1"``, ``"2"``, …); one
        add-on item option is created per unit. ``addon_option_id`` is the
        add-on's item-option id (a ticket id on an ``ADD_ON_PRODUCT_TYPE`` product
        from ``ProductService.get_all_products``).

        :raises PiiAccessDisabledError: without ``full_customer_access`` (before any request)
        :raises ValueError: when ``addon_option_id`` is missing, ``quantity`` is
            not a positive-integer string, the add-on is not found on any product,
            or any of the underlying quote/order mutations fail
        """
        self._assert_pii_enabled(_OP_ADD_ADDON)
        assert_booking_id(booking_id)
        addon_option_id, quantity = _parse_addon_input(addon)

        # List the booking's existing add-ons first — this yields the order id (no
        # separate lookup) and lets us reuse an existing add-on refid instead of
        # minting a new one. Resolve the add-on's parent item in parallel.
        sale, parent_item_id = await asyncio.gather(
            self._fetch_booking_sale(booking_id), self._resolve_parent_item_id(addon_option_id)
        )

        normalized_order_id = normalize_booking_id(sale.order_id)

        # Reuse the bookingQuote item refid when this parent item is already on the
        # booking under a non-canceled add-on; otherwise mint a fresh refid.
        existing_item_refid = next(
            (
                opt.item_refid
                for item in sale.items
                if item.booking_quote_reservation_status != ADDON_OPTION_STATUS_CANCELED
                for opt in item.addon_item_options
                if opt.item_id == parent_item_id
            ),
            None,
        )
        addon_refid = existing_item_refid or str(uuid4())

        # Step 1 — create a quote from the order.
        quote_id, sale_quote_refid = await self._create_quote_from_order_or_raise(
            normalized_order_id
        )
        if not sale_quote_refid:
            raise ValueError(ERROR_CREATE_QUOTE_FAILED)

        # Step 2 — add the add-on to the quote (one new itemOption per unit).
        item_options = [
            {
                "itemOptionId": addon_option_id,
                "reservationStatus": RESERVATION_STATUS_CONFIRMED,
                "refid": str(uuid4()),
            }
            for _ in range(quantity)
        ]
        await self._update_quote_or_raise(
            quote_id,
            {
                "bookingQuotes": [
                    {
                        "refid": sale_quote_refid,
                        "addons": [
                            {
                                "itemOptions": item_options,
                                "itemId": parent_item_id,
                                "reservationStatus": RESERVATION_STATUS_CONFIRMED,
                                "refid": addon_refid,
                            }
                        ],
                        "reservationStatus": RESERVATION_STATUS_CONFIRMED,
                    }
                ]
            },
        )

        # Step 3 — amend the order with the updated quote.
        await self._amend_order_or_raise(quote_id, normalized_order_id)

        return BookingAddonsMutationResult(
            updated_booking_addons=await self.list_addons(booking_id)
        )

    async def remove_addon(
        self, booking_id: str, addon: AddAddonInput
    ) -> BookingAddonsMutationResult:
        """Removes (cancels) add-on options from a booking. Lists the booking's
        add-ons first to get the order id and the existing item/option refids,
        then issues the same three mutations as :meth:`add_addon` but with
        cancellation variables. Returns the booking's add-ons after the change.

        :raises PiiAccessDisabledError: without ``full_customer_access`` (before any request)
        :raises ValueError: on invalid input, when no confirmed matching option is
            on the booking, or when a mutation fails
        """
        self._assert_pii_enabled(_OP_REMOVE_ADDON)
        assert_booking_id(booking_id)
        addon_option_id, quantity = _parse_addon_input(addon)

        sale = await self._fetch_booking_sale(booking_id)
        normalized_order_id = normalize_booking_id(sale.order_id)

        booking_quotes, canceled_count = build_cancellation(sale.items, addon_option_id, quantity)
        if canceled_count == 0:
            raise ValueError(ERROR_NO_ADDON_OPTION_TO_REMOVE)

        # Step 1 — create a quote from the order (only the quote id is needed; the
        # refids come from the existing booking, not the quote).
        quote_id, _ = await self._create_quote_from_order_or_raise(normalized_order_id)

        # Step 2 — update the quote, canceling the selected options.
        await self._update_quote_or_raise(quote_id, {"bookingQuotes": booking_quotes})

        # Step 3 — amend the order.
        await self._amend_order_or_raise(quote_id, normalized_order_id)

        return BookingAddonsMutationResult(
            updated_booking_addons=await self.list_addons(booking_id)
        )

    async def _fetch_booking_sale(self, booking_id: str) -> _BookingSale:
        """Runs the sales add-ons query for a booking, validates that exactly one
        booking matched, and parses the node into the internal model."""
        body = await self._request(SALES_ADDONS_QUERY, build_sales_addons_variables(booking_id))

        edges = _sales_edges(body)
        if not edges:
            raise ValueError(ERROR_BOOKING_NOT_FOUND)
        if len(edges) > 1:
            raise ValueError(ERROR_MULTIPLE_BOOKINGS_FOUND)

        node: Mapping[str, Any] = edges[0].get("node") or {}
        return _BookingSale(
            items=parse_sale_node(node),
            display_id=node.get("displayId") or "",
            order_id=(node.get("order") or {}).get("id") or "",
            normalized_booking_id=node.get("id") or "",
        )

    async def _create_quote_from_order_or_raise(self, normalized_order_id: str) -> tuple[str, str]:
        """Runs ``createQuoteFromOrder`` and validates the response, returning the
        new quote id and the first sale quote refid (empty string when absent)."""
        body = await self._request(
            CREATE_QUOTE_FROM_ORDER_MUTATION,
            {"input": {"orderId": normalized_order_id, "quoteInput": {}}},
        )
        created = _data(body).get("createQuoteFromOrder") or {}
        quote = created.get("quote") or {}
        if _has_errors(created) or not quote.get("id"):
            raise ValueError(ERROR_CREATE_QUOTE_FAILED)
        sale_quotes = quote.get("saleQuotes") or []
        sale_quote_refid = (sale_quotes[0].get("refid") if sale_quotes else None) or ""
        return str(quote["id"]), str(sale_quote_refid)

    async def _update_quote_or_raise(self, quote_id: str, quote_input: WirePayload) -> None:
        """Runs ``updateQuoteV2`` with the given quote input and validates the response."""
        body = await self._request(
            UPDATE_QUOTE_V2_MUTATION, {"input": {"quoteId": quote_id, "quoteInput": quote_input}}
        )
        updated = _data(body).get("updateQuoteV2") or {}
        if _has_errors(updated) or not updated.get("quote"):
            raise ValueError(ERROR_UPDATE_QUOTE_FAILED)

    async def _amend_order_or_raise(self, quote_id: str, normalized_order_id: str) -> None:
        """Runs ``amendOrder`` and validates the response."""
        body = await self._request(
            AMEND_ORDER_MUTATION, {"input": {"quoteId": quote_id, "orderId": normalized_order_id}}
        )
        amended = _data(body).get("amendOrder") or {}
        if _has_errors(amended) or not amended.get("order"):
            raise ValueError(ERROR_AMEND_ORDER_FAILED)

    async def create(self, booking: CreateBookingInput) -> CreatedBooking:
        """Creates a booking via ``createQuoteV2`` → ``createOrderFromQuote``,
        optionally marking it paid. IDs must be pre-resolved (no free-text
        matching) — resolve ``activity_id`` + ticket ``resource_option_id`` s from
        ``ProductService`` and ``availability_time_id`` from
        ``AvailabilityService.get_availability_times``.

        :raises ValueError: when ``activity_id``, ``availability_time_id``, a
            ticket ``resource_option_id``/positive ``quantity``, or the guest
            ``name`` is missing; when ``mark_as_paid`` is set without an
            ``idempotency_key``; when ``list_price`` is malformed; when
            ``require_required_questions`` is set and a required custom question
            is left unanswered; or when the quote/order mutations fail
        """
        _validate_create_input(booking)

        # Split the optional list price across the tickets up front — a malformed
        # amount raises here, before any quote exists.
        ticket_count = sum(ticket.quantity for ticket in booking.tickets)
        list_price_amounts = (
            None
            if booking.list_price is None
            else distribute_list_price(booking.list_price, ticket_count)
        )

        # Resolve custom-question answers (and, when a list price is set, the
        # activity's currency) before anything is created: a bad answer fails here
        # rather than after a quote exists, and the two reads run in parallel.
        question_answers, currency = await asyncio.gather(
            self._build_question_answers(booking),
            self._resolve_activity_currency(booking.activity_id)
            if list_price_amounts
            else _resolved(""),
        )

        tickets: list[WirePayload] = []
        for ticket in booking.tickets:
            for _ in range(ticket.quantity):
                seat: WirePayload = {
                    "resourceOptionId": ticket.resource_option_id,
                    "reservationStatus": RESERVATION_STATUS_CONFIRMED,
                    "refid": str(uuid4()),
                }
                if list_price_amounts:
                    seat["price"] = {
                        "amount": list_price_amounts[len(tickets)],
                        "currency": currency,
                    }
                tickets.append(seat)

        guest = booking.guest
        booking_quote: WirePayload = {
            "tickets": tickets,
            "activityId": booking.activity_id,
            "availabilityTimeId": booking.availability_time_id,
            "refid": str(uuid4()),
            "skipCustomerEmail": bool(booking.skip_customer_email),
            "guest": {
                "name": guest.name,
                "email": guest.email,
                "phone": guest.phone,
                "optinMarketing": bool(guest.optin_marketing),
                "optinSms": bool(guest.optin_sms),
                "postalCode": guest.postal_code,
                "country": guest.country,
            },
        }
        if booking.operator_notes:
            booking_quote["operatorNotes"] = booking.operator_notes
        if question_answers:
            booking_quote["questionAnswers"] = question_answers

        quote_input: WirePayload = {"bookingQuotes": [booking_quote]}
        if booking.parent_order_id:
            quote_input["source"] = {"clonedFromId": booking.parent_order_id}

        # Step 1 — create the quote.
        quote_body = await self._request(
            CREATE_QUOTE_V2_MUTATION, {"input": {"quoteInput": quote_input}}
        )
        quote_result = _data(quote_body).get("createQuoteV2") or {}
        quote = quote_result.get("quote") or {}
        if _has_errors(quote_result) or not quote.get("id"):
            raise ValueError(ERROR_CREATE_QUOTE_V2_FAILED)
        quote_id = quote["id"]

        # Step 2 — create the order from the quote.
        order_body = await self._request(
            CREATE_ORDER_FROM_QUOTE_MUTATION, {"input": {"quoteId": quote_id}}
        )
        order_result = _data(order_body).get("createOrderFromQuote") or {}
        if _has_errors(order_result):
            raise ValueError(ERROR_CREATE_ORDER_FAILED)
        order = order_result.get("order") or {}
        sales = order.get("sales") or []
        if not order or not sales:
            raise ValueError(ERROR_ORDER_NO_SALES)
        sale = sales[0]
        balance_total = (sale.get("balance") or {}).get("total") or {}

        created = CreatedBooking(
            order_id=order.get("id") or "",
            booking_id=sale.get("id") or "",
            display_id=sale.get("displayId") or "",
            balance_amount=balance_total.get("amount") or _DEFAULT_BALANCE_AMOUNT,
            balance_currency=balance_total.get("currency") or DEFAULT_CURRENCY,
            balance_formatted=balance_total.get("formatted") or _DEFAULT_BALANCE_FORMATTED,
        )

        # Step 3 — optionally mark the booking paid.
        if booking.mark_as_paid:
            transaction_id = await self._mark_created_booking_paid(created, booking)
            created = replace(created, transaction_id=transaction_id)

        return created

    async def _build_question_answers(
        self, booking: CreateBookingInput
    ) -> list[WirePayload] | None:
        """Resolves the input's custom-question answers into the quote's
        ``questionAnswers`` payload (each tagged with a fresh ``refid``), or
        ``None`` when none were supplied. Fetches the activity's custom questions
        to validate against; raises on the first unmatched/ambiguous/invalid
        answer. When ``accept_all_custom_question_ids`` is set the fetch is skipped
        if every answer is given by id (a by-name answer still needs the list to
        resolve)."""
        answers = booking.custom_question_answers or []
        require_required = bool(booking.require_required_questions)
        accept_all_ids = bool(booking.accept_all_custom_question_ids)
        # Nothing to resolve and no required-coverage check to enforce — skip the
        # questions fetch entirely.
        if not answers and not require_required:
            return None
        # When accepting all ids and not enforcing required-question coverage, the
        # activity's questions are only needed to resolve by-name answers — every
        # by-id answer is accepted as-is. Skip the fetch when no answer needs it.
        needs_questions = (
            not accept_all_ids
            or require_required
            or any(not is_custom_question_id(answer.question_id_or_text) for answer in answers)
        )
        questions = (
            await self._product_service.get_custom_questions(booking.activity_id)
            if needs_questions
            else []
        )
        resolved = resolve_custom_question_answers(
            answers,
            questions,
            ResolveCustomQuestionOptions(
                require_required=require_required, accept_all_ids=accept_all_ids
            ),
        )
        if not resolved:
            return None
        return [{**resolved_answer_to_wire(answer), "refid": str(uuid4())} for answer in resolved]

    async def _mark_created_booking_paid(
        self, created: CreatedBooking, booking: CreateBookingInput
    ) -> str:
        parsed_partial = _parse_float(booking.mark_as_paid_amount)
        amount = (
            f"{parsed_partial:.2f}"
            if not math.isnan(parsed_partial) and parsed_partial > 0
            else created.balance_amount
        )

        body = await self._request(
            APPLY_PAYMENT_TO_ORDER_MUTATION,
            {
                "input": {
                    "amount": {"amount": amount, "currency": created.balance_currency},
                    "orderId": created.order_id,
                    "paymentSourceId": _MARK_AS_PAID_SOURCE_ID,
                    "idempotencyKey": booking.idempotency_key,
                    "customerMessage": _MARK_AS_PAID_MESSAGE,
                    "scopedTo": [created.booking_id],
                }
            },
        )

        result = _data(body).get("applyPaymentToOrder") or {}
        transaction_id = result.get("transactionId")
        if _has_errors(result) or not transaction_id:
            raise ValueError(ERROR_MARK_PAID_FAILED)
        return str(transaction_id)

    async def _resolve_activity_currency(self, activity_id: str) -> str:
        """Resolves an activity's ISO currency via the product service, falling
        back to :data:`DEFAULT_CURRENCY` when the activity (or its currency) can't
        be found."""
        products = await self._product_service.get_all_products()
        match = next((p for p in products if p.product_id == activity_id), None)
        return (match.currency if match else "") or DEFAULT_CURRENCY

    async def _resolve_parent_item_id(self, addon_option_id: str) -> str:
        """Finds the parent item id of an add-on by matching its option id."""
        products = await self._product_service.get_all_products()
        matched = next(
            (
                p
                for p in products
                if p.type == ADD_ON_PRODUCT_TYPE
                and any(ticket.id == addon_option_id for ticket in p.tickets)
            ),
            None,
        )
        if matched is None:
            raise ValueError(ERROR_ADDON_NOT_FOUND)
        return matched.product_id

    async def _fetch_paginated(
        self,
        query: str,
        base_params: Mapping[str, Any],
        include_guests: bool,
        include_price_breakdown: bool,
    ) -> list[Booking]:
        bookings: list[Booking] = []
        after: str | None = None

        # Cursor pagination is inherently sequential: each page yields the next cursor.
        while True:
            body = await self._request(
                query,
                build_bookings_variables(**base_params, page_size=self._page_size, after=after),
            )
            sales = _data(body).get("sales") or {}
            for edge in sales.get("edges") or []:
                bookings.append(
                    from_booking_node(edge.get("node"), include_guests, include_price_breakdown)
                )

            page_info = sales.get("pageInfo") or {}
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                after = page_info["endCursor"]
            else:
                break

        return bookings


async def _resolved(value: str) -> str:
    """An already-resolved awaitable (the ``Promise.resolve`` analogue for ``gather``)."""
    return value


def _parse_float(value: str | None) -> float:
    """``parseFloat`` semantics: the leading numeric prefix, or ``NaN``."""
    if not value:
        return math.nan
    match = _LEADING_FLOAT_RE.match(value)
    return float(match.group(0)) if match else math.nan


def _parse_addon_input(addon: AddAddonInput) -> tuple[str, int]:
    """Validates an add-on input, returning the trimmed option id and the parsed quantity."""
    addon_option_id = (addon.addon_option_id or "").strip()
    if not addon_option_id:
        raise ValueError(ERROR_ADDON_OPTION_ID_REQUIRED)
    quantity = parse_quantity(addon.quantity)
    if quantity is None:
        raise ValueError(ERROR_QUANTITY_INVALID)
    return addon_option_id, quantity


def _validate_payment_input(payment: MakePaymentInput) -> None:
    source_id = payment.payment_source_id
    if not source_id or (
        not source_id.startswith(_PAYMENT_SOURCE_PREFIX)
        and source_id not in _ALLOWED_PAYMENT_SOURCE_IDS
    ):
        raise ValueError(ERROR_PAYMENT_SOURCE_INVALID)
    assert_amount(payment.amount)
    assert_currency(payment.currency)
    assert_idempotency_key(payment.idempotency_key)
    assert_booking_id(payment.booking_id)


def _validate_refund_input(refund: RefundInput) -> None:
    if not refund.payment_id or not refund.payment_id.startswith(_PAYMENT_ID_PREFIX):
        raise ValueError(ERROR_PAYMENT_ID_INVALID)
    assert_amount(refund.amount)
    assert_currency(refund.currency)
    assert_idempotency_key(refund.idempotency_key)
    assert_booking_id(refund.booking_id)


def assert_amount(amount: str) -> None:
    """Raises unless ``amount`` is a non-empty numeric string."""
    try:
        parsed = float(amount) if amount else math.nan
    except ValueError:
        parsed = math.nan
    if math.isnan(parsed):
        raise ValueError(ERROR_AMOUNT_INVALID)


def assert_currency(currency: str) -> None:
    """Raises unless ``currency`` is a 3-letter uppercase code."""
    if not currency or not _CURRENCY_CODE_RE.fullmatch(currency):
        raise ValueError(ERROR_CURRENCY_INVALID)


def assert_idempotency_key(idempotency_key: str | None) -> None:
    if not idempotency_key:
        raise ValueError(ERROR_IDEMPOTENCY_KEY_REQUIRED)


def assert_booking_id(booking_id: str) -> None:
    """Raises unless ``booking_id`` is a valid booking db id (``b_…``) or display id (``B-…``)."""
    if not (
        _BOOKING_DB_ID_RE.fullmatch(booking_id) or _BOOKING_DISPLAY_ID_RE.fullmatch(booking_id)
    ):
        raise ValueError(ERROR_INVALID_BOOKING_ID)


def assert_custom_status(custom_status: str) -> None:
    """Raises unless ``custom_status`` is a non-empty (non-whitespace) string."""
    if not isinstance(custom_status, str) or not custom_status.strip():
        raise ValueError(ERROR_CUSTOM_STATUS_REQUIRED)


def assert_non_empty_string(value: Any, field: str) -> None:
    """Raises unless ``value`` is a non-empty (non-whitespace) string, naming ``field``."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}{_ERROR_NON_EMPTY_STRING_SUFFIX}")


def assert_order_id(order_id: str) -> None:
    """Raises unless ``order_id`` is a valid order db id (``o_…``) or display id (``O-…``)."""
    if not (_ORDER_DB_ID_RE.fullmatch(order_id) or _ORDER_DISPLAY_ID_RE.fullmatch(order_id)):
        raise ValueError(ERROR_INVALID_ORDER_ID)


def _validate_create_input(booking: CreateBookingInput) -> None:
    if not booking.activity_id:
        raise ValueError(ERROR_ACTIVITY_ID_REQUIRED)
    if not booking.availability_time_id:
        raise ValueError(ERROR_AVAILABILITY_TIME_ID_REQUIRED)
    if not booking.tickets:
        raise ValueError(ERROR_TICKETS_REQUIRED)
    if any(not t.resource_option_id or not t.quantity > 0 for t in booking.tickets):
        raise ValueError(ERROR_TICKET_INVALID)
    if not booking.guest or not booking.guest.name:
        raise ValueError(ERROR_GUEST_NAME_REQUIRED)
    if booking.mark_as_paid and not booking.idempotency_key:
        raise ValueError(ERROR_IDEMPOTENCY_KEY_REQUIRED_FOR_PAID)
    if booking.parent_order_id:
        assert_order_id(booking.parent_order_id)


def parse_quantity(value: Any) -> int | None:
    """Parses a positive-integer quantity given as a string (or int); ``None`` when invalid."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    text = str(value).strip()
    if not _QUANTITY_RE.fullmatch(text):
        return None
    num = int(text)
    return num if num > 0 else None


def build_cancellation(
    items: Sequence[AddonItem], addon_option_id: str, quantity: int
) -> tuple[list[WirePayload], int]:
    """Builds the ``bookingQuotes`` cancellation payload for ``updateQuoteV2``.
    Selects up to ``quantity`` options across the booking where the item and the
    option are both still ``CONFIRMED`` and ``option_id == addon_option_id``,
    grouped by booking item. Each selected option becomes a CANCELED
    ``itemOptions`` entry (by its ``option_refid``); the parent add-on is marked
    CANCELED only when every one of its options ends up canceled. Returns the
    payload and the number of options selected."""
    budget = quantity
    # booking_quote_refid -> (item_refid -> (item, canceled option refids))
    by_booking_quote: dict[str, dict[str, tuple[AddonItem, list[str]]]] = {}

    for item in items:
        if budget <= 0:
            break
        for opt in item.addon_item_options:
            if budget <= 0:
                break
            # Only cancel options that are themselves still confirmed — an item can
            # hold a mix of already-canceled and confirmed options for the same
            # option id, and we must skip the canceled ones.
            if (
                opt.item_reservation_status != RESERVATION_STATUS_CONFIRMED
                or opt.option_reservation_status != RESERVATION_STATUS_CONFIRMED
                or opt.option_id != addon_option_id
            ):
                continue
            item_map = by_booking_quote.setdefault(item.booking_quote_refid, {})
            entry = item_map.setdefault(opt.item_refid, (item, []))
            entry[1].append(opt.option_refid)
            budget -= 1

    canceled_count = quantity - budget

    booking_quotes: list[WirePayload] = []
    for booking_quote_refid, item_map in by_booking_quote.items():
        addons: list[WirePayload] = []
        for item_refid, (item, canceled_option_refids) in item_map.items():
            canceled_set = set(canceled_option_refids)
            item_options = [
                {"reservationStatus": ADDON_OPTION_STATUS_CANCELED, "refid": refid}
                for refid in canceled_option_refids
            ]
            # Mark the add-on canceled only if every option ends up canceled.
            all_canceled = all(
                o.option_reservation_status == ADDON_OPTION_STATUS_CANCELED
                or o.option_refid in canceled_set
                for o in item.addon_item_options
            )
            addon: WirePayload = {"itemOptions": item_options, "refid": item_refid}
            if all_canceled:
                addon["reservationStatus"] = ADDON_OPTION_STATUS_CANCELED
            addons.append(addon)
        booking_quotes.append({"refid": booking_quote_refid, "addons": addons})

    return booking_quotes, canceled_count
