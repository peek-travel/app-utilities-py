from datetime import datetime
from typing import Any

from peek_app_utilities.internal.peek.bookings.booking_converter import (
    convert_guests,
    from_booking_node,
)
from peek_app_utilities.models.peek.booking import (
    CustomQuestionAnswer,
    GuestMetadata,
    Price,
    Resource,
    ResourcePoolAssignment,
    Ticket,
)


def guest_node() -> dict[str, Any]:
    return {
        "id": "g1",
        "name": "Ada",
        "email": "ada@example.com",
        "phone": "+1",
        "country": "US",
        "dateOfBirth": "1990-01-01",
        "isGdpr": True,
        "isParticipant": True,
        "optinSms": True,
        "optinMarketing": False,
        "postalCode": "12345",
        "fieldResponses": [
            {"id": "f1", "text": "peanuts", "fieldLocation": {"field": {"name": "Allergies"}}}
        ],
    }


def full_node() -> dict[str, Any]:
    return {
        "id": "b_1",
        "displayId": "B-1",
        "primaryGuest": guest_node(),
        "activitySnapshot": {"type": "RENTAL", "name": "Kayak", "id": "act-1"},
        "ticketQuantities": [
            {
                "quantity": 2,
                "resourceOptionSnapshot": {"name": "Adult", "id": "r1"},
                "value": {
                    "price": {"amount": "45.00", "formatted": "$45.00"},
                    "total": {"amount": "90.00", "formatted": "$90.00"},
                },
            },
            {"quantity": 1, "resourceOptionSnapshot": {"name": "Child", "id": "r2"}},
        ],
        "reservationStatus": "CANCELED",
        "checkinStatus": "CHECKED_IN",
        "returnStatus": "RETURNED",
        "fulfillmentStatusOverride": {"status": "NO_SHOW"},
        "timeSnapshot": {"id": "ts", "legacyId": "legacy-ts"},
        "purchasedAt": "2026-01-01T09:00:00Z",
        "purchasedAtUtc": "2026-01-01T09:00:00Z",
        "startsAt": "2026-01-02T10:00:00Z",
        "startsAtUtc": "2026-01-02T10:00:00Z",
        "endsAt": "2026-01-02T11:30:00Z",
        "endsAtUtc": "2026-01-02T11:30:00Z",
        "availabilityTimeId": "avail-1",
        "bookingPortalUrl": "https://portal/b1",
        "operatorNotes": "VIP",
        "operatorStatus": "Awaiting deposit",
        "value": {
            "total": {"amount": "100.00", "formatted": "$100.00"},
            "convenienceFee": {"amount": "2.00", "formatted": "$2.00"},
            "price": {"amount": "90.00", "formatted": "$90.00"},
        },
        "balance": {"total": {"amount": "10.00", "formatted": "$10.00"}},
        "tips": [{"price": {"amount": "5.00", "formatted": "$5.00"}}],
        "order": {
            "id": "o_1",
            "promoCodes": [{"code": "SUMMER"}],
            "channelSnapshot": {"id": "ch-1", "name": "Acme", "agent": {"name": "Jane"}},
            "initialQuote": {"source": {"actor": {"app": "WIDGET", "name": "Acme Widget"}}},
        },
        "questionAnswers": [
            {
                "answer": "yes",
                "questionText": "Waiver?",
                "questionLocationSnapshot": {"latitude": "1.0", "longitude": "2.0"},
            }
        ],
        "tickets": [
            {"questionAnswers": [{"answer": "blue", "questionText": "Color?"}]},
            {"questionAnswers": None},
        ],
        "resourcePoolAssignments": [
            {
                "quantity": 1,
                "resourcePool": {"name": "Guides", "shortName": "G"},
                "resourceAssignments": [{"resource": {"id": "res-1", "name": "Ada"}}],
            }
        ],
        "bookingGuests": [guest_node()],
    }


