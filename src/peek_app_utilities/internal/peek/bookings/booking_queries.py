"""Raw Peek GraphQL fields, queries, mutations, variables, and response shapes
for bookings. Internal — never re-exported from the package root.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.booking import BookingSearchBy

SEARCH_BY_PURCHASE_DATE: Final[BookingSearchBy] = "purchaseDate"
SEARCH_BY_ACTIVITY_DATE: Final[BookingSearchBy] = "activityDate"

_ORDER_BY_DIRECTION_ASC: Final = "ASC"
_ORDER_BY_FIELD_STARTS_AT: Final = "STARTS_AT"


def normalize_booking_id(booking_id: str) -> str:
    """Normalizes a booking id to the API's expected form (lowercased, ``-`` → ``_``)."""
    return booking_id.lower().replace("-", "_")


def build_sales_query(node_body: str) -> str:
    """Wraps a ``sales`` edge-node selection in the shared paginated ``sales(...)``
    query envelope (the ``query Sales(...)``/``pageInfo``/``edges { node { … } }``
    boilerplate every booking read uses). ``node_body`` is the raw selection
    placed inside ``node { … }`` (e.g. ``... on Booking { … }``, optionally
    preceded by ``Sale``-level fields like ``order { … }``). All readers share it
    so the envelope lives in one place."""
    return f"""
    query Sales($after: String, $first: Int, $filter: SalesFilter!, $orderBy: SalesOrdering) {{
      sales(after: $after, first: $first, filter: $filter, orderBy: $orderBy) {{
        pageInfo {{ endCursor hasNextPage }}
        edges {{
          node {{
            {node_body}
          }}
        }}
      }}
    }}
  """


# The customer-identity guest fields (name, contact, DOB, postal code, and the
# free-text custom field responses). These are PII and are only selected when
# `full_customer_access` is set; the trailing group sits after the non-PII flags
# to keep the maximal selection order stable for the webhook drift-guard.
_GUEST_IDENTITY_PII_FIELDS: Final = "name country dateOfBirth email isGdpr"
_GUEST_CONTACT_PII_FIELDS: Final = """phone
  postalCode
  fieldResponses {
    id
    text
    fieldLocation {
      field {
        name
      }
    }
  }"""


def build_guest_fields(full_customer_access: bool) -> str:
    """Builds the guest selection. Without ``full_customer_access``, only the
    structural id and the participation/opt-in flags are requested — the identity
    fields come back absent (→ ``None`` in the converter)."""
    return f"""
  id
  {_GUEST_IDENTITY_PII_FIELDS if full_customer_access else ""}
  isParticipant
  optinSms
  optinMarketing
  {_GUEST_CONTACT_PII_FIELDS if full_customer_access else ""}
"""


def build_booking_guests_fields(full_customer_access: bool) -> str:
    """Builds the ``bookingGuests`` + ``primaryGuest`` guest sections."""
    guest_fields = build_guest_fields(full_customer_access)
    return f"""
  bookingGuests {{
    {guest_fields}
  }}
  primaryGuest {{
    {guest_fields}
  }}
"""


BOOKING_GUESTS_FIELDS: Final = build_booking_guests_fields(True)
"""The maximal (PII-included) guest sections — used by the webhook selection."""

# The primary-guest PII block on a booking — drives `customer_name`/`email`/
# `phone`. Selected only when `full_customer_access` is set.
_BOOKING_PRIMARY_GUEST_PII_FIELDS: Final = """primaryGuest {
    name
    email
    phone
    optinMarketing
    optinSms
    isGdpr
    postalCode
  }"""

# Custom question answers captured on the booking and per guest/ticket. These
# routinely carry PII (address, DOB, captured location), so they are selected
# only when `full_customer_access` is set.
_BOOKING_QUESTION_ANSWERS_PII_FIELDS: Final = """questionAnswers {
    answer
    questionText
    questionLocationSnapshot {
      latitude
      longitude
    }
  }
  tickets {
    questionAnswers {
      answer
      questionText
    }
  }"""

