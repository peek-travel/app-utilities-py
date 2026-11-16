"""Port of test/peek/seatmaps/seatmap-converter.test.ts."""

from __future__ import annotations

from typing import Any

import pytest

from peek_app_utilities.errors import (
    UnknownSeatmapAssignmentParentError,
    UnknownSeatmapBlockStatusError,
    UnknownSeatmapDisplayTypeError,
)
from peek_app_utilities.internal.peek.seatmaps.seatmap_converter import (
    from_assignable_bookings,
    from_assigned_seatmap,
    from_deleted_assignments,
    from_seatmap_nodes,
    from_seatmap_summary_nodes,
    to_assignment_response,
)
from peek_app_utilities.models.peek.seatmap import (
    AssignableBooking,
    AssignableTicket,
    AssignedSeatmapBlock,
    AssignmentResponse,
    CurrentSeatAssignment,
    DeletedSeatAssignment,
    SeatmapAssignment,
    SeatmapBlock,
    SeatmapBlockAssignment,
    SeatmapDisplay,
    SeatmapSummary,
    SeatmapTicket,
    SeatmapZone,
    SuccessfulAssignment,
)


def full_node() -> dict[str, Any]:
    """A representative map node mirroring the shapes the API returns."""
    return {
        "id": "csm_8j734",
        "name": "Dinner Theater",
        "zones": [
            {
                "id": "csz_z77an",
                "name": "Premium",
                "colorHex": "#ff0000",
                "resourceOptions": [{"id": "ro-1", "name": "Adult - Premium"}],
            }
        ],
        "sections": [
            # A decorative SHAPE: width/height/label/type populated, no groups.
            {
                "id": "css_krn56",
                "display": {
                    "height": 60,
                    "label": "Stage",
                    "type": "SHAPE",
                    "width": 200,
                    "x": 672,
                    "y": 366,
                },
                "groups": [],
            },
            # A seatable SECTION: width/height/label null, one group with blocks.
            {
                "id": "css_km8d5",
                "display": {
                    "height": None,
                    "label": None,
                    "type": "SECTION",
                    "width": None,
                    "x": 800,
                    "y": 432,
                },
                "groups": [
                    {
                        "assignableTo": ["GUEST"],
                        "name": "Table 12",
                        "id": "csg_yj9ge",
                        "display": {
                            "table": True,
                            "tableHeight": 80,
                            "tableWidth": 120,
                            "x": 176,
                            "y": 256,
                        },
                        "blocks": [
                            {
                                "display": {"x": 0, "y": 0},
                                "fullBlockName": "Table 12, Seat 1",
                                "id": "csb_a7bk8",
                                "name": "1",
                                "order": 0,
                                "zone": {"id": "csz_zy3de"},
                            }
                        ],
                    }
                ],
            },
        ],
    }


def display(**overrides: Any) -> SeatmapDisplay:
    """A :class:`SeatmapDisplay` with every field ``None`` except ``overrides``."""
    base: dict[str, Any] = {
        "x": 0,
        "y": 0,
        "width": None,
        "height": None,
        "table_width": None,
        "table_height": None,
        "table": None,
        "label": None,
        "type": None,
    }
    return SeatmapDisplay(**{**base, **overrides})


def section_node(id: str, type: str, groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"id": id, "display": {"x": 0, "y": 0, "type": type}}
    if groups is not None:
        node["groups"] = groups
    return node


# ─── from_seatmap_nodes ───────────────────────────────────────────────────────


def test_maps_a_seating_map_node_into_the_clean_model():
    [seatmap] = from_seatmap_nodes([full_node()])

    assert (seatmap.id, seatmap.name) == ("csm_8j734", "Dinner Theater")
    assert seatmap.zones == [
        SeatmapZone(
            id="csz_z77an",
            name="Premium",
            color_hex="#ff0000",
            tickets=[SeatmapTicket(id="ro-1", name="Adult - Premium")],
        )
    ]
    assert len(seatmap.sections) == 2


def test_fills_a_sections_shared_display_and_leaves_table_fields_none():
    [seatmap] = from_seatmap_nodes([full_node()])
    shape = seatmap.sections[0]

    # Fields a section never carries collapse to None.
    assert shape.display == display(
        x=672, y=366, width=200, height=60, label="Stage", type="SHAPE"
    )
    assert shape.groups == []