class TestFromBookingNode:
    def test_maps_a_fully_populated_node_with_guests_and_price_breakdown(self):
        booking = from_booking_node(full_node(), True, True)

        assert booking.booking_id == "b_1"
        assert booking.display_id == "B-1"
        assert booking.source == "website"
        assert booking.source_app == "WIDGET"
        assert booking.source_description == "Website Booking Flow"
        assert booking.source_details == "Acme Widget"
        assert booking.customer_name == "Ada"
        assert booking.is_rental_product is True
        assert booking.timeslot_id == "legacy-ts"
        assert booking.total_tickets == 3
        assert booking.ticket_description == "2x Adult, 1x Child"
        assert len(booking.tickets) == 2
        assert booking.tickets[0] == Ticket(
            name="Adult",
            quantity=2,
            ticket_id="r1",
            list_price=Price(amount="45.00", display="$45.00"),
            total_value=Price(amount="90.00", display="$90.00"),
        )
        # A ticket without a `value` selection has no list/total price.
        assert booking.tickets[1].list_price is None
        assert booking.tickets[1].total_value is None
        assert booking.is_canceled is True
        assert booking.is_no_show is True
        assert booking.is_checked_in is True
        assert booking.is_returned is True
        assert booking.duration_min == 90
        assert booking.notes == "VIP"
        assert booking.custom_status == "Awaiting deposit"
        assert booking.value_display == "$100.00"
        assert booking.outstanding_balance_amount == "10.00"
        assert booking.promo_codes == ["SUMMER"]
        assert booking.tips == [Price(display="$5.00", amount="5.00")]
        assert booking.resources == [Resource(quantity=1, name="Guides", short_name="G")]
        assert booking.resource_pool_assignments == [ResourcePoolAssignment(id="res-1", name="Ada")]
        assert booking.reseller_id == "ch-1"
        assert booking.reseller_name == "Acme - Jane"
        assert booking.order_id == "o_1"
        assert (
            booking.peek_pro_booking_deep_link
            == "http://pro-app.peek.com/-/order%2Fo_1%3FsaleId=b_1"
        )
        assert booking.convenience_fee == Price(amount="2.00", display="$2.00")
        assert booking.price == Price(amount="90.00", display="$90.00")
        assert booking.taxes is None
        assert booking.custom_question_answers == [
            CustomQuestionAnswer(question="Waiver?", answer="yes", latitude="1.0", longitude="2.0")
        ]
        assert booking.custom_guest_question_answers == [
            CustomQuestionAnswer(question="Color?", answer="blue")
        ]
        assert booking.guests is not None
        assert len(booking.guests) == 1
        guest = booking.guests[0]
        assert guest.id == "g1"
        assert guest.is_primary is True
        assert guest.date_of_birth == datetime(1990, 1, 1)
        assert guest.metadata == [GuestMetadata(id="f1", name="Allergies", value="peanuts")]

    def test_applies_defaults_for_an_empty_node(self):
        booking = from_booking_node(None)
        assert booking.booking_id == ""
        assert booking.display_id == ""
        assert booking.source == "unknown"
        assert booking.source_app == "unknown"
        assert booking.source_description == "unknown"
        assert booking.source_details is None
        assert booking.customer_name == ""
        assert booking.customer_email is None
        assert booking.product_id == "unknown"
        assert booking.product_name == "unknown"
        assert booking.is_rental_product is False
        assert booking.timeslot_id is None
        assert booking.total_tickets == 0
        assert booking.ticket_description == ""
        assert booking.tickets == []
        assert booking.is_canceled is False
        assert booking.duration_min == 0
        assert booking.notes == ""
        assert booking.custom_status is None
        assert booking.promo_codes == []
        assert booking.tips == []
        assert booking.resources == []
        assert booking.resource_pool_assignments == []
        assert booking.reseller_id is None
        assert booking.reseller_name is None
        assert booking.order_id == ""
        assert booking.peek_pro_booking_deep_link == ""
        assert booking.custom_question_answers == []
        assert booking.custom_guest_question_answers == []
        assert booking.guests is None
        assert booking.convenience_fee is None

    def test_maps_an_unknown_app_and_non_rental_type_to_defaults(self):
        node = {
            "activitySnapshot": {"type": "ACTIVITY", "name": "Tour", "id": "a"},
            "order": {"initialQuote": {"source": {"actor": {"app": "NOT_A_SOURCE"}}}},
        }
        booking = from_booking_node(node)
        assert booking.source == "unknown"
        assert booking.source_description == "unknown"
        assert booking.source_app == "NOT_A_SOURCE"
        assert booking.source_details is None
        assert booking.is_rental_product is False

    def test_normalizes_ids_when_building_the_peek_pro_deep_link(self):
        node = {"id": "B-2", "order": {"id": "O-2"}}
        assert (
            from_booking_node(node).peek_pro_booking_deep_link
            == "http://pro-app.peek.com/-/order%2Fo_2%3FsaleId=b_2"
        )

    def test_uses_just_the_channel_name_when_there_is_no_agent(self):
        node = {"order": {"channelSnapshot": {"id": "ch", "name": "Acme", "agent": None}}}
        assert from_booking_node(node).reseller_name == "Acme"

    def test_omits_price_breakdown_and_guests_when_not_requested(self):
        booking = from_booking_node(full_node(), False, False)
        assert booking.convenience_fee is None
        assert booking.guests is None
        # Ticket list/total prices are part of the breakdown and stay off too.
        assert booking.tickets[0].list_price is None
        assert booking.tickets[0].total_value is None

    def test_falls_back_gracefully_for_present_but_empty_nested_fields(self):
        node: dict[str, Any] = {
            "id": "b",
            "ticketQuantities": [{}],
            "tips": [{}],
            "value": {},
            "order": {"channelSnapshot": {"id": "ch", "agent": {}}},
            "resourcePoolAssignments": [{"resourceAssignments": [{}]}],
            "tickets": [{"questionAnswers": [{"questionText": "q"}]}],
        }
        booking = from_booking_node(node, False, True)

        assert booking.total_tickets == 0
        assert booking.ticket_description == "0x Unknown"
        assert booking.tickets == [
            Ticket(
                name="Unknown", quantity=0, ticket_id="unknown", list_price=None, total_value=None
            )
        ]
        assert booking.tips == [Price(display="", amount="")]
        assert booking.resources == [Resource(quantity=0, name="", short_name="")]
        assert booking.resource_pool_assignments == [ResourcePoolAssignment(id="", name="")]
        assert booking.value_display == ""
        assert booking.reseller_name == ""
        assert booking.custom_guest_question_answers == []
        assert booking.convenience_fee is None

    def test_omits_question_coordinates_when_the_location_is_incomplete(self):
        node = {
            "questionAnswers": [
                {
                    "answer": "a",
                    "questionText": "q",
                    "questionLocationSnapshot": {"latitude": "1.0"},
                }
            ]
        }
        assert from_booking_node(node).custom_question_answers == [
            CustomQuestionAnswer(question="q", answer="a")
        ]

    def test_duration_is_zero_when_a_timestamp_cannot_be_parsed_or_zones_mismatch(self):
        assert (
            from_booking_node(
                {"startsAt": "not-a-date", "endsAt": "2026-01-02T11:30:00Z"}
            ).duration_min
            == 0
        )
        assert (
            from_booking_node(
                {"startsAt": "2026-01-02T10:00:00", "endsAt": "2026-01-02T11:30:00Z"}
            ).duration_min
            == 0
        )

    def test_guest_date_of_birth_is_none_when_unparseable(self):
        booking = from_booking_node({"bookingGuests": [{"id": "g", "dateOfBirth": "bogus"}]}, True)
        assert booking.guests is not None
        assert booking.guests[0].date_of_birth is None


class TestConvertGuests:
    def test_appends_the_primary_guest_when_not_already_present(self):
        guests = convert_guests(
            {
                "primaryGuest": {"id": "p1", "name": "Primary"},
                "bookingGuests": [{"id": "g2", "name": "Other"}],
            }
        )
        assert [(g.id, g.is_primary) for g in guests] == [("g2", False), ("p1", True)]

    def test_returns_an_empty_list_when_there_are_no_guests_and_no_primary_id(self):
        assert convert_guests({}) == []
