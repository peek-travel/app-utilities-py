"""Resolves the dedicated guests query into a merged guest list (booking guests
plus the primary guest when not already present). Pure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from peek_app_utilities.internal.peek.bookings.booking_converter import map_guest_node
from peek_app_utilities.models.peek.booking import Guest


def from_booking_guests_response(response: Mapping[str, Any] | None) -> list[Guest]:
    """Maps a booking-guests response into a :class:`Guest` list."""
    sales = (response or {}).get("sales") or {}
    edges = sales.get("edges") or []
    if not edges:
        return []

    booking_node: Mapping[str, Any] = (edges[0] or {}).get("node") or {}
    primary_guest_node = booking_node.get("primaryGuest")
    raw_guests = booking_node.get("bookingGuests")
    booking_guest_nodes: list[Mapping[str, Any]] = (
        raw_guests if isinstance(raw_guests, list) else []
    )
    primary_id = (primary_guest_node or {}).get("id")

    guests = [
        map_guest_node(guest_node, bool(primary_id) and guest_node.get("id") == primary_id)
        for guest_node in booking_guest_nodes
    ]

    has_primary_in_guests = bool(primary_id) and any(
        guest.get("id") == primary_id for guest in booking_guest_nodes
    )
    if not has_primary_in_guests and primary_guest_node:
        guests.append(map_guest_node(primary_guest_node, True))

    return guests
