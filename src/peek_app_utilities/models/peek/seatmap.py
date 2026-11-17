"""The clean data model for a Peek Pro seating map.

A seating map describes the physical layout a product sells seats against: a
set of :class:`SeatmapZone` pricing tiers (each mapping to one or more bookable
tickets) and a tree of :class:`SeatmapSection` → :class:`SeatmapGroup` (tables)
→ :class:`SeatmapBlock` (individual seats). Every rendered element carries a
shared :class:`SeatmapDisplay` describing where and how to draw it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

SEATMAP_DISPLAY_TYPES: Final[tuple[str, ...]] = ("SHAPE", "SECTION", "LABEL")
"""The kinds of section a :attr:`SeatmapDisplay.type` can describe. The API owns
this set; a non-``None`` value outside it makes the converter raise
``UnknownSeatmapDisplayTypeError`` rather than silently widen the type.

- ``"SECTION"`` — a seatable section containing groups (tables) of blocks.
- ``"SHAPE"`` — a non-seatable decorative shape (e.g. a stage).
- ``"LABEL"`` — a free-text label drawn on the map.
"""

SeatmapDisplayType = Literal["SHAPE", "SECTION", "LABEL"]
"""A known :attr:`SeatmapDisplay.type` value. See :data:`SEATMAP_DISPLAY_TYPES`."""

SEATMAP_BLOCK_STATUSES: Final[tuple[str, ...]] = ("AVAILABLE", "OCCUPIED", "BLOCKED")
"""Occupancy status of a seat over a queried datetime range. The API owns this
set; a value outside it makes ``SeatmapService.get_seat_map_assignments`` raise
``UnknownSeatmapBlockStatusError``."""

SeatmapBlockStatus = Literal["AVAILABLE", "OCCUPIED", "BLOCKED"]
"""A known seat occupancy status. See :data:`SEATMAP_BLOCK_STATUSES`."""

SEATMAP_OCCUPANT_TYPES: Final[tuple[str, ...]] = ("GUEST", "ACCOUNT_USER", "FIELD_LOCATION")
"""What kind of occupant holds a seat, derived from the assignment's parent type.
An unrecognized parent makes ``SeatmapService.get_seat_map_assignments`` raise
``UnknownSeatmapAssignmentParentError``."""

SeatmapOccupantType = Literal["GUEST", "ACCOUNT_USER", "FIELD_LOCATION"]
"""A known seat occupant kind. See :data:`SEATMAP_OCCUPANT_TYPES`."""

ASSIGNMENT_STATUSES: Final[tuple[str, ...]] = ("SUCCESS", "PARTIAL", "FAILED")
"""The outcome of a bulk :class:`SeatmapBlockAssignment` request: ``"SUCCESS"``
when every assignment succeeded, ``"FAILED"`` when every one failed,
``"PARTIAL"`` when some of each. Only per-assignment failures are reflected
here — transport/GraphQL errors still raise."""

AssignmentStatus = Literal["SUCCESS", "PARTIAL", "FAILED"]
"""A bulk-assignment outcome status. See :data:`ASSIGNMENT_STATUSES`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapDisplay:
    """The display geometry shared by sections, groups (tables), and blocks (seats).

    The same shape is used in all three positions, but the API populates
    different fields in each: only :attr:`x`/:attr:`y` are always present. Every
    other field is ``None`` wherever the map element does not carry it
    (``table``/``table_width``/``table_height`` are populated only on a group's
    display; ``label``/``width``/``height``/``type`` only on a section's display;
    a block's display carries only ``x``/``y``).
    """

    x: float
    """X coordinate of the element, in map units. Always present."""
    y: float
    """Y coordinate of the element, in map units. Always present."""
    width: float | None
    """Width of the element, or ``None`` where not applicable (sections only)."""
    height: float | None
    """Height of the element, or ``None`` where not applicable (sections only)."""
    table_width: float | None
    """Table width, or ``None`` where not applicable (groups only)."""
    table_height: float | None
    """Table height, or ``None`` where not applicable (groups only)."""
    table: bool | None
    """Whether the group is drawn as a table, or ``None`` where not applicable (groups only)."""
    label: str | None
    """Free-text label, or ``None`` where not applicable (sections only)."""
    type: SeatmapDisplayType | None
    """The section kind, or ``None`` where not applicable (sections only). A
    non-``None`` value is always one of :data:`SEATMAP_DISPLAY_TYPES`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapTicket:
    """A bookable ticket (resource option) a :class:`SeatmapZone` sells seats as —
    the same id passed as a ticket's ``resource_option_id`` when creating a booking."""

    id: str
    """Unique identifier of the ticket / resource option."""
    name: str
    """Human-readable name of the ticket (e.g. ``"Adult - Premium"``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapZone:
    """A pricing tier on the map. Every block belongs to a zone (via
    :attr:`SeatmapBlock.zone_id`), and each zone maps to the
    :class:`SeatmapTicket` s its seats can be sold as."""

    id: str
    """Unique identifier of the zone."""
    name: str
    """Human-readable name of the zone (e.g. ``"Premium"``)."""
    color_hex: str | None
    """The zone's display color as a hex string (e.g. ``"#ff0000"``), or ``None``
    when the API reports no color for the zone."""
    tickets: list[SeatmapTicket]
    """The tickets (resource options) this zone sells seats as."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapBlock:
    """A single seat within a :class:`SeatmapGroup` (table)."""

    id: str
    """Unique identifier of the block (seat)."""
    name: str
    """Short seat name within its table (e.g. ``"1"``, ``"O-2"``)."""
    full_block_name: str
    """Fully qualified seat name (e.g. ``"Table 12, Seat 1"``)."""
    order: int
    """Position of the seat within its table, zero-based."""
    zone_id: str | None
    """The :class:`SeatmapZone` this seat belongs to, or ``None`` when the API
    reports the seat as unassigned to any zone."""
    display: SeatmapDisplay
    """Where to draw the seat. Only ``x``/``y`` are populated on a block."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapGroup:
    """A group of :class:`SeatmapBlock` s — typically a single table of seats."""

    id: str
    """Unique identifier of the group."""
    name: str
    """Human-readable name of the group (e.g. ``"Table 12"``)."""
    assignable_to: list[str]
    """The audience(s) this group's seats can be assigned to (e.g. ``["GUEST"]``).
    The API owns these values; the model keeps them as raw strings."""
    blocks: list[SeatmapBlock]
    """The seats in this group."""
    display: SeatmapDisplay
    """Where to draw the group. ``x``/``y`` plus the ``table``/``table_width``/
    ``table_height`` fields are populated on a group."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapSection:
    """A top-level region of the map: a seatable section, a shape, or a label."""

    id: str
    """Unique identifier of the section."""
    display: SeatmapDisplay
    """Where and how to draw the section. ``x``/``y`` plus the
    ``label``/``width``/``height``/``type`` fields are populated on a section."""
    groups: list[SeatmapGroup]
    """The groups (tables) in this section; empty for shapes and labels."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Seatmap:
    """A complete seating map configured on a product."""

    id: str
    """Unique identifier of the seating map (e.g. ``"csm_8j734"``)."""
    name: str
    """Human-readable name of the seating map."""
    zones: list[SeatmapZone]
    """The pricing tiers on the map."""
    sections: list[SeatmapSection]
    """The top-level sections, shapes, and labels on the map."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapSummary:
    """A lightweight summary of a seating map — just its identity, without the
    zones and section/group/block layout a full :class:`Seatmap` carries.
    Returned by ``SeatmapService.get_seatmap_ids_for_product``."""

    id: str
    """Unique identifier of the seating map (e.g. ``"csm_8j734"``)."""
    name: str
    """Human-readable name of the seating map."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapAssignment:
    """A single occupant of a seat for the queried datetime range. A seat can
    carry more than one assignment across a range that spans multiple slots.

    The booking-derived fields are populated only when :attr:`occupied_by` is
    ``"GUEST"``; they are ``None`` for every other occupant. :attr:`guest_name`
    is populated for a ``"GUEST"`` (the booking's primary guest) and for an
    ``"ACCOUNT_USER"`` (the staff member's name), and is ``None`` for a
    ``"FIELD_LOCATION"``. A guest name is **customer PII**: when the owning
    access service was created without ``full_customer_access``, a ``"GUEST"``
    occupant's ``guest_name`` is always ``None`` (it is never requested).
    """

    occupied_by: SeatmapOccupantType
    """The kind of occupant holding the seat."""
    booking_id: str | None
    """Booking id (GUEST only), else ``None``."""
    booking_display_id: str | None
    """Human-facing booking display id (GUEST only), else ``None``."""
    product_id: str | None
    """Product (activity) id from the booking snapshot (GUEST only), else ``None``."""
    product_name: str | None
    """Product (activity) name from the booking snapshot (GUEST only), else ``None``."""
    ticket_id: str | None
    """Ticket (resource-option) id from the snapshot (GUEST only), else ``None``."""
    ticket_name: str | None
    """Ticket (resource-option) name from the snapshot (GUEST only), else ``None``."""
    guest_name: str | None
    """Occupant name: the booking's primary guest (GUEST) or the staff member
    (ACCOUNT_USER); ``None`` for a FIELD_LOCATION, and ``None`` for a GUEST when
    ``full_customer_access`` is off."""
    starts_at: str | None
    """Booking start, naive datetime (GUEST only), else ``None``."""
    ends_at: str | None
    """Booking end, naive datetime (GUEST only), else ``None``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedSeatmapBlock(SeatmapBlock):
    """A seat enriched with its occupancy over a queried datetime range. Returned
    (nested under :class:`AssignedSeatmap`) by
    ``SeatmapService.get_seat_map_assignments``. Extends :class:`SeatmapBlock`
    with the two assignment fields; the plain ``get_seatmap_for_product`` read
    returns the base :class:`SeatmapBlock` without them."""

    status: SeatmapBlockStatus
    """Occupancy status of the seat for the queried range."""
    assigned_to: list[SeatmapAssignment]
    """The occupants of the seat across the range. Empty unless ``status`` is ``"OCCUPIED"``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedSeatmapGroup:
    """A :class:`SeatmapGroup` whose blocks carry assignment data."""

    id: str
    """Unique identifier of the group."""
    name: str
    """Human-readable name of the group (e.g. ``"Table 12"``)."""
    assignable_to: list[str]
    """The audience(s) this group's seats can be assigned to (e.g. ``["GUEST"]``)."""
    blocks: list[AssignedSeatmapBlock]
    """The seats in this group, enriched with occupancy."""
    display: SeatmapDisplay
    """Where to draw the group."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedSeatmapSection:
    """A :class:`SeatmapSection` whose groups carry assignment data."""

    id: str
    """Unique identifier of the section."""
    display: SeatmapDisplay
    """Where and how to draw the section."""
    groups: list[AssignedSeatmapGroup]
    """The groups (tables) in this section, enriched with occupancy."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedSeatmap:
    """A :class:`Seatmap` whose seats carry occupancy for a queried datetime
    range. Returned by ``SeatmapService.get_seat_map_assignments``."""

    id: str
    """Unique identifier of the seating map (e.g. ``"csm_8j734"``)."""
    name: str
    """Human-readable name of the seating map."""
    zones: list[SeatmapZone]
    """The pricing tiers on the map."""
    sections: list[AssignedSeatmapSection]
    """The sections of the map, enriched with occupancy."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrentSeatAssignment:
    """The seat a bookable ticket is currently assigned to, when it has one.
    Returned on an :class:`AssignableTicket` by ``SeatmapService.assignable_bookings``."""

    assignment_id: str
    """The seating-assignment record id — starts with ``asa_``."""
    block_id: str | None
    """The assigned seat (block) id, or ``None`` when the API omits the block."""
    block_name: str | None
    """The assigned seat's full name (e.g. ``"Table 12, Seat 1"``), or ``None``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignableTicket:
    """A bookable ticket on an :class:`AssignableBooking` — the unit that gets
    assigned to a seat. :attr:`currently_assigned_to` is ``None`` when the ticket
    has no seat yet (the assignable case)."""

    assignable_id: str
    """The ticket's stable assignment handle (its ``hashid``) — starts with ``t_``."""
    ticket_id: str | None
    """The ticket's resource-option id (from the snapshot), or ``None``."""
    ticket_name: str | None
    """The ticket's resource-option name (from the snapshot), or ``None``."""
    currently_assigned_to: CurrentSeatAssignment | None
    """The seat this ticket currently holds, or ``None`` when unassigned."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignableBooking:
    """A confirmed booking overlapping a queried datetime range, with the tickets
    that can be assigned to seats. Returned by ``SeatmapService.assignable_bookings``.

    :attr:`guest_name` is **customer PII**: when the owning access service was
    created without ``full_customer_access`` it is always ``None`` (never requested).
    """

    id: str
    """The booking id."""
    display_id: str
    """Human-facing booking display id."""
    starts_at: str | None
    """Booking start, naive datetime (fractional seconds stripped), or ``None``."""
    ends_at: str | None
    """Booking end, naive datetime (fractional seconds stripped), or ``None``."""
    notes: str
    """Operator-facing booking notes; empty string when none."""
    guest_name: str | None
    """Primary guest name, or ``None`` (also ``None`` when ``full_customer_access`` is off)."""
    assignable_tickets: list[AssignableTicket]
    """The booking's tickets that can be assigned to seats."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SeatmapBlockAssignment:
    """One seat assignment to request: bind a bookable ticket (``assignable_id``,
    a ``t_…`` ticket handle) to a seat (``block_id``, a ``csb_…`` block). Input to
    ``SeatmapService.assign_tickets_to_seats``."""

    assignable_id: str
    """The ticket handle to assign (must start with ``t_``)."""
    block_id: str
    """The seat (block) id to assign it to (must start with ``csb_``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SuccessfulAssignment:
    """A ticket that was successfully assigned to a seat, pairing the requested
    ticket handle with the created seating-assignment record."""

    assignable_id: str
    """The requested ticket handle (a ``t_…``, from the ticket's ``hashid``)."""
    assignment_id: str
    """The created seating-assignment record id (an ``asa_…``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignmentResponse:
    """The result of ``SeatmapService.assign_tickets_to_seats``."""

    status: AssignmentStatus
    """Overall outcome across all requested assignments."""
    successful_assignments: list[SuccessfulAssignment]
    """The tickets that were assigned successfully, with their new assignment ids."""
    failed_assignments: list[str]
    """The ``assignable_id`` s that failed to assign (per-assignment errors)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DeletedSeatAssignment:
    """A seat assignment that was just deleted by
    ``SeatmapService.delete_seat_assignments`` — returned so callers can reload
    state without a refetch."""

    assignment_id: str
    """The (now-deleted) seating-assignment record id — starts with ``asa_``."""
    block_id: str | None
    """The seat (block) id it occupied, or ``None`` when the API omits the block."""
    block_name: str | None
    """The seat's full name (e.g. ``"Table 12, Seat 1"``), or ``None``."""
    ticket_hash_id: str | None
    """The freed ticket's ``hashid`` (starts with ``t_``) when the parent is a ticket, else ``None``."""
