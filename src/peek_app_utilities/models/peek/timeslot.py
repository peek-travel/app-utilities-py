"""The clean data model for Peek Pro timeslots and timeslot operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

TimeslotFilter = Literal["all", "withBookings", "withoutBookings"]
"""Booking filter for :class:`Timeslot` day queries."""

GUIDE_ASSIGNMENT_ACTIONS: Final[tuple[str, ...]] = ("assign", "unassign")
"""Every action a :class:`GuideAssignment` accepts."""

GuideAssignmentAction = Literal["assign", "unassign"]
"""Whether a :class:`GuideAssignment` assigns or unassigns guides."""

AssignGuideStatus = Literal["success", "error"]
"""Outcome of a guide (un)assignment request."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedResource:
    """A resource allocated to a :class:`Timeslot`."""

    name: str
    """Resource pool name."""
    capacity: int
    """Resource pool capacity."""
    category: str
    """Resource pool category (e.g. ``"guide"``)."""
    quantity: int
    """Allocated quantity."""
    account_user_id: str | None
    """Backing account user id, or ``None``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Timeslot:
    """A bookable timeslot for an activity."""

    id: str
    """Unique identifier."""
    product_id: str
    """The activity (product) id this timeslot belongs to."""
    total_capacity: int
    """Total capacity of the timeslot."""
    available_capacity: int
    """Remaining available capacity."""
    max_party_size: int
    """Maximum party size per booking."""
    booking_count: int
    """Number of bookings on the timeslot."""
    checked_in_count: int
    """Number of checked-in guests."""
    status: str
    """Status reported by Peek (e.g. open/closed)."""
    notes: str | None
    """Manifest notes, or ``None``."""
    duration_min: int
    """Duration in minutes."""
    date: str
    """Date (``YYYY-MM-DD``)."""
    start_time: str | None
    """Start time, or ``None``."""
    assigned_resources: list[AssignedResource]
    """Resources (e.g. guides, equipment) allocated to this timeslot."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateTimeslotResult:
    """Result of a timeslot update (set availability / notes)."""

    manifest_notes: str | None
    status: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GuideAssignment:
    """Input describing a guide (un)assignment across timeslots."""

    timeslot_ids: Sequence[str]
    """Timeslots to (un)assign."""
    guide_ids: Sequence[str]
    """Guides to (un)assign — matched by resource-pool id, account-user id, or name."""
    action: GuideAssignmentAction
    """Whether to assign or unassign."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignGuideError:
    """A single error reported by a failed guide (un)assignment."""

    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignGuideResult:
    """Result of a guide (un)assignment request."""

    status: AssignGuideStatus
    resource_allocation_request_id: str | None
    """The created allocation request id on success, else ``None``."""
    errors: list[AssignGuideError] | None
    """Error details on failure, else ``None``."""
