"""Port of test/peek/timeslots/timeslot-converter.test.ts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from peek_app_utilities.internal.peek.timeslots.timeslot_converter import (
    from_timeslot_node,
    from_timeslot_nodes,
)
from peek_app_utilities.internal.peek.timeslots.timeslot_queries import TimeslotNode
from peek_app_utilities.models.peek.timeslot import AssignedResource, Timeslot

FULL_NODE_RAW: dict[str, Any] = {
    "id": "ts-1",
    "bookingCount": 2,
    "availableSpots": 8,
    "maxPartySize": 4,
    "totalCapacity": 10,
    "checkedInCount": 1,
    "manifestNotes": "VIP",
    "minuteLength": 90,
    "status": "OPEN",
    "date": "2026-01-02",
    "start": "2026-01-02T10:00:00Z",
    "inheritedResourceAllocations": [
        {
            "quantity": 1,
            "status": "ACTIVE",
            "resourcePool": {
                "id": "rp-1",
                "name": "Ada",
                "category": "guide",
                "capacity": 5,
                "accountUser": {"id": "u1"},
            },
        }
    ],
    "resourceAllocations": None,
}

BOB_ALLOCATION: dict[str, Any] = {
    "quantity": 2,
    "status": "ACTIVE",
    "resourcePool": {
        "id": "rp-2",
        "name": "Bob",
        "category": "guide",
        "capacity": 3,
        "accountUser": {"id": "u2"},
    },
}


def node(**overrides: Any) -> TimeslotNode:
    """A copy of the full raw node with ``overrides`` applied."""
    return cast("TimeslotNode", {**FULL_NODE_RAW, **overrides})


FULL_NODE = node()


def zeroed(product_id: str) -> Timeslot:
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


def test_maps_a_full_node_including_assigned_resources():
    assert from_timeslot_node(FULL_NODE, "act-1") == Timeslot(
        id="ts-1",
        product_id="act-1",
        total_capacity=10,
        available_capacity=8,
        max_party_size=4,
        booking_count=2,
        checked_in_count=1,
        status="OPEN",
        notes="VIP",
        duration_min=90,
        date="2026-01-02",
        start_time="2026-01-02T10:00:00Z",
        assigned_resources=[
            AssignedResource(
                name="Ada", capacity=5, category="guide", quantity=1, account_user_id="u1"
            )
        ],
    )


def test_returns_a_zeroed_timeslot_for_a_missing_node():
    assert from_timeslot_node(None, "act-1") == zeroed("act-1")


def test_applies_defaults_for_nullish_fields_and_a_null_resource_pool():
    sparse = cast(
        "TimeslotNode",
        {
            "id": "",
            "bookingCount": None,
            "availableSpots": None,
            "maxPartySize": None,
            "totalCapacity": None,
            "checkedInCount": None,
            "manifestNotes": None,
            "minuteLength": None,
            "status": None,
            "date": None,
            "inheritedResourceAllocations": [
                {"quantity": None, "status": "ACTIVE", "resourcePool": None}
            ],
        },
    )

    assert from_timeslot_node(sparse, "act-1") == replace(
        zeroed("act-1"),
        assigned_resources=[
            AssignedResource(name="", capacity=0, category="", quantity=0, account_user_id=None)
        ],
    )


def test_treats_missing_inherited_resource_allocations_as_no_assigned_resources():
    node_ = node(inheritedResourceAllocations=None)
    assert from_timeslot_node(node_, "act-1").assigned_resources == []


def test_falls_back_to_resource_allocations_when_inherited_is_none():
    node_ = node(inheritedResourceAllocations=None, resourceAllocations=[BOB_ALLOCATION])
    assert from_timeslot_node(node_, "act-1").assigned_resources == [
        AssignedResource(name="Bob", capacity=3, category="guide", quantity=2, account_user_id="u2")
    ]


def test_falls_back_to_resource_allocations_when_inherited_is_an_empty_list():
    node_ = node(
        inheritedResourceAllocations=[], resourceAllocations=[{**BOB_ALLOCATION, "quantity": 1}]
    )
    assert len(from_timeslot_node(node_, "act-1").assigned_resources) == 1
    assert from_timeslot_node(node_, "act-1").assigned_resources[0].name == "Bob"


def test_prefers_inherited_over_regular_resource_allocations_when_both_are_present():
    node_ = node(resourceAllocations=[{**BOB_ALLOCATION, "quantity": 9}])
    assigned = from_timeslot_node(node_, "act-1").assigned_resources
    assert len(assigned) == 1
    assert assigned[0].name == "Ada"


def test_filters_out_allocations_whose_status_is_not_active():
    node_ = node(
        inheritedResourceAllocations=[
            *FULL_NODE_RAW["inheritedResourceAllocations"],
            {
                "quantity": 1,
                "status": "REMOVAL",
                "resourcePool": {
                    "name": "Bob",
                    "category": "guide",
                    "capacity": 5,
                    "accountUser": {"id": "u2"},
                },
            },
        ],
    )
    assigned = from_timeslot_node(node_, "act-1").assigned_resources
    assert len(assigned) == 1
    assert assigned[0].name == "Ada"


def test_from_timeslot_nodes_maps_each_node_with_the_product_id():
    result = from_timeslot_nodes([FULL_NODE, node(id="ts-2")], "act-1")
    assert [t.id for t in result] == ["ts-1", "ts-2"]
    assert all(t.product_id == "act-1" for t in result)


def test_from_timeslot_nodes_returns_an_empty_list_for_no_nodes():
    assert from_timeslot_nodes([], "act-1") == []