_BOOKING_PORTAL_URL_PII_FIELD: Final = "bookingPortalUrl"


def build_booking_query_fields(full_customer_access: bool) -> str:
    """Builds the booking selection. Without ``full_customer_access`` the
    primary-guest block, the customer booking-portal URL, and the custom question
    answers are omitted entirely (they come back absent → ``None``/empty in the
    converter). The operator-facing deep link, notes, money, and structural fields
    always stay."""
    return f"""
  displayId
  id
  {_BOOKING_PRIMARY_GUEST_PII_FIELDS if full_customer_access else ""}
  activitySnapshot {{
    type
    name
    id
  }}
  ticketQuantities {{
    quantity
    resourceOptionSnapshot {{
      name
      id
    }}
  }}
  reservationStatus
  checkinStatus
  returnStatus
  fulfillmentStatusOverride {{
    status
  }}
  timeSnapshot {{
    id
    legacyId
  }}
  purchasedAt
  purchasedAtUtc
  startsAt
  startsAtUtc
  endsAt
  endsAtUtc
  availabilityTimeId
  {_BOOKING_PORTAL_URL_PII_FIELD if full_customer_access else ""}
  operatorNotes
  operatorStatus
  value {{
    total {{
      formatted
      amount
    }}
  }}
  balance {{
    total {{
      amount
      formatted
    }}
  }}
  tips {{
    price {{
      amount
      formatted
    }}
  }}
  order {{
    displayId
    id
    promoCodes {{
      code
    }}
    channelSnapshot {{
      id
      name
      agent {{
        name
      }}
    }}
    initialQuote {{
      source {{
        actor {{
          app
          name
        }}
      }}
    }}
  }}
  {_BOOKING_QUESTION_ANSWERS_PII_FIELDS if full_customer_access else ""}
  resourcePoolAssignments {{
    quantity
    resourcePool {{
      name
      shortName
      resources {{
        name
      }}
    }}
    resourceAssignments {{
      resource {{
        id
        name
      }}
    }}
  }}
"""


BOOKING_QUERY_FIELDS: Final = build_booking_query_fields(True)
"""The maximal (PII-included) booking selection — used by the webhook selection."""

PRICE_BREAKDOWN_FIELDS: Final = """
  convenienceFee { amount formatted }
  deposit { amount formatted }
  discount { amount formatted }
  discountedPrice { amount formatted }
  fees { amount formatted }
  flatPartnerFee { amount formatted }
  price { amount formatted }
  retailPrice { amount formatted }
  taxes { amount formatted }
  tips { amount formatted }
"""

TICKET_VALUE_FIELDS: Final = """
  value {
    price { amount formatted }
    total { amount formatted }
  }
"""
"""Per-ticket price selection (list price + line total) injected into
``ticketQuantities`` when the price breakdown is requested."""

VALUE_OPEN_TOKEN: Final = "value {"
"""The ``value`` sub-field that anchors the price-breakdown injection."""
_TICKET_QUANTITIES_OPEN_TOKEN: Final = "ticketQuantities {"


def build_bookings_listing_query(
    include_guests: bool,
    include_price_breakdown: bool,
    full_customer_access: bool = True,
) -> str:
    """Builds the bookings listing query, optionally including guests and price
    breakdown. When ``full_customer_access`` is ``False`` (default ``True`` for
    the raw builder; the service passes the resolved access option), customer PII
    fields are not requested at all — see :func:`build_booking_query_fields`."""
    guests_section = build_booking_guests_fields(full_customer_access) if include_guests else ""
    # Inject the booking-level breakdown first: it anchors on the first `value {`,
    # which is the booking node's. The ticket-level `value` (added by the second
    # replace) must go in afterwards, or it would capture that anchor instead.
    base_fields = build_booking_query_fields(full_customer_access)
    fields = (
        base_fields.replace(
            VALUE_OPEN_TOKEN, f"{VALUE_OPEN_TOKEN} {PRICE_BREAKDOWN_FIELDS}", 1
        ).replace(
            _TICKET_QUANTITIES_OPEN_TOKEN,
            f"{_TICKET_QUANTITIES_OPEN_TOKEN} {TICKET_VALUE_FIELDS}",
            1,
        )
        if include_price_breakdown
        else base_fields
    )

    return build_sales_query(f"""
    ... on Booking {{
      {fields}
      {guests_section}
    }}
  """)


