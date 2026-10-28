from typing import Any

from peek_app_utilities.internal.peek.bookings.booking_guest_converter import (
    from_booking_guests_response,
)


def response(node: dict[str, Any]) -> dict[str, Any]:
    return {"sales": {"edges": [{"node": node}]}}


class TestFromBookingGuestsResponse:
    def test_merges_booking_guests_and_flags_the_primary(self):
        guests = from_booking_guests_response(
            response(
                {
                    "displayId": "B-1",
                    "id": "b_1",
                    "primaryGuest": {"id": "g1"},
                    "bookingGuests": [{"id": "g1"}, {"id": "g2"}],
                }
            )
        )
        assert [(g.id, g.is_primary) for g in guests] == [("g1", True), ("g2", False)]

    def test_appends_the_primary_guest_when_missing_from_booking_guests(self):
        guests = from_booking_guests_response(
            response(
                {
                    "displayId": "B-1",
                    "id": "b_1",
                    "primaryGuest": {"id": "p1"},
                    "bookingGuests": [{"id": "g2"}],
                }
            )
        )
        assert [g.id for g in guests] == ["g2", "p1"]

    def test_returns_an_empty_list_when_the_booking_has_no_guests_at_all(self):
        assert from_booking_guests_response(response({"displayId": "B-1", "id": "b_1"})) == []

    def test_returns_an_empty_list_when_there_are_no_edges(self):
        assert from_booking_guests_response({"sales": {"edges": []}}) == []
        assert from_booking_guests_response(None) == []