def test_fills_a_section_display_with_none_width_height_label():
    [seatmap] = from_seatmap_nodes([full_node()])
    section = seatmap.sections[1]

    assert section.display == display(x=800, y=432, type="SECTION")


def test_fills_a_group_display_with_table_fields_and_nones_section_only_fields():
    [seatmap] = from_seatmap_nodes([full_node()])
    group = seatmap.sections[1].groups[0]

    assert (group.id, group.name, group.assignable_to) == ("csg_yj9ge", "Table 12", ["GUEST"])
    # Section-only fields collapse to None on a group.
    assert group.display == display(x=176, y=256, table=True, table_width=120, table_height=80)


def test_maps_a_block_keeping_only_x_y_on_its_display_and_resolving_zone_id():
    [seatmap] = from_seatmap_nodes([full_node()])
    block = seatmap.sections[1].groups[0].blocks[0]

    assert block == SeatmapBlock(
        id="csb_a7bk8",
        name="1",
        full_block_name="Table 12, Seat 1",
        order=0,
        zone_id="csz_zy3de",
        display=display(x=0, y=0),
    )


def test_accepts_every_known_display_type():
    node = {
        "id": "m",
        "name": "m",
        "sections": [
            section_node("a", "SHAPE", []),
            section_node("b", "SECTION", []),
            section_node("c", "LABEL", []),
        ],
    }
    [seatmap] = from_seatmap_nodes([node])
    assert [s.display.type for s in seatmap.sections] == ["SHAPE", "SECTION", "LABEL"]


def test_raises_unknown_seatmap_display_type_error_on_an_unrecognized_type():
    node = {"id": "m", "name": "m", "sections": [section_node("a", "CIRCLE", [])]}

    with pytest.raises(UnknownSeatmapDisplayTypeError) as info:
        from_seatmap_nodes([node])
    assert info.value.type == "CIRCLE"


def test_treats_a_none_group_table_height_as_none_irregular_table():
    node = {
        "id": "m",
        "name": "m",
        "sections": [
            section_node(
                "a",
                "SECTION",
                [
                    {
                        "assignableTo": ["GUEST"],
                        "name": "Table 9",
                        "id": "g",
                        "display": {
                            "table": True,
                            "tableHeight": None,
                            "tableWidth": 60,
                            "x": -624,
                            "y": -256,
                        },
                        "blocks": [],
                    }
                ],
            )
        ],
    }
    [seatmap] = from_seatmap_nodes([node])
    assert seatmap.sections[0].groups[0].display.table_height is None


def test_defaults_a_blocks_missing_zone_to_a_none_zone_id():
    node = {
        "id": "m",
        "name": "m",
        "sections": [
            section_node(
                "a",
                "SECTION",
                [
                    {
                        "name": "g",
                        "id": "g",
                        "display": {"x": 0, "y": 0},
                        "blocks": [
                            {
                                "display": {"x": 0, "y": 0},
                                "fullBlockName": "Unassigned",
                                "id": "b",
                                "name": "1",
                                "order": 0,
                            }
                        ],
                    }
                ],
            )
        ],
    }
    [seatmap] = from_seatmap_nodes([node])
    assert seatmap.sections[0].groups[0].blocks[0].zone_id is None


def test_defaults_missing_optional_collections_to_empty_lists():
    [seatmap] = from_seatmap_nodes([{"id": "m", "name": "m"}])

    assert seatmap.zones == []
    assert seatmap.sections == []


def test_defaults_missing_group_collections_and_assignable_to():
    node = {
        "id": "m",
        "name": "m",
        "zones": [{"id": "z", "name": "Z"}],
        "sections": [
            section_node("a", "SECTION", [{"name": "g", "id": "g", "display": {"x": 0, "y": 0}}])
        ],
    }
    [seatmap] = from_seatmap_nodes([node])

    assert seatmap.zones[0].tickets == []
    assert seatmap.zones[0].color_hex is None
    assert seatmap.sections[0].groups[0].assignable_to == []
    assert seatmap.sections[0].groups[0].blocks == []


def test_from_seatmap_nodes_returns_an_empty_list_for_no_nodes():
    assert from_seatmap_nodes([]) == []


# ─── from_seatmap_summary_nodes ───────────────────────────────────────────────


