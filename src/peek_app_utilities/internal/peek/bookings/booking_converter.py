"""Pure functions mapping a raw booking node into the clean :class:`Booking`
model. No network, no logging, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from peek_app_utilities.internal.peek.bookings.booking_queries import normalize_booking_id
from peek_app_utilities.models.peek.booking import (
    Booking,
    CustomQuestionAnswer,
    Guest,
    GuestMetadata,
    Price,
    Resource,
    ResourcePoolAssignment,
    Ticket,
)

UNKNOWN: Final = "unknown"
_UNKNOWN_TICKET_NAME: Final = "Unknown"
_DEFAULT_PRICE_AMOUNT: Final = "0"

_PEEK_PRO_DEEP_LINK_BASE: Final = "http://pro-app.peek.com/-/order"

_RENTAL_TYPE: Final = "RENTAL"
_RESERVATION_STATUS_CANCELED: Final = "CANCELED"
_FULFILLMENT_STATUS_NO_SHOW: Final = "NO_SHOW"
_STATUS_NONE: Final = "NONE"

_SOURCE_SOURCE_MAP: Final[Mapping[str, str]] = {
    "APP_REGISTRY": "app",
    "BOOKING_IMPORTER_FUTURE": "importer",
    "BOOKING_IMPORTER_HISTORIC": "importer",
    "EXPEDIA": "expedia",
    "GROUPON": "groupon",
    "GYG": "getyourguide",
    "HOOK": "internal",
    "INTERNAL_TOOLS": "internal",
    "IOS_PP": "ios",
    "OCTO": "octo",
    "PDC": "peekcom",
    "PEEK_PLUS": "peekcom",
    "PP": "backend",
    "RWG": "rwg",
    "SELF_SERVE": "internal",
    "SYSTEM": "internal",
    "VIATOR": "viator",
    "WIDGET": "website",
    "YELP": "yelp",
}

_SOURCE_DESC_MAP: Final[Mapping[str, str]] = {
    "APP_REGISTRY": "App Store App",
    "BOOKING_IMPORTER_FUTURE": "Booking Importer",
    "BOOKING_IMPORTER_HISTORIC": "Booking Importer",
    "EXPEDIA": "Expedia",
    "GROUPON": "Groupon",
    "GYG": "GetYourGuide",
    "HOOK": "Internal",
    "INTERNAL_TOOLS": "Internal",
    "IOS_PP": "Peek Pro: iOS App",
    "OCTO": "OCTO",
    "PDC": "Peek.com",
    "PEEK_PLUS": "Peek.com",
    "PP": "Peek Pro: Backend",
    "RWG": "Reserve with Google",
    "SELF_SERVE": "Internal",
    "SYSTEM": "Internal",
    "VIATOR": "Viator",
    "WIDGET": "Website Booking Flow",
    "YELP": "Yelp",
}

RawNode = Mapping[str, Any]


def _mapping(value: Any) -> dict[str, Any]:
    """Narrows an optional nested node to a dict (``{}`` for ``None``/non-mapping)."""
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    """Narrows an optional nested list to a list (``[]`` for ``None``/non-list)."""
    return list(value) if isinstance(value, Sequence) and not isinstance(value, str) else []


def _dig(data: RawNode, *keys: str) -> dict[str, Any]:
    """Walks nested mapping keys, yielding ``{}`` as soon as one is absent."""
    current: dict[str, Any] = _mapping(data)
    for key in keys:
        current = _mapping(current.get(key))
    return current


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def from_booking_node(
    node: RawNode | None,
    include_guests: bool = False,
    include_price_breakdown: bool = False,
) -> Booking:
    """Converts a raw booking node into a :class:`Booking`."""
    data = _mapping(node)
    ticket_quantities = [_mapping(t) for t in _sequence(data.get("ticketQuantities"))]
    actor = _dig(data, "order", "initialQuote", "source", "actor")
    app: str | None = actor.get("app") or None
    source_details: str | None = actor.get("name") or None

    primary_guest = _mapping(data.get("primaryGuest"))
    activity = _mapping(data.get("activitySnapshot"))
    order = _mapping(data.get("order"))
    value = _mapping(data.get("value"))
    balance_total = _dig(data, "balance", "total")
    value_total = _mapping(value.get("total"))
    channel_snapshot = order.get("channelSnapshot")
    pool_assignments = [_mapping(p) for p in _sequence(data.get("resourcePoolAssignments"))]
    starts_at = data.get("startsAt") or None
    ends_at = data.get("endsAt") or None

    def breakdown(key: str) -> Price | None:
        return _map_price(value.get(key)) if include_price_breakdown else None

    return Booking(
        booking_id=data.get("id") or "",
        display_id=data.get("displayId") or "",
        source=_source_from_app(app),
        source_app=app or UNKNOWN,
        source_description=_source_description_from_app(app),
        source_details=source_details,
        customer_name=primary_guest.get("name") or "",
        customer_email=primary_guest.get("email") or None,
        customer_phone=primary_guest.get("phone") or None,
        product_id=activity.get("id") or UNKNOWN,
        product_name=activity.get("name") or UNKNOWN,
        is_rental_product=activity.get("type") == _RENTAL_TYPE,
        timeslot_id=_mapping(data.get("timeSnapshot")).get("legacyId") or None,
        total_tickets=_ticket_quantity(ticket_quantities),
        ticket_description=_format_tickets(ticket_quantities),
        tickets=_tickets_to_ticket_list(ticket_quantities, include_price_breakdown),
        is_canceled=data.get("reservationStatus") == _RESERVATION_STATUS_CANCELED,
        is_no_show=_mapping(data.get("fulfillmentStatusOverride")).get("status")
        == _FULFILLMENT_STATUS_NO_SHOW,
        is_checked_in=data.get("checkinStatus") != _STATUS_NONE,
        is_returned=data.get("returnStatus") != _STATUS_NONE,
        purchased_at=data.get("purchasedAt") or None,
        purchased_at_utc=data.get("purchasedAtUtc") or None,
        starts_at=starts_at,
        starts_at_utc=data.get("startsAtUtc") or None,
        ends_at=ends_at,
        ends_at_utc=data.get("endsAtUtc") or None,
        duration_min=_duration_in_min(starts_at, ends_at),
        availability_time_id=data.get("availabilityTimeId") or None,
        portal_url=data.get("bookingPortalUrl") or None,
        notes=data.get("operatorNotes") or "",
        custom_status=data.get("operatorStatus") or None,
        value_display=value_total.get("formatted") or "",
        value_amount=value_total.get("amount") or "",
        outstanding_balance_amount=balance_total.get("amount") or "",
        outstanding_balance_display=balance_total.get("formatted") or "",
        promo_codes=[
            _text(_mapping(promo).get("code")) for promo in _sequence(order.get("promoCodes"))
        ],
        tips=[
            Price(
                display=_dig(tip, "price").get("formatted") or "",
                amount=_dig(tip, "price").get("amount") or "",
            )
            for tip in _sequence(data.get("tips"))
        ],
        custom_question_answers=_map_question_answers(data.get("questionAnswers")),
        custom_guest_question_answers=_map_guest_question_answers(data.get("tickets")),
        resources=[
            Resource(
                quantity=pool.get("quantity") or 0,
                name=_dig(pool, "resourcePool").get("name") or "",
                short_name=_dig(pool, "resourcePool").get("shortName") or "",
            )
            for pool in pool_assignments
        ],
        resource_pool_assignments=_map_resource_pool_assignments(pool_assignments),
        reseller_id=_mapping(channel_snapshot).get("id") or None,
        reseller_name=_reseller_name_from_channel_snapshot(channel_snapshot),
        order_id=order.get("id") or "",
        peek_pro_booking_deep_link=_build_peek_pro_booking_deep_link(
            order.get("id"), data.get("id")
        ),
        convenience_fee=breakdown("convenienceFee"),
        deposit=breakdown("deposit"),
        discount=breakdown("discount"),
        discounted_price=breakdown("discountedPrice"),
        fees=breakdown("fees"),
        flat_partner_fee=breakdown("flatPartnerFee"),
        price=breakdown("price"),
        retail_price=breakdown("retailPrice"),
        taxes=breakdown("taxes"),
        tips_breakdown=breakdown("tips"),
        guests=convert_guests(data) if include_guests else None,
    )


def convert_guests(data: RawNode) -> list[Guest]:
    """Merges a booking node's ``bookingGuests`` + ``primaryGuest`` into a guest list."""
    booking_guest_nodes = [_mapping(g) for g in _sequence(data.get("bookingGuests"))]
    primary_guest_node = _mapping(data.get("primaryGuest"))
    primary_id = primary_guest_node.get("id")

    guests = [
        map_guest_node(guest_node, bool(primary_id) and guest_node.get("id") == primary_id)
        for guest_node in booking_guest_nodes
    ]

    has_primary_in_guests = bool(primary_id) and any(
        guest.get("id") == primary_id for guest in booking_guest_nodes
    )
    if not has_primary_in_guests and primary_id:
        guests.append(map_guest_node(primary_guest_node, True))

    return guests