def build_booking_guests_query(full_customer_access: bool) -> str:
    """Builds the query fetching the guests for a booking. Without
    ``full_customer_access`` the guest identity fields are omitted (only ids +
    participation/opt-in flags)."""
    return build_sales_query(f"""
    ... on Booking {{
      displayId
      id
      {build_booking_guests_fields(full_customer_access)}
    }}
  """)


BOOKING_PAYMENTS_ON_FILE_QUERY: Final = build_sales_query("""
  order {
    payments {
      id
      paymentSource { id }
      appliedAt
      currentAmount { amount currency }
      refundableAmount { amount currency }
    }
    id
    displayId
    paymentSources { description type id }
  }
  ... on Booking {
    displayId
    id
  }
""")
"""Query fetching a booking's order payments + payment sources."""

UPDATE_OPERATOR_NOTES_MUTATION: Final = """
  mutation Account($input: UpdateOperatorNotesForBookingInput!) {
    updateOperatorNotesForBooking(input: $input) {
      booking { operatorNotes }
    }
  }
"""

UPDATE_OPERATOR_STATUS_MUTATION: Final = """
  mutation Account($input: UpdateOperatorStatusForBookingInput!) {
    updateOperatorStatusForBooking(input: $input) {
      booking { operatorStatus }
    }
  }
"""

UPDATE_BOOKING_CHECKIN_MUTATION: Final = """
  mutation Account($input: UpdateBookingCheckInInput!) {
    updateBookingCheckIn(input: $input) {
      booking { checkinStatus }
    }
  }
"""

CANCEL_BOOKING_MUTATION: Final = """
  mutation Account($input: CancelBookingInput!) {
    cancelBooking(input: $input) {
      booking { id displayId reservationStatus }
    }
  }
"""

APPLY_PAYMENT_TO_ORDER_MUTATION: Final = """
  mutation ApplyPaymentToOrder($input: ApplyPaymentToOrderInput!) {
    applyPaymentToOrder(input: $input) {
      transactionId
      errors { code detail value }
    }
  }
"""

APPLY_REFUND_TO_ORDER_MUTATION: Final = """
  mutation ApplyRefundToOrder($input: ApplyRefundToOrderInput!) {
    applyRefundToOrder(input: $input) {
      transactionId
      errors { code detail value }
    }
  }
"""

CREATE_INVOICE_LINK_MUTATION: Final = """
  mutation CreateInvoiceLink($input: CreateInvoiceLinkInput!) {
    createInvoiceLink(input: $input) {
      invoiceLink { status url }
      errors { code detail value __typename }
    }
  }
"""

CREATE_QUOTE_FROM_ORDER_MUTATION: Final = """
  mutation CreateQuoteFromOrder($input: CreateQuoteFromOrderInput!) {
    createQuoteFromOrder(input: $input) {
      errors { detail value code }
      quote {
        id
        saleQuotes { refid reservationStatus }
      }
    }
  }
"""

UPDATE_QUOTE_V2_MUTATION: Final = """
  mutation UpdateQuoteV2($input: UpdateQuoteV2Input!) {
    updateQuoteV2(input: $input) {
      errors { detail value code }
      quote { id }
    }
  }
"""

AMEND_ORDER_MUTATION: Final = """
  mutation AmendOrder($input: AmendOrderInput!) {
    amendOrder(input: $input) {
      errors { code detail value }
      order { id }
    }
  }
"""

CREATE_QUOTE_V2_MUTATION: Final = """
  mutation CreateQuoteV2($input: CreateQuoteV2Input!) {
    createQuoteV2(input: $input) {
      errors { detail value code }
      quote { id }
    }
  }
"""

