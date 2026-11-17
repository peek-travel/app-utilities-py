"""Pure functions mapping raw seating-map nodes into the clean :class:`Seatmap`
models. No I/O.

The one failure mode is an unrecognized API-owned enum value: a non-``None``
section ``display.type`` outside :data:`SEATMAP_DISPLAY_TYPES` raises
``UnknownSeatmapDisplayTypeError``, an unknown seat ``availability.status``
raises ``UnknownSeatmapBlockStatusError``, and an unknown assignment parent
``__typename`` raises ``UnknownSeatmapAssignmentParentError`` — rather than
silently widening the clean model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, cast

from peek_app_utilities.errors import (
    UnknownSeatmapAssignmentParentError,
    UnknownSeatmapBlockStatusError,
    UnknownSeatmapDisplayTypeError,
)
from peek_app_utilities.internal.peek.seatmaps.seatmap_queries import (
    ASSIGNMENT_SUCCESS_TYPENAME,
    PARENT_ACCOUNT_USER,
    PARENT_BLOCKED_SEAT,
    PARENT_FIELD_LOCATION,
    PARENT_TICKET,
    SEATMAP_ASSIGNMENT_PARENTS,
    RawAssignableBooking,
    RawAssignableSeatingAssignment,
    RawAssignableTicket,
    RawAssignedSeatmapBlock,
    RawAssignedSeatmapGroup,
    RawAssignedSeatmapNode,
    RawAssignedSeatmapSection,
    RawDeletedAssignment,
    RawSeatmapAssignment,
    RawSeatmapBlock,
    RawSeatmapDisplay,
    RawSeatmapGroup,
    RawSeatmapNode,
    RawSeatmapPrimaryGuest,
    RawSeatmapSection,
    RawSeatmapSummaryNode,
    RawSeatmapZone,
    assign_blocks_alias,
)
from peek_app_utilities.models.peek.seatmap import (
    SEATMAP_BLOCK_STATUSES,
    SEATMAP_DISPLAY_TYPES,
    AssignableBooking,
    AssignableTicket,
    AssignedSeatmap,
    AssignedSeatmapBlock,
    AssignedSeatmapGroup,
    AssignedSeatmapSection,
    AssignmentResponse,
    AssignmentStatus,
    CurrentSeatAssignment,
    DeletedSeatAssignment,
    Seatmap,
    SeatmapAssignment,
    SeatmapBlock,
    SeatmapBlockAssignment,
    SeatmapBlockStatus,
    SeatmapDisplay,
    SeatmapDisplayType,
    SeatmapGroup,
    SeatmapOccupantType,
    SeatmapSection,
    SeatmapSummary,
    SeatmapTicket,
    SeatmapZone,
    SuccessfulAssignment,
)

OCCUPANT_GUEST: Final[SeatmapOccupantType] = "GUEST"
OCCUPANT_ACCOUNT_USER: Final[SeatmapOccupantType] = "ACCOUNT_USER"
OCCUPANT_FIELD_LOCATION: Final[SeatmapOccupantType] = "FIELD_LOCATION"

STATUS_OCCUPIED: Final = "OCCUPIED"
"""The seat status under which assignments are meaningful."""

ASSIGNMENT_STATUS_SUCCESS: Final[AssignmentStatus] = "SUCCESS"
ASSIGNMENT_STATUS_PARTIAL: Final[AssignmentStatus] = "PARTIAL"
ASSIGNMENT_STATUS_FAILED: Final[AssignmentStatus] = "FAILED"

_FRACTIONAL_SECONDS_RE: Final = re.compile(r"\.\d+")
_GUEST_NAME_SEPARATOR: Final = " "


# ─── Shared geometry / structure ──────────────────────────────────────────────


def _normalize_display_type(raw: str | None) -> SeatmapDisplayType | None:
    """Narrows a raw ``display.type`` to a known :data:`SeatmapDisplayType`.
    Absent/``None`` (the group and block positions, which never select ``type``)
    maps to ``None``; a non-``None`` value outside the known set raises."""
    if raw is None:
        return None
    if raw in SEATMAP_DISPLAY_TYPES:
        return cast("SeatmapDisplayType", raw)
    raise UnknownSeatmapDisplayTypeError(raw, SEATMAP_DISPLAY_TYPES)


def _to_display(raw: RawSeatmapDisplay) -> SeatmapDisplay:
    """Builds the shared :class:`SeatmapDisplay` from whichever subset of fields
    the API populated in this position — every field the position does not
    carry collapses to ``None``."""
    return SeatmapDisplay(
        x=raw.get("x", 0),
        y=raw.get("y", 0),
        width=raw.get("width"),
        height=raw.get("height"),
        table_width=raw.get("tableWidth"),
        table_height=raw.get("tableHeight"),
        table=raw.get("table"),
        label=raw.get("label"),
        type=_normalize_display_type(raw.get("type")),
    )


def _from_block(raw: RawSeatmapBlock) -> SeatmapBlock:
    return SeatmapBlock(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        full_block_name=raw.get("fullBlockName", ""),
        order=raw.get("order", 0),
        zone_id=(raw.get("zone") or {}).get("id"),
        display=_to_display(raw.get("display") or {}),
    )


def _from_group(raw: RawSeatmapGroup) -> SeatmapGroup:
    return SeatmapGroup(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        assignable_to=list(raw.get("assignableTo") or []),
        blocks=[_from_block(block) for block in raw.get("blocks") or []],
        display=_to_display(raw.get("display") or {}),
    )


def _from_section(raw: RawSeatmapSection) -> SeatmapSection:
    return SeatmapSection(
        id=raw.get("id", ""),
        display=_to_display(raw.get("display") or {}),
        groups=[_from_group(group) for group in raw.get("groups") or []],
    )


def _from_zone(raw: RawSeatmapZone) -> SeatmapZone:
    return SeatmapZone(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        color_hex=raw.get("colorHex"),
        tickets=[
            SeatmapTicket(id=option.get("id", ""), name=option.get("name", ""))
            for option in raw.get("resourceOptions") or []
        ],
    )


def _from_seatmap(raw: RawSeatmapNode) -> Seatmap:
    return Seatmap(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        zones=[_from_zone(zone) for zone in raw.get("zones") or []],
        sections=[_from_section(section) for section in raw.get("sections") or []],
    )


def from_seatmap_nodes(nodes: Iterable[RawSeatmapNode]) -> list[Seatmap]:
    """Converts the seating-map nodes from a response into :class:`Seatmap` s."""
    return [_from_seatmap(node) for node in nodes]


def from_seatmap_summary_nodes(nodes: Iterable[RawSeatmapSummaryNode]) -> list[SeatmapSummary]:
    """Converts the lightweight id/name seating-map nodes into :class:`SeatmapSummary` s."""
    return [SeatmapSummary(id=node.get("id", ""), name=node.get("name", "")) for node in nodes]


# ─── Seat assignments ─────────────────────────────────────────────────────────


def _normalize_status(raw: str | None) -> SeatmapBlockStatus:
    """Narrows a raw ``availability.status`` to a known :data:`SeatmapBlockStatus`,
    raising on an absent or unrecognized value."""
    if raw is not None and raw in SEATMAP_BLOCK_STATUSES:
        return cast("SeatmapBlockStatus", raw)
    raise UnknownSeatmapBlockStatusError(str(raw), SEATMAP_BLOCK_STATUSES)


def _strip_fractional_seconds(value: str | None) -> str | None:
    """Strips a fractional-seconds component from an API datetime so booking
    times read as ``YYYY-MM-DDTHH:MM:SS`` (e.g. ``…T19:00:00.000000`` →
    ``…T19:00:00``). Any other part (including a timezone, if present) is left
    untouched."""
    if value is None:
        return None
    return _FRACTIONAL_SECONDS_RE.sub("", value, count=1)


def _join_guest_name(first: str | None, last: str | None) -> str | None:
    """Joins a guest's first/last name, dropping blanks; ``None`` when nothing remains."""
    parts = [part.strip() for part in (first, last) if part]
    parts = [part for part in parts if part]
    return _GUEST_NAME_SEPARATOR.join(parts) if parts else None