def map_guest_node(guest_node: RawNode, is_primary: bool) -> Guest:
    """Maps a single raw guest node into a :class:`Guest`."""
    field_responses = [_mapping(r) for r in _sequence(guest_node.get("fieldResponses"))]
    metadata = [
        GuestMetadata(
            id=_text(response.get("id")),
            name=_dig(response, "fieldLocation", "field").get("name") or "",
            value=response.get("text") or "",
        )
        for response in field_responses
    ]
    date_of_birth = guest_node.get("dateOfBirth")
    return Guest(
        id=_text(guest_node.get("id")),
        name=guest_node.get("name"),
        country=guest_node.get("country"),
        date_of_birth=_parse_datetime(date_of_birth) if date_of_birth else None,
        phone=guest_node.get("phone"),
        email=guest_node.get("email"),
        is_gdpr=bool(guest_node.get("isGdpr")),
        is_participant=bool(guest_node.get("isParticipant")),
        is_primary=is_primary,
        optin_sms=bool(guest_node.get("optinSms")),
        optin_marketing=bool(guest_node.get("optinMarketing")),
        postal_code=guest_node.get("postalCode"),
        metadata=metadata,
    )


def _map_question_answers(raw: Any) -> list[CustomQuestionAnswer]:
    answers: list[CustomQuestionAnswer] = []
    for answer in _sequence(raw):
        node = _mapping(answer)
        location = _mapping(node.get("questionLocationSnapshot"))
        has_coordinates = bool(location.get("latitude")) and bool(location.get("longitude"))
        answers.append(
            CustomQuestionAnswer(
                question=_text(node.get("questionText")),
                answer=_text(node.get("answer")),
                latitude=location["latitude"] if has_coordinates else None,
                longitude=location["longitude"] if has_coordinates else None,
            )
        )
    return answers


