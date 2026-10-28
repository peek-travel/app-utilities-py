import json
from typing import Any

from peek_app_utilities.internal.peek.bookings.booking_webhook import (
    BOOKING_WEBHOOK_GQL_QUERY,
    parse_booking_webhook,
)
from peek_app_utilities.models.peek.booking import Price

# The exact selection set that must be registered with the live booking webhook
# (the external `output_fields_gql_query` config — e.g. the connector's
# `app.json`). This is the cross-system contract: if a field change here is
# intentional, update this snapshot AND the external config + `docs/webhooks.md`;
# if it is accidental, this catches it before release.
REGISTERED_WEBHOOK_QUERY = "{ displayId id primaryGuest { name email phone optinMarketing optinSms isGdpr postalCode } activitySnapshot { type name id } ticketQuantities { quantity resourceOptionSnapshot { name id } } reservationStatus checkinStatus returnStatus fulfillmentStatusOverride { status } timeSnapshot { id legacyId } purchasedAt purchasedAtUtc startsAt startsAtUtc endsAt endsAtUtc availabilityTimeId bookingPortalUrl operatorNotes operatorStatus value { convenienceFee { amount formatted } deposit { amount formatted } discount { amount formatted } discountedPrice { amount formatted } fees { amount formatted } flatPartnerFee { amount formatted } price { amount formatted } retailPrice { amount formatted } taxes { amount formatted } tips { amount formatted } total { formatted amount } } balance { total { amount formatted } } tips { price { amount formatted } } order { displayId id promoCodes { code } channelSnapshot { id name agent { name } } initialQuote { source { actor { app name } } } } questionAnswers { answer questionText questionLocationSnapshot { latitude longitude } } tickets { questionAnswers { answer questionText } } resourcePoolAssignments { quantity resourcePool { name shortName resources { name } } resourceAssignments { resource { id name } } } bookingGuests { id name country dateOfBirth email isGdpr isParticipant optinSms optinMarketing phone postalCode fieldResponses { id text fieldLocation { field { name } } } } primaryGuest { id name country dateOfBirth email isGdpr isParticipant optinSms optinMarketing phone postalCode fieldResponses { id text fieldLocation { field { name } } } } }"


def webhook_node() -> dict[str, Any]:
    return {
        "id": "b_1",
        "displayId": "B-1",
        "primaryGuest": {"id": "g1", "name": "Ada", "email": "ada@example.com", "phone": "+1"},
        "activitySnapshot": {"type": "RENTAL", "name": "Kayak", "id": "act-1"},
        "ticketQuantities": [
            {"quantity": 2, "resourceOptionSnapshot": {"name": "Adult", "id": "r1"}}
        ],
        "reservationStatus": "CONFIRMED",
        "checkinStatus": "NONE",
        "returnStatus": "NONE",
        "value": {"total": {"amount": "100.00", "formatted": "$100.00"}},
        "balance": {"total": {"amount": "0.00", "formatted": "$0.00"}},
        "order": {"id": "o_1", "initialQuote": {"source": {"actor": {"app": "WIDGET"}}}},
    }


class TestBookingWebhookGqlQuery:
    def test_is_a_single_line_paste_ready_selection_set(self):
        assert BOOKING_WEBHOOK_GQL_QUERY.startswith("{")
        assert BOOKING_WEBHOOK_GQL_QUERY.endswith("}")
        assert "\n" not in BOOKING_WEBHOOK_GQL_QUERY
        assert "  " not in BOOKING_WEBHOOK_GQL_QUERY

    def test_is_the_maximal_selection_guests_and_price_breakdown(self):
        assert "bookingGuests {" in BOOKING_WEBHOOK_GQL_QUERY
        assert "fieldResponses {" in BOOKING_WEBHOOK_GQL_QUERY
        assert "taxes { amount formatted }" in BOOKING_WEBHOOK_GQL_QUERY
        assert "retailPrice { amount formatted }" in BOOKING_WEBHOOK_GQL_QUERY

    def test_matches_the_query_registered_with_the_live_webhook_drift_guard(self):
        assert BOOKING_WEBHOOK_GQL_QUERY == REGISTERED_WEBHOOK_QUERY


class TestParseBookingWebhook:
    def test_parses_the_booking_envelope_into_a_booking(self):
        booking = parse_booking_webhook({"booking": webhook_node()})
        assert booking.booking_id == "b_1"
        assert booking.display_id == "B-1"
        assert booking.source == "website"
        assert booking.customer_name == "Ada"

    def test_parses_a_bare_booking_node_no_envelope(self):
        assert parse_booking_webhook(webhook_node()).booking_id == "b_1"

    def test_parses_a_json_string_body(self):
        assert parse_booking_webhook(json.dumps({"booking": webhook_node()})).booking_id == "b_1"

    def test_auto_detects_guests_when_the_payload_carries_them(self):
        node = webhook_node()
        node["bookingGuests"] = [{"id": "g1", "name": "Ada", "email": "ada@example.com"}]
        booking = parse_booking_webhook({"booking": node})
        assert booking.guests is not None
        assert len(booking.guests) == 1

    def test_omits_guests_when_the_payload_does_not_carry_them(self):
        assert parse_booking_webhook({"booking": webhook_node()}).guests is None

    def test_auto_detects_the_price_breakdown_when_the_payload_carries_it(self):
        node = webhook_node()
        node["value"] = {
            "total": {"amount": "100.00", "formatted": "$100.00"},
            "taxes": {"amount": "8.00", "formatted": "$8.00"},
        }
        booking = parse_booking_webhook({"booking": node})
        assert booking.taxes == Price(amount="8.00", display="$8.00")

    def test_omits_the_price_breakdown_when_only_the_total_is_present(self):
        assert parse_booking_webhook({"booking": webhook_node()}).taxes is None

    def test_omits_the_price_breakdown_when_value_is_not_an_object(self):
        node = webhook_node()
        node["value"] = None
        assert parse_booking_webhook({"booking": node}).taxes is None

    def test_returns_an_empty_ish_booking_for_malformed_input_rather_than_raising(self):
        parse_booking_webhook(None)
        parse_booking_webhook("not json")
        parse_booking_webhook([1, 2])
        assert parse_booking_webhook(None).booking_id == ""
        assert parse_booking_webhook("not json").booking_id == ""
