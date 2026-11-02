import re

from peek_app_utilities.internal.peek.bookings.booking_queries import (
    build_booking_guests_query,
    build_bookings_listing_query,
    build_bookings_variables,
    normalize_booking_id,
)


def collapse(query: str) -> str:
    """Collapses whitespace so selection sets can be matched regardless of layout."""
    return re.sub(r"\s+", " ", query).strip()


class TestBuildBookingsListingQuery:
    def test_injects_the_per_ticket_value_selection_when_the_price_breakdown_is_requested(self):
        query = collapse(build_bookings_listing_query(False, True))
        assert (
            "ticketQuantities { value { price { amount formatted } total { amount formatted } }"
            in query
        )
        # The booking-level breakdown still lands on the booking node's `value`.
        assert "value { convenienceFee { amount formatted }" in query

    def test_omits_the_per_ticket_value_selection_when_the_breakdown_is_not_requested(self):
        query = collapse(build_bookings_listing_query(False, False))
        assert "ticketQuantities { quantity resourceOptionSnapshot" in query
        assert "ticketQuantities { value {" not in query
        assert "convenienceFee" not in query

    def test_requests_customer_pii_fields_when_full_customer_access_is_true(self):
        query = collapse(build_bookings_listing_query(True, False, True))
        assert "primaryGuest { name email phone" in query
        assert "bookingPortalUrl" in query
        assert "questionAnswers {" in query
        assert "questionLocationSnapshot { latitude longitude }" in query
        # Guest identity fields present in the guests section.
        assert "bookingGuests { id name country dateOfBirth email" in query
        assert "fieldResponses {" in query

    def test_omits_all_customer_pii_fields_when_full_customer_access_is_false(self):
        query = collapse(build_bookings_listing_query(True, False, False))
        # No primary-guest identity block, portal URL, or custom question answers.
        assert "primaryGuest { name" not in query
        assert "bookingPortalUrl" not in query
        assert "questionAnswers {" not in query
        assert "questionLocationSnapshot" not in query
        assert "fieldResponses {" not in query
        assert "dateOfBirth" not in query
        # Operator-facing + structural fields still present.
        assert "operatorNotes" in query
        assert "operatorStatus" in query
        assert "resourcePoolAssignments {" in query
        # Guests section keeps only ids + participation/opt-in flags.
        assert "bookingGuests { id isParticipant optinSms optinMarketing }" in query


class TestBuildBookingGuestsQuery:
    def test_selects_guest_identity_fields_when_full_customer_access_is_true(self):
        query = collapse(build_booking_guests_query(True))
        assert "bookingGuests { id name country dateOfBirth email isGdpr" in query
        assert "phone postalCode fieldResponses {" in query

    def test_selects_only_ids_and_flags_when_full_customer_access_is_false(self):
        query = collapse(build_booking_guests_query(False))
        assert "bookingGuests { id isParticipant optinSms optinMarketing }" in query
        assert "primaryGuest { id isParticipant optinSms optinMarketing }" in query
        assert "name" not in query
        assert "email" not in query
        assert "fieldResponses" not in query


class TestBuildBookingsVariables:
    def test_normalizes_booking_id(self):
        assert normalize_booking_id("B-ABC-123") == "b_abc_123"

    def test_booking_id_takes_precedence_over_timeslot_and_range(self):
        variables = build_bookings_variables(
            page_size=10, after=None, booking_id="B-1", timeslot_id="ts", product_id="p"
        )
        assert variables["filter"] == {"bookingFilter": {"ids": ["b_1"]}}
        assert variables["first"] == 10
        assert variables["after"] is None
        assert variables["orderBy"] == {"direction": "ASC", "field": "STARTS_AT"}

    def test_timeslot_filter_ignores_product_id(self):
        variables = build_bookings_variables(
            page_size=1, after="c", timeslot_id="ts", product_id="p"
        )
        assert variables["filter"] == {"bookingFilter": {"timeslotRefid": "ts"}}
        assert variables["after"] == "c"

    def test_no_search_by_leaves_the_range_out(self):
        variables = build_bookings_variables(
            page_size=1, after=None, start_date_time="a", end_date_time="b", product_id="p"
        )
        assert variables["filter"] == {"bookingFilter": {"activityIds": ["p"]}}