def _map_guest_question_answers(raw_tickets: Any) -> list[CustomQuestionAnswer]:
    answers: list[CustomQuestionAnswer] = []
    for ticket in _sequence(raw_tickets):
        for qa in _sequence(_mapping(ticket).get("questionAnswers")):
            node = _mapping(qa)
            # Mirrors the `!== undefined` guard: a response missing either key is dropped.
            if "answer" not in node or "questionText" not in node:
                continue
            answers.append(
                CustomQuestionAnswer(
                    question=_text(node.get("questionText")), answer=_text(node.get("answer"))
                )
            )
    return answers


def _build_peek_pro_booking_deep_link(order_id: str | None, booking_id: str | None) -> str:
    """Builds the Peek Pro app deep link from an order id and booking id. Both ids
    are normalized (lowercased, ``-`` → ``_``); returns ``""`` when either is absent."""
    if not order_id or not booking_id:
        return ""
    return (
        f"{_PEEK_PRO_DEEP_LINK_BASE}%2F{normalize_booking_id(order_id)}"
        f"%3FsaleId={normalize_booking_id(booking_id)}"
    )


def _source_from_app(app: str | None) -> str:
    if not app:
        return UNKNOWN
    return _SOURCE_SOURCE_MAP.get(app, UNKNOWN)


def _source_description_from_app(app: str | None) -> str:
    if not app:
        return UNKNOWN
    return _SOURCE_DESC_MAP.get(app, UNKNOWN)


def _reseller_name_from_channel_snapshot(channel_snapshot: Any) -> str | None:
    if not channel_snapshot:
        return None
    snapshot = _mapping(channel_snapshot)
    out = snapshot.get("name") or ""
    agent_name = _mapping(snapshot.get("agent")).get("name")
    if agent_name:
        out += " - " + agent_name
    return str(out)


def _tickets_to_ticket_list(
    ticket_quantities: list[dict[str, Any]], include_price_breakdown: bool
) -> list[Ticket]:
    tickets: list[Ticket] = []
    for ticket in ticket_quantities:
        snapshot = _mapping(ticket.get("resourceOptionSnapshot"))
        value = _mapping(ticket.get("value"))
        tickets.append(
            Ticket(
                name=snapshot.get("name") or _UNKNOWN_TICKET_NAME,
                quantity=ticket.get("quantity") or 0,
                ticket_id=snapshot.get("id") or UNKNOWN,
                list_price=_map_price(value.get("price")) if include_price_breakdown else None,
                total_value=_map_price(value.get("total")) if include_price_breakdown else None,
            )
        )
    return tickets


def _parse_datetime(value: Any) -> datetime | None:
    """Parses an ISO datetime/date string; ``None`` when it cannot be parsed."""
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _duration_in_min(starts_at: str | None, ends_at: str | None) -> int:
    if not starts_at or not ends_at:
        return 0
    start = _parse_datetime(starts_at)
    end = _parse_datetime(ends_at)
    if start is None or end is None:
        return 0
    try:
        delta = end - start
    except TypeError:  # one side is timezone-aware and the other naive
        return 0
    return int(delta.total_seconds() // 60)


def _ticket_quantity(ticket_quantities: list[dict[str, Any]]) -> int:
    return sum(ticket.get("quantity") or 0 for ticket in ticket_quantities)


def _format_tickets(ticket_quantities: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{ticket.get('quantity') or 0}x "
        f"{_mapping(ticket.get('resourceOptionSnapshot')).get('name') or _UNKNOWN_TICKET_NAME}"
        for ticket in ticket_quantities
    )


def _map_resource_pool_assignments(
    pool_assignments: list[dict[str, Any]],
) -> list[ResourcePoolAssignment]:
    return [
        ResourcePoolAssignment(
            id=_dig(assignment, "resource").get("id") or "",
            name=_dig(assignment, "resource").get("name") or "",
        )
        for pool in pool_assignments
        for assignment in _sequence(pool.get("resourceAssignments"))
    ]


def _map_price(price_data: Any) -> Price | None:
    price = _mapping(price_data)
    if not price.get("amount") and not price.get("formatted"):
        return None
    return Price(
        amount=price.get("amount") or _DEFAULT_PRICE_AMOUNT, display=price.get("formatted") or ""
    )