def _guest_name(guest: RawSeatmapPrimaryGuest | None) -> str | None:
    """The joined primary-guest name, or ``None`` when the guest was not selected (PII off)."""
    if not guest:
        return None
    return _join_guest_name(guest.get("firstName"), guest.get("lastName"))


def _detail_free_assignment(
    occupied_by: SeatmapOccupantType, guest_name: str | None
) -> SeatmapAssignment:
    """An assignment with no booking detail (non-GUEST occupants)."""
    return SeatmapAssignment(
        occupied_by=occupied_by,
        booking_id=None,
        booking_display_id=None,
        product_id=None,
        product_name=None,
        ticket_id=None,
        ticket_name=None,
        guest_name=guest_name,
        starts_at=None,
        ends_at=None,
    )


def _from_assignment(raw: RawSeatmapAssignment) -> SeatmapAssignment | None:
    """Maps one raw assignment to a :class:`SeatmapAssignment`, keyed off the
    parent's ``__typename``. Returns ``None`` for a ``BlockedSeat`` parent (a
    block, not an occupant) and raises on an unknown typename."""
    parent = raw.get("parent") or {}
    typename = parent.get("__typename")
    if typename == PARENT_TICKET:
        booking = parent.get("booking") or {}
        snapshot = booking.get("activitySnapshot") or {}
        option = parent.get("resourceOptionSnapshot") or {}
        return SeatmapAssignment(
            occupied_by=OCCUPANT_GUEST,
            booking_id=booking.get("id"),
            booking_display_id=booking.get("displayId"),
            product_id=snapshot.get("id"),
            product_name=snapshot.get("name"),
            ticket_id=option.get("id"),
            ticket_name=option.get("name"),
            guest_name=_guest_name(booking.get("primaryGuest")),
            starts_at=_strip_fractional_seconds(booking.get("startsAt")),
            ends_at=_strip_fractional_seconds(booking.get("endsAt")),
        )
    if typename == PARENT_ACCOUNT_USER:
        return _detail_free_assignment(OCCUPANT_ACCOUNT_USER, parent.get("name"))
    if typename == PARENT_FIELD_LOCATION:
        return _detail_free_assignment(OCCUPANT_FIELD_LOCATION, None)
    if typename == PARENT_BLOCKED_SEAT:
        return None
    raise UnknownSeatmapAssignmentParentError(str(typename), SEATMAP_ASSIGNMENT_PARENTS)


