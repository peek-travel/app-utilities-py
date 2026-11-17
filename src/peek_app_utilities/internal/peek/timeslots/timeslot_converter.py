"""Pure functions mapping raw timeslot nodes into the clean :class:`Timeslot`
model. No I/O.
"""

from __future__ import annotations

from collections.abc import Iterable

from peek_app_utilities.internal.peek.timeslots.resource_allocation_queries import (
    ALLOCATION_STATUS_ACTIVE,
)
from peek_app_utilities.internal.peek.timeslots.timeslot_queries import (
    TimeslotNode,
    TimeslotResourceAllocationNode,
)
from peek_app_utilities.models.peek.timeslot import AssignedResource, Timeslot


def from_timeslot_nodes(nodes: Iterable[TimeslotNode | None], product_id: str) -> list[Timeslot]:
    """Converts a list of timeslot nodes for the given activity into
    :class:`Timeslot` models."""
    return [from_timeslot_node(node, product_id) for node in nodes]


def from_timeslot_node(node: TimeslotNode | None, product_id: str) -> Timeslot:
    """Converts a single timeslot node into a :class:`Timeslot`. A missing node
    yields a zeroed timeslot."""
    if not node:
        return Timeslot(
            id="",
            product_id=product_id,
            total_capacity=0,
            available_capacity=0,
            max_party_size=0,
            booking_count=0,
            checked_in_count=0,
            status="",
            notes=None,
            duration_min=0,
            date="",
            start_time=None,
            assigned_resources=[],
        )

    return Timeslot(
        id=node.get("id") or "",
        product_id=product_id,
        total_capacity=node.get("totalCapacity") or 0,
        available_capacity=node.get("availableSpots") or 0,
        max_party_size=node.get("maxPartySize") or 0,
        booking_count=node.get("bookingCount") or 0,
        checked_in_count=node.get("checkedInCount") or 0,
        status=node.get("status") or "",
        notes=node.get("manifestNotes"),
        duration_min=node.get("minuteLength") or 0,
        date=node.get("date") or "",
        start_time=node.get("start"),
        assigned_resources=_map_assigned_resources(_select_resource_allocations(node)),
    )


def _select_resource_allocations(
    node: TimeslotNode,
) -> list[TimeslotResourceAllocationNode] | None:
    """Timeslots may carry both inherited (schedule-level) and directly-assigned
    resource allocations. Prefer inherited; fall back to the regular allocations
    only when the inherited field is absent or empty."""
    inherited = node.get("inheritedResourceAllocations")
    if isinstance(inherited, list) and len(inherited) > 0:
        return inherited
    return node.get("resourceAllocations")


def _map_assigned_resources(
    allocations: list[TimeslotResourceAllocationNode] | None,
) -> list[AssignedResource]:
    if not isinstance(allocations, list) or len(allocations) == 0:
        return []
    return [
        _from_allocation(allocation)
        for allocation in allocations
        if allocation.get("status") == ALLOCATION_STATUS_ACTIVE
    ]


def _from_allocation(allocation: TimeslotResourceAllocationNode) -> AssignedResource:
    pool = allocation.get("resourcePool") or {}
    account_user = pool.get("accountUser") or {}
    return AssignedResource(
        name=pool.get("name") or "",
        capacity=pool.get("capacity") or 0,
        category=pool.get("category") or "",
        quantity=allocation.get("quantity") or 0,
        account_user_id=account_user.get("id"),
    )