def test_summary_maps_each_node_to_its_id_and_name_only():
    assert from_seatmap_summary_nodes(
        [{"id": "csm_8j734", "name": "Dinner Theater"}, {"id": "csm_zz001", "name": "Patio"}]
    ) == [
        SeatmapSummary(id="csm_8j734", name="Dinner Theater"),
        SeatmapSummary(id="csm_zz001", name="Patio"),
    ]


def test_summary_returns_an_empty_list_for_no_nodes():
    assert from_seatmap_summary_nodes([]) == []


# ─── from_assigned_seatmap ────────────────────────────────────────────────────


def assigned_node(availability: dict[str, Any] | None) -> dict[str, Any]:
    """Wraps one seat with the given availability inside a full assigned-map node."""
    return {
        "id": "csm_8j734",
        "name": "Dinner Theater",
        "zones": [
            {
                "id": "csz_z77an",
                "name": "Premium",
                "colorHex": "#ff0000",
                "resourceOptions": [{"id": "ro-1", "name": "Adult - Premium"}],
            }
        ],
        "sections": [
            {
                "id": "css_km8d5",
                "display": {
                    "x": 800,
                    "y": 432,
                    "type": "SECTION",
                    "width": None,
                    "height": None,
                    "label": None,
                },
                "groups": [
                    {
                        "assignableTo": ["GUEST"],
                        "name": "Table 12",
                        "id": "csg_yj9ge",
                        "display": {
                            "x": 176,
                            "y": 256,
                            "table": True,
                            "tableWidth": 120,
                            "tableHeight": 80,
                        },
                        "blocks": [
                            {
                                "fullBlockName": "Table 12, Seat 1",
                                "name": "1",
                                "id": "csb_a7bk8",
                                "order": 0,
                                "zone": {"id": "csz_zy3de"},
                                "display": {"x": 0, "y": 0},
                                "availability": availability,
                            }
                        ],
                    }
                ],
            }
        ],
    }


TICKET_PARENT: dict[str, Any] = {
    "__typename": "Ticket",
    "id": "t_1",
    "resourceOptionSnapshot": {"id": "ro-1", "name": "Adult - Premium"},
    "booking": {
        "id": "bk_1",
        "displayId": "ABC123",
        "activityId": "act-1",
        "activitySnapshot": {"id": "act-1", "name": "Dinner Theater"},
        "startsAt": "2026-11-06T14:00:00",
        "endsAt": "2026-11-06T16:00:00",
        "primaryGuest": {"firstName": "Ada", "lastName": "Lovelace"},
    },
}

ACCOUNT_USER_PARENT: dict[str, Any] = {
    "__typename": "AccountUser",
    "id": "au_1",
    "name": "Grace Hopper",
}


def ticket_parent_with_booking(**booking_overrides: Any) -> dict[str, Any]:
    return {**TICKET_PARENT, "booking": {**TICKET_PARENT["booking"], **booking_overrides}}


def first_block(node: dict[str, Any]) -> AssignedSeatmapBlock:
    """Reaches the single seat's assignment data in an assigned-map result."""
    return from_assigned_seatmap(node).sections[0].groups[0].blocks[0]


def occupied(*assignments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "OCCUPIED", "assignments": list(assignments)}


