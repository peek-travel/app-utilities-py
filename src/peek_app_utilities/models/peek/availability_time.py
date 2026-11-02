"""The clean data models for Peek Pro activity availability times.

``AvailabilityService.get_availability_times()`` returns the bookable time slots
for a given activity and date, each carrying its per-resource-option
availability so callers can decide whether a requested party fits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class DurationLength:
    """The numeric length of a :class:`Duration` paired with its unit."""

    amount: int
    """Quantity of ``unit`` (e.g. ``60``)."""
    unit: str
    """Unit of ``amount`` (e.g. ``"minutes"``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Duration:
    """The length of an :class:`AvailabilityTime` slot."""

    name: str
    """Human-readable duration name (e.g. ``"1 hour"``)."""
    length: DurationLength
    """The numeric length paired with its unit."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Availability:
    """Availability for a specific resource option within a slot."""

    qty: int
    """Total capacity of this resource option for the slot."""
    taken: int
    """How much of ``qty`` is already taken."""
    resource_option_id: str
    """The resource option this availability is for."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailabilityTime:
    """A single bookable availability time slot for an activity.

    Each slot describes a start/end window on the queried date and reports how
    much capacity remains per resource option (see :class:`Availability`).
    """

    id: str
    """Stable unique identifier of the slot."""
    time: str
    """Human-readable time label for the slot (e.g. ``"10:00 AM"``)."""
    from_: str
    """Slot start as reported by Peek (ISO datetime). Named ``from_`` because
    ``from`` is a Python keyword."""
    end: str
    """Slot end as reported by Peek (ISO datetime)."""
    duration: Duration
    """How long the slot runs."""
    status: str
    """Availability status reported by Peek (e.g. open/closed/sold-out)."""
    availability: list[Availability]
    """Remaining availability broken down per resource option. One entry per
    resource option offered for the slot."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceOptionQuantity:
    """A requested resource-option quantity used when querying availability."""

    resource_option_id: str
    """The resource option to check."""
    quantity: int
    """How many units of that option to check availability for."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AvailabilityTimesQuery:
    """Query parameters for fetching availability times."""

    activity_id: str
    """Activity (product) id."""
    date: str
    """Date to check (``YYYY-MM-DD``)."""
    resource_option_quantities: Sequence[ResourceOptionQuantity]
    """The resource options and quantities to check availability for."""