CREATE_ORDER_FROM_QUOTE_MUTATION: Final = """
  mutation CreateOrderFromQuote($input: CreateOrderFromQuoteInput!) {
    createOrderFromQuote(input: $input) {
      errors { code detail value }
      order {
        id
        sales {
          id
          displayId
          ... on Booking {
            balance { total { amount currency formatted } }
          }
        }
      }
    }
  }
"""


def build_bookings_variables(
    *,
    page_size: int,
    after: str | None,
    start_date_time: str | None = None,
    end_date_time: str | None = None,
    timeslot_id: str | None = None,
    search_by: BookingSearchBy | None = None,
    product_id: str | None = None,
    booking_id: str | None = None,
    email: str | None = None,
    search_string: str | None = None,
) -> dict[str, Any]:
    """Builds the variables for the bookings/guests/payments/metadata sales queries."""
    variables_filter: dict[str, Any] = {}
    booking_filter: dict[str, Any] = {}

    if booking_id:
        booking_filter["ids"] = [normalize_booking_id(booking_id)]
    elif timeslot_id:
        booking_filter["timeslotRefid"] = timeslot_id
    else:
        if search_by == SEARCH_BY_ACTIVITY_DATE:
            booking_filter["overlapsRange"] = f"[{start_date_time},{end_date_time}]"
        elif search_by == SEARCH_BY_PURCHASE_DATE:
            variables_filter["purchasedAtRangeUtc"] = f"[{start_date_time},{end_date_time}]"
        if product_id:
            booking_filter["activityIds"] = [product_id]

    if email:
        variables_filter["primaryGuestEmail"] = email
    if search_string:
        variables_filter["searchString"] = search_string
    if booking_filter:
        variables_filter["bookingFilter"] = booking_filter

    return {
        "first": page_size,
        "after": after,
        "orderBy": {"direction": _ORDER_BY_DIRECTION_ASC, "field": _ORDER_BY_FIELD_STARTS_AT},
        "filter": variables_filter,
    }


# ---- Raw response shapes -------------------------------------------------


class BookingGuestFieldResponse(TypedDict, total=False):
    id: str
    text: str | None
    fieldLocation: dict[str, Any] | None


class BookingGuestNode(TypedDict, total=False):
    id: str
    name: str | None
    country: str | None
    dateOfBirth: str | None
    phone: str | None
    email: str | None
    isGdpr: bool
    isParticipant: bool
    optinSms: bool
    optinMarketing: bool
    postalCode: str | None
    fieldResponses: list[BookingGuestFieldResponse]


class BookingNode(TypedDict, total=False):
    """A raw booking node. The base bookings query selects the primary guest's
    name/email/phone; when guests are requested the full guest fields (id,
    fieldResponses, …) are merged in as well, and ``bookingGuests`` is present."""

    displayId: str
    id: str
    primaryGuest: BookingGuestNode | None
    activitySnapshot: dict[str, Any] | None
    ticketQuantities: list[dict[str, Any]]
    reservationStatus: str
    checkinStatus: str
    returnStatus: str
    fulfillmentStatusOverride: dict[str, Any] | None
    timeSnapshot: dict[str, Any] | None
    purchasedAt: str
    purchasedAtUtc: str
    startsAt: str
    startsAtUtc: str
    endsAt: str
    endsAtUtc: str
    availabilityTimeId: str
    bookingPortalUrl: str
    operatorNotes: str | None
    operatorStatus: str | None
    value: dict[str, Any]
    balance: dict[str, Any] | None
    tips: list[dict[str, Any]]
    order: dict[str, Any] | None
    questionAnswers: list[dict[str, Any]]
    tickets: list[dict[str, Any]] | None
    resourcePoolAssignments: list[dict[str, Any]]
    bookingGuests: list[BookingGuestNode]


class PaymentMutationError(TypedDict, total=False):
    """A payment/refund/invoice/quote error entry."""

    code: str
    detail: str
    value: str | None