def _from_assigned_block(raw: RawAssignedSeatmapBlock) -> AssignedSeatmapBlock:
    availability = raw.get("availability") or {}
    status = _normalize_status(availability.get("status"))
    # Assignments are meaningful only for an occupied seat; BlockedSeat parents
    # (and anything under a non-occupied status) drop out.
    assigned_to: list[SeatmapAssignment] = []
    if status == STATUS_OCCUPIED:
        for entry in availability.get("assignments") or []:
            converted = _from_assignment(entry)
            if converted is not None:
                assigned_to.append(converted)
    base = _from_block(raw)
    return AssignedSeatmapBlock(
        id=base.id,
        name=base.name,
        full_block_name=base.full_block_name,
        order=base.order,
        zone_id=base.zone_id,
        display=base.display,
        status=status,
        assigned_to=assigned_to,
    )


def _from_assigned_group(raw: RawAssignedSeatmapGroup) -> AssignedSeatmapGroup:
    return AssignedSeatmapGroup(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        assignable_to=list(raw.get("assignableTo") or []),
        blocks=[_from_assigned_block(block) for block in raw.get("blocks") or []],
        display=_to_display(raw.get("display") or {}),
    )


def _from_assigned_section(raw: RawAssignedSeatmapSection) -> AssignedSeatmapSection:
    return AssignedSeatmapSection(
        id=raw.get("id", ""),
        display=_to_display(raw.get("display") or {}),
        groups=[_from_assigned_group(group) for group in raw.get("groups") or []],
    )


def from_assigned_seatmap(raw: RawAssignedSeatmapNode) -> AssignedSeatmap:
    """Converts a raw seating-map node into an :class:`AssignedSeatmap`."""
    return AssignedSeatmap(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        zones=[_from_zone(zone) for zone in raw.get("zones") or []],
        sections=[_from_assigned_section(section) for section in raw.get("sections") or []],
    )