def empty_assignment(occupied_by: str, guest_name: str | None = None) -> SeatmapAssignment:
    return SeatmapAssignment(
        occupied_by=occupied_by,  # type: ignore[arg-type]
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


def test_assigned_carries_the_same_structural_data_as_the_base_map():
    seatmap = from_assigned_seatmap(assigned_node({"status": "AVAILABLE", "assignments": []}))
    assert (seatmap.id, seatmap.name) == ("csm_8j734", "Dinner Theater")
    assert seatmap.zones[0].tickets[0] == SeatmapTicket(id="ro-1", name="Adult - Premium")
    assert seatmap.zones[0].color_hex == "#ff0000"
    block = seatmap.sections[0].groups[0].blocks[0]
    assert (block.id, block.full_block_name, block.order, block.zone_id) == (
        "csb_a7bk8",
        "Table 12, Seat 1",
        0,
        "csz_zy3de",
    )
    assert (block.display.x, block.display.y) == (0, 0)


def test_maps_a_guest_assignment_with_full_booking_detail():
    block = first_block(assigned_node(occupied({"id": "asa_1", "parent": TICKET_PARENT})))
    assert block.status == "OCCUPIED"
    assert block.assigned_to == [
        SeatmapAssignment(
            occupied_by="GUEST",
            booking_id="bk_1",
            booking_display_id="ABC123",
            product_id="act-1",
            product_name="Dinner Theater",
            ticket_id="ro-1",
            ticket_name="Adult - Premium",
            guest_name="Ada Lovelace",
            starts_at="2026-11-06T14:00:00",
            ends_at="2026-11-06T16:00:00",
        )
    ]


def test_strips_fractional_seconds_from_booking_starts_at_ends_at():
    parent = ticket_parent_with_booking(
        startsAt="2026-11-02T19:00:00.000000", endsAt="2026-11-02T21:30:00.500"
    )
    block = first_block(assigned_node(occupied({"id": "asa_1", "parent": parent})))
    assert block.assigned_to[0].starts_at == "2026-11-02T19:00:00"
    assert block.assigned_to[0].ends_at == "2026-11-02T21:30:00"


def test_nones_a_guest_guest_name_when_primary_guest_is_absent_pii_off():
    parent = ticket_parent_with_booking(primaryGuest=None)
    block = first_block(assigned_node(occupied({"id": "asa_1", "parent": parent})))
    assert block.assigned_to[0].guest_name is None
    # Non-PII booking detail still present.
    assert block.assigned_to[0].booking_id == "bk_1"
    assert block.assigned_to[0].starts_at == "2026-11-06T14:00:00"


def test_maps_an_account_user_assignment_with_the_staff_name_as_guest_name():
    block = first_block(assigned_node(occupied({"id": "asa_2", "parent": ACCOUNT_USER_PARENT})))
    assignment = block.assigned_to[0]
    assert assignment.occupied_by == "ACCOUNT_USER"
    assert assignment.guest_name == "Grace Hopper"
    assert assignment.booking_id is None
    assert assignment.ticket_id is None
    assert assignment.starts_at is None


def test_maps_a_field_location_assignment_with_all_detail_none():
    block = first_block(
        assigned_node(
            occupied({"id": "asa_3", "parent": {"__typename": "FieldLocation", "id": "fl_1"}})
        )
    )
    assert block.assigned_to[0] == empty_assignment("FIELD_LOCATION")


def test_keeps_every_assignment_when_a_seat_has_more_than_one():
    block = first_block(
        assigned_node(
            occupied(
                {"id": "asa_1", "parent": TICKET_PARENT},
                {"id": "asa_2", "parent": ACCOUNT_USER_PARENT},
            )
        )
    )
    assert len(block.assigned_to) == 2
    assert [a.occupied_by for a in block.assigned_to] == ["GUEST", "ACCOUNT_USER"]


def test_drops_a_blocked_seat_parent_and_never_populates_assigned_to_off_occupied():
    blocked_seat = {"id": "asa_4", "parent": {"__typename": "BlockedSeat", "id": "bs_1"}}
    blocked = first_block(assigned_node({"status": "BLOCKED", "assignments": [blocked_seat]}))
    assert blocked.status == "BLOCKED"
    assert blocked.assigned_to == []

    # Even if a BlockedSeat somehow rides along an OCCUPIED status, it drops out.
    occupied_block = first_block(
        assigned_node(occupied(blocked_seat, {"id": "asa_1", "parent": TICKET_PARENT}))
    )
    assert len(occupied_block.assigned_to) == 1
    assert occupied_block.assigned_to[0].occupied_by == "GUEST"


def test_leaves_assigned_to_empty_for_an_available_seat():
    block = first_block(
        assigned_node(
            {"status": "AVAILABLE", "assignments": [{"id": "asa_1", "parent": TICKET_PARENT}]}
        )
    )
    assert block.assigned_to == []


def test_raises_on_an_unknown_seat_status():
    with pytest.raises(UnknownSeatmapBlockStatusError):
        from_assigned_seatmap(assigned_node({"status": "HELD", "assignments": []}))


def test_raises_on_a_missing_seat_status():
    with pytest.raises(UnknownSeatmapBlockStatusError) as info:
        from_assigned_seatmap(assigned_node({"assignments": []}))
    assert info.value.status == "None"


def test_raises_on_an_unknown_assignment_parent_typename():
    with pytest.raises(UnknownSeatmapAssignmentParentError) as info:
        from_assigned_seatmap(
            assigned_node(occupied({"id": "asa_x", "parent": {"__typename": "Robot", "id": "r_1"}}))
        )
    assert info.value.typename == "Robot"


def test_assigned_defaults_missing_optional_collections_to_empty():
    seatmap = from_assigned_seatmap({"id": "m", "name": "m"})
    assert seatmap.zones == []
    assert seatmap.sections == []


def test_assigned_defaults_missing_groups_blocks_collections_to_empty():
    seatmap = from_assigned_seatmap(
        {
            "id": "m",
            "name": "m",
            "sections": [
                section_node("s1", "SECTION"),
                section_node(
                    "s2", "SECTION", [{"id": "g1", "name": "g1", "display": {"x": 0, "y": 0}}]
                ),
            ],
        }
    )
    assert seatmap.sections[0].groups == []
    assert seatmap.sections[1].groups[0].blocks == []


def test_nones_every_booking_derived_field_when_a_ticket_carries_no_booking_snapshots():
    block = first_block(
        assigned_node(occupied({"id": "asa_1", "parent": {"__typename": "Ticket", "id": "t_1"}}))
    )
    assert block.assigned_to[0] == empty_assignment("GUEST")


def test_nones_guest_name_when_both_name_parts_are_blank():
    parent = ticket_parent_with_booking(primaryGuest={"firstName": "  ", "lastName": None})
    block = first_block(assigned_node(occupied({"id": "asa_1", "parent": parent})))
    assert block.assigned_to[0].guest_name is None


def test_treats_a_none_assignments_list_under_occupied_as_empty():
    block = first_block(assigned_node({"status": "OCCUPIED", "assignments": None}))
    assert block.assigned_to == []


# ─── from_assignable_bookings ─────────────────────────────────────────────────

ASSIGNABLE_BOOKING: dict[str, Any] = {
    "id": "bk_1",
    "displayId": "ABC123",
    "startsAt": "2026-11-02T19:00:00.000000",
    "endsAt": "2026-11-02T21:00:00.0",
    "operatorNotes": "VIP — window seat",
    "primaryGuest": {"firstName": "Ada", "lastName": "Lovelace"},
    "tickets": [
        {
            "hashid": "tkt_h1",
            "resourceOptionSnapshot": {"id": "ro-1", "name": "Adult - Premium"},
            "seatingAssignment": {
                "id": "asa_1",
                "block": {"id": "csb_a7bk8", "fullBlockName": "Table 12, Seat 1"},
            },
        }
    ],
}


def test_maps_a_booking_with_an_assigned_ticket():
    [booking] = from_assignable_bookings([ASSIGNABLE_BOOKING])
    assert booking == AssignableBooking(
        id="bk_1",
        display_id="ABC123",
        starts_at="2026-11-02T19:00:00",
        ends_at="2026-11-02T21:00:00",
        notes="VIP — window seat",
        guest_name="Ada Lovelace",
        assignable_tickets=[
            AssignableTicket(
                assignable_id="tkt_h1",
                ticket_id="ro-1",
                ticket_name="Adult - Premium",
                currently_assigned_to=CurrentSeatAssignment(
                    assignment_id="asa_1", block_id="csb_a7bk8", block_name="Table 12, Seat 1"
                ),
            )
        ],
    )


def test_nones_currently_assigned_to_when_a_ticket_has_no_seating_assignment():
    [booking] = from_assignable_bookings(
        [
            {
                **ASSIGNABLE_BOOKING,
                "tickets": [
                    {"hashid": "tkt_h2", "resourceOptionSnapshot": {"id": "ro-2", "name": "Child"}}
                ],
            }
        ]
    )
    assert booking.assignable_tickets[0].currently_assigned_to is None


def test_nones_ticket_snapshot_fields_and_block_fields_when_absent():
    [booking] = from_assignable_bookings(
        [{**ASSIGNABLE_BOOKING, "tickets": [{"hashid": "tkt_h3", "seatingAssignment": {"id": "asa_3"}}]}]
    )
    assert booking.assignable_tickets[0] == AssignableTicket(
        assignable_id="tkt_h3",
        ticket_id=None,
        ticket_name=None,
        currently_assigned_to=CurrentSeatAssignment(
            assignment_id="asa_3", block_id=None, block_name=None
        ),
    )


def test_assignable_nones_guest_name_when_primary_guest_is_absent_pii_off():
    [booking] = from_assignable_bookings([{**ASSIGNABLE_BOOKING, "primaryGuest": None}])
    assert booking.guest_name is None


def test_defaults_missing_tickets_times_and_notes_to_empty_none():
    [booking] = from_assignable_bookings([{"id": "bk_2", "displayId": "X"}])
    assert booking.assignable_tickets == []
    assert booking.starts_at is None
    assert booking.ends_at is None
    assert booking.notes == ""


def test_assignable_returns_an_empty_list_for_no_nodes():
    assert from_assignable_bookings([]) == []


# ─── to_assignment_response ───────────────────────────────────────────────────

ASSIGNMENTS = [
    SeatmapBlockAssignment(assignable_id="t_A1", block_id="csb_A1"),
    SeatmapBlockAssignment(assignable_id="t_B1", block_id="csb_B1"),
]


def ok(asa_id: str, hashid: str) -> dict[str, Any]:
    return {
        "__typename": "AssignmentResponse",
        "assignments": [{"id": asa_id, "parent": {"__typename": "Ticket", "hashid": hashid}}],
    }


def test_returns_success_with_assignable_id_assignment_id_pairs_when_all_succeed():
    data = {"a0": ok("asa_1", "t_A1"), "a1": ok("asa_2", "t_B1")}
    assert to_assignment_response(data, ASSIGNMENTS) == AssignmentResponse(
        status="SUCCESS",
        successful_assignments=[
            SuccessfulAssignment(assignable_id="t_A1", assignment_id="asa_1"),
            SuccessfulAssignment(assignable_id="t_B1", assignment_id="asa_2"),
        ],
        failed_assignments=[],
    )


def test_returns_partial_when_some_succeed_and_some_fail():
    data = {"a0": ok("asa_1", "t_A1"), "a1": {"__typename": "AssignBlocksErrorOverbooking"}}
    assert to_assignment_response(data, ASSIGNMENTS) == AssignmentResponse(
        status="PARTIAL",
        successful_assignments=[SuccessfulAssignment(assignable_id="t_A1", assignment_id="asa_1")],
        failed_assignments=["t_B1"],
    )


def test_returns_failed_when_every_assignment_failed():
    data = {
        "a0": {"__typename": "AssignBlocksErrorInvalidType"},
        "a1": {"__typename": "AssignBlocksErrorOverbooking"},
    }
    assert to_assignment_response(data, ASSIGNMENTS) == AssignmentResponse(
        status="FAILED", successful_assignments=[], failed_assignments=["t_A1", "t_B1"]
    )


def test_treats_a_missing_none_aliased_result_as_a_failure():
    assert to_assignment_response({"a0": ok("asa_1", "t_A1")}, ASSIGNMENTS) == AssignmentResponse(
        status="PARTIAL",
        successful_assignments=[SuccessfulAssignment(assignable_id="t_A1", assignment_id="asa_1")],
        failed_assignments=["t_B1"],
    )
    assert to_assignment_response({"a0": ok("asa_1", "t_A1"), "a1": None}, ASSIGNMENTS).status == (
        "PARTIAL"
    )


def test_falls_back_to_the_input_assignable_id_when_the_parent_hashid_is_absent():
    data = {"a0": {"__typename": "AssignmentResponse", "assignments": [{"id": "asa_9"}]}}
    assert to_assignment_response(data, [ASSIGNMENTS[0]]) == AssignmentResponse(
        status="SUCCESS",
        successful_assignments=[SuccessfulAssignment(assignable_id="t_A1", assignment_id="asa_9")],
        failed_assignments=[],
    )


# ─── from_deleted_assignments ─────────────────────────────────────────────────


def test_maps_a_deleted_assignment_to_the_clean_model():
    nodes = [
        {
            "id": "asa_1",
            "block": {"id": "csb_A1", "fullBlockName": "Zone A · Row 1 · Seat 1"},
            "parent": {"__typename": "Ticket", "hashid": "t_pmwj9xbb"},
        }
    ]
    assert from_deleted_assignments(nodes) == [
        DeletedSeatAssignment(
            assignment_id="asa_1",
            block_id="csb_A1",
            block_name="Zone A · Row 1 · Seat 1",
            ticket_hash_id="t_pmwj9xbb",
        )
    ]


def test_deleted_nones_block_and_ticket_fields_when_absent():
    assert from_deleted_assignments([{"id": "asa_2"}]) == [
        DeletedSeatAssignment(
            assignment_id="asa_2", block_id=None, block_name=None, ticket_hash_id=None
        )
    ]


def test_deleted_returns_an_empty_list_for_no_nodes():
    assert from_deleted_assignments([]) == []