def from_assigned_seatmap_nodes(nodes: Iterable[RawAssignedSeatmapNode]) -> list[AssignedSeatmap]:
    """Converts the assignment-enriched seating-map nodes into :class:`AssignedSeatmap` s."""
    return [from_assigned_seatmap(node) for node in nodes]


# ─── Assignable bookings ──────────────────────────────────────────────────────


def _from_current_seat_assignment(raw: RawAssignableSeatingAssignment) -> CurrentSeatAssignment:
    block = raw.get("block") or {}
    return CurrentSeatAssignment(
        assignment_id=raw.get("id", ""),
        block_id=block.get("id"),
        block_name=block.get("fullBlockName"),
    )


def _from_assignable_ticket(raw: RawAssignableTicket) -> AssignableTicket:
    option = raw.get("resourceOptionSnapshot") or {}
    seating = raw.get("seatingAssignment")
    return AssignableTicket(
        assignable_id=raw.get("hashid", ""),
        ticket_id=option.get("id"),
        ticket_name=option.get("name"),
        currently_assigned_to=_from_current_seat_assignment(seating) if seating else None,
    )


def _from_assignable_booking(raw: RawAssignableBooking) -> AssignableBooking:
    return AssignableBooking(
        id=raw.get("id", ""),
        display_id=raw.get("displayId", ""),
        starts_at=_strip_fractional_seconds(raw.get("startsAt")),
        ends_at=_strip_fractional_seconds(raw.get("endsAt")),
        notes=raw.get("operatorNotes") or "",
        guest_name=_guest_name(raw.get("primaryGuest")),
        assignable_tickets=[_from_assignable_ticket(t) for t in raw.get("tickets") or []],
    )


def from_assignable_bookings(nodes: Iterable[RawAssignableBooking]) -> list[AssignableBooking]:
    """Converts the booking nodes from an assignable-bookings response into models."""
    return [_from_assignable_booking(node) for node in nodes]


# ─── Writes ───────────────────────────────────────────────────────────────────


def to_assignment_response(
    data: Mapping[str, Any], assignments: Sequence[SeatmapBlockAssignment]
) -> AssignmentResponse:
    """Classifies each requested assignment by its aliased result into an
    :class:`AssignmentResponse`: a result is successful only when its
    ``__typename`` is :data:`ASSIGNMENT_SUCCESS_TYPENAME` — every other member
    (the error unions, or a missing result) counts as a failure. ``status`` is
    ``SUCCESS``/``FAILED`` when all succeed/fail, else ``PARTIAL``."""
    successful: list[SuccessfulAssignment] = []
    failed: list[str] = []
    for i, assignment in enumerate(assignments):
        result = data.get(assign_blocks_alias(i)) or {}
        if result.get("__typename") == ASSIGNMENT_SUCCESS_TYPENAME:
            # One assignBlocks call binds one ticket to one block → one assignment;
            # the ticket handle comes back on the parent's hashid.
            created_list = result.get("assignments") or []
            created = created_list[0] if created_list else {}
            parent = created.get("parent") or {}
            successful.append(
                SuccessfulAssignment(
                    assignable_id=parent.get("hashid") or assignment.assignable_id,
                    assignment_id=created.get("id") or "",
                )
            )
        else:
            failed.append(assignment.assignable_id)
    if not failed:
        status = ASSIGNMENT_STATUS_SUCCESS
    elif not successful:
        status = ASSIGNMENT_STATUS_FAILED
    else:
        status = ASSIGNMENT_STATUS_PARTIAL
    return AssignmentResponse(
        status=status, successful_assignments=successful, failed_assignments=failed
    )


def from_deleted_assignments(nodes: Iterable[RawDeletedAssignment]) -> list[DeletedSeatAssignment]:
    """Converts the now-deleted assignment nodes into :class:`DeletedSeatAssignment` s."""
    deleted: list[DeletedSeatAssignment] = []
    for node in nodes:
        block = node.get("block") or {}
        parent = node.get("parent") or {}
        deleted.append(
            DeletedSeatAssignment(
                assignment_id=node.get("id", ""),
                block_id=block.get("id"),
                block_name=block.get("fullBlockName"),
                ticket_hash_id=parent.get("hashid"),
            )
        )
    return deleted
