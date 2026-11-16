"""Port of test/peek/seatmaps/seatmap-service.test.ts.

The TypeScript suite drives a real ``GraphQLClient`` over a fake ``fetch``; here
the service takes the :class:`FakeGraphQLClient` directly (the port convention),
so the URL assertions become endpoint-name assertions and the request body
assertions read ``gql.last_call``.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.errors import (
    PeekGraphQLError,
    SeatmapDeleteError,
    UnknownSeatmapBlockStatusError,
    UnknownSeatmapDisplayTypeError,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.seatmaps.seatmap_service import SeatmapService
from peek_app_utilities.models.peek.seatmap import (
    AssignmentResponse,
    DeletedSeatAssignment,
    SeatmapBlockAssignment,
    SeatmapSummary,
    SeatmapTicket,
    SuccessfulAssignment,
)
from tests.conftest import FakeGraphQLClient

PRIMARY_GUEST: str = "primaryGuest"


def build_service(gql: FakeGraphQLClient, *, full_customer_access: bool = False) -> SeatmapService:
    return SeatmapService(
        gql,  # type: ignore[arg-type]
        ResolvedAccessOptions(full_customer_access=full_customer_access),
    )


SEATMAP_NODE: dict[str, Any] = {
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
                "label": None,
                "x": 800,
                "y": 432,
                "width": None,
                "height": None,
                "type": "SECTION",
            },
            "groups": [
                {
                    "assignableTo": ["GUEST"],
                    "name": "Table 12",
                    "id": "csg_yj9ge",
                    "display": {
                        "x": 176,
                        "y": 256,
                        "tableWidth": 120,
                        "tableHeight": 80,
                        "table": True,
                    },
                    "blocks": [
                        {
                            "fullBlockName": "Table 12, Seat 1",
                            "name": "1",
                            "id": "csb_a7bk8",
                            "order": 0,
                            "zone": {"id": "csz_zy3de"},
                            "display": {"x": 0, "y": 0},
                        }
                    ],
                }
            ],
        }
    ],
}


def seating_maps(maps: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"activity": {"seatingMaps": maps}}


# ─── get_seatmap_for_product ──────────────────────────────────────────────────


async def test_get_seatmap_for_product_returns_every_seating_map_on_the_product(gql):
    gql.queue(seating_maps([SEATMAP_NODE]))

    maps = await build_service(gql).get_seatmap_for_product("act-1")

    assert len(maps) == 1
    assert maps[0].id == "csm_8j734"
    assert maps[0].zones[0].tickets[0] == SeatmapTicket(id="ro-1", name="Adult - Premium")
    assert maps[0].zones[0].color_hex == "#ff0000"
    assert maps[0].sections[0].groups[0].blocks[0].zone_id == "csz_zy3de"

    # Reaches the sales endpoint with the product id as the `id` variable.
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.variables == {"id": "act-1"}


async def test_get_seatmap_for_product_returns_an_empty_list_when_the_activity_is_not_found(gql):
    gql.queue({"activity": None})
    assert await build_service(gql).get_seatmap_for_product("missing") == []


async def test_get_seatmap_for_product_returns_an_empty_list_when_the_activity_has_no_maps(gql):
    gql.queue(seating_maps(None))
    assert await build_service(gql).get_seatmap_for_product("act-1") == []


async def test_get_seatmap_for_product_raises_on_a_blank_product_id_without_hitting_the_network(
    gql,
):
    with pytest.raises(ValueError, match=re.escape("A non-empty product id is required.")):
        await build_service(gql).get_seatmap_for_product("  ")
    assert gql.calls == []


async def test_get_seatmap_for_product_propagates_an_unknown_display_type_from_the_converter(gql):
    gql.queue(
        seating_maps(
            [
                {
                    "id": "m",
                    "name": "m",
                    "sections": [
                        {"id": "a", "display": {"x": 0, "y": 0, "type": "CIRCLE"}, "groups": []}
                    ],
                }
            ]
        )
    )
    with pytest.raises(UnknownSeatmapDisplayTypeError):
        await build_service(gql).get_seatmap_for_product("act-1")


# ─── get_seatmap_ids_for_product ──────────────────────────────────────────────


async def test_get_seatmap_ids_for_product_returns_the_id_and_name_of_every_map(gql):
    gql.queue(
        seating_maps(
            [{"id": "csm_8j734", "name": "Dinner Theater"}, {"id": "csm_zz001", "name": "Patio"}]
        )
    )

    maps = await build_service(gql).get_seatmap_ids_for_product("act-1")

    assert maps == [
        SeatmapSummary(id="csm_8j734", name="Dinner Theater"),
        SeatmapSummary(id="csm_zz001", name="Patio"),
    ]
    # Reaches the sales endpoint with the product id, and the trimmed query
    # selects no layout (no zones/sections).
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.variables == {"id": "act-1"}
    assert "zones" not in gql.last_call.query
    assert "sections" not in gql.last_call.query


async def test_get_seatmap_ids_for_product_returns_an_empty_list_when_the_activity_is_not_found(
    gql,
):
    gql.queue({"activity": None})
    assert await build_service(gql).get_seatmap_ids_for_product("missing") == []


async def test_get_seatmap_ids_for_product_returns_an_empty_list_when_the_activity_has_no_maps(
    gql,
):
    gql.queue(seating_maps(None))
    assert await build_service(gql).get_seatmap_ids_for_product("act-1") == []


async def test_get_seatmap_ids_for_product_raises_on_a_blank_product_id_without_network(gql):
    with pytest.raises(ValueError, match=re.escape("A non-empty product id is required.")):
        await build_service(gql).get_seatmap_ids_for_product("  ")
    assert gql.calls == []


# ─── get_seat_map_assignments ─────────────────────────────────────────────────


def assignments_response() -> dict[str, Any]:
    """A seat-assignments response with one map holding one occupied GUEST seat."""
    return seating_maps(
        [
            {
                "id": "csm_8j734",
                "name": "Dinner Theater",
                "zones": [],
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
                                        "availability": {
                                            "status": "OCCUPIED",
                                            "assignments": [
                                                {
                                                    "id": "asa_1",
                                                    "parent": {
                                                        "__typename": "Ticket",
                                                        "id": "t_1",
                                                        "resourceOptionSnapshot": {
                                                            "id": "ro-1",
                                                            "name": "Adult - Premium",
                                                        },
                                                        "booking": {
                                                            "id": "bk_1",
                                                            "displayId": "ABC123",
                                                            "activityId": "act-1",
                                                            "activitySnapshot": {
                                                                "id": "act-1",
                                                                "name": "Dinner Theater",
                                                            },
                                                            "startsAt": "2026-11-06T14:00:00",
                                                            "endsAt": "2026-11-06T16:00:00",
                                                            "primaryGuest": {
                                                                "firstName": "Ada",
                                                                "lastName": "Lovelace",
                                                            },
                                                        },
                                                    },
                                                }
                                            ],
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    )


async def test_get_seat_map_assignments_returns_maps_with_occupancy_and_sends_id_and_range(gql):
    gql.queue(assignments_response())

    maps = await build_service(gql, full_customer_access=True).get_seat_map_assignments(
        "act-1", "2026-11-06T14:00:00", "2026-11-06T16:00:00"
    )

    assert len(maps) == 1
    block = maps[0].sections[0].groups[0].blocks[0]
    assert block.status == "OCCUPIED"
    assert block.assigned_to[0].occupied_by == "GUEST"
    assert block.assigned_to[0].guest_name == "Ada Lovelace"

    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.variables == {
        "id": "act-1",
        "range": "[2026-11-06T14:00:00,2026-11-06T16:00:00)",
    }


async def test_get_seat_map_assignments_selects_primary_guest_only_when_full_customer_access():
    with_pii = FakeGraphQLClient().queue(assignments_response())
    await build_service(with_pii, full_customer_access=True).get_seat_map_assignments(
        "csm_1", "2026-11-06T14:00", "2026-11-06T16:00"
    )
    assert PRIMARY_GUEST in with_pii.last_call.query

    no_pii = FakeGraphQLClient().queue(assignments_response())
    await build_service(no_pii, full_customer_access=False).get_seat_map_assignments(
        "csm_1", "2026-11-06T14:00", "2026-11-06T16:00"
    )
    assert PRIMARY_GUEST not in no_pii.last_call.query


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-11-06T14:00", "2026-11-06T16:00", "[2026-11-06T14:00:00,2026-11-06T16:00:00)"),
        (
            "2026-11-06T14:00:00Z",
            "2026-11-06T16:00:00Z",
            "[2026-11-06T14:00:00,2026-11-06T16:00:00)",
        ),
        (
            "2026-11-06T14:00:00+05:30",
            "2026-11-06T16:00:00-0800",
            "[2026-11-06T14:00:00,2026-11-06T16:00:00)",
        ),
        (
            "2026-11-06T14:00:00.123",
            "2026-11-06T16:00:30.9",
            "[2026-11-06T14:00:00,2026-11-06T16:00:30)",
        ),
    ],
)
async def test_get_seat_map_assignments_normalizes_flexible_datetime_inputs(
    gql, start, end, expected
):
    gql.queue(assignments_response())
    await build_service(gql).get_seat_map_assignments("csm_1", start, end)
    assert gql.last_call.variables["range"] == expected


async def test_get_seat_map_assignments_returns_an_empty_list_when_not_found_or_no_maps(gql):
    gql.queue({"activity": None})
    assert (
        await build_service(gql).get_seat_map_assignments(
            "missing", "2026-11-06T14:00", "2026-11-06T16:00"
        )
        == []
    )

    gql.queue(seating_maps(None))
    assert (
        await build_service(gql).get_seat_map_assignments(
            "act-1", "2026-11-06T14:00", "2026-11-06T16:00"
        )
        == []
    )


async def test_get_seat_map_assignments_raises_on_a_blank_product_id_without_network(gql):
    with pytest.raises(ValueError, match=re.escape("A non-empty product id is required.")):
        await build_service(gql).get_seat_map_assignments(
            "  ", "2026-11-06T14:00", "2026-11-06T16:00"
        )
    assert gql.calls == []


async def test_get_seat_map_assignments_raises_on_unparseable_or_out_of_range_datetime(gql):
    service = build_service(gql)

    with pytest.raises(ValueError, match="rangeStart"):
        await service.get_seat_map_assignments("csm_1", "11/06/2026 2pm", "2026-11-06T16:00")
    with pytest.raises(ValueError, match="rangeEnd"):
        await service.get_seat_map_assignments("csm_1", "2026-11-06T14:00", "2026-13-06T16:00")
    with pytest.raises(ValueError, match=re.escape("rangeStart is required.")):
        await service.get_seat_map_assignments("csm_1", "", "2026-11-06T16:00")
    assert gql.calls == []


async def test_get_seat_map_assignments_raises_when_the_range_bounds_fall_on_different_dates(gql):
    service = build_service(gql)

    with pytest.raises(
        ValueError, match=re.escape("rangeStart and rangeEnd must fall on the same date.")
    ):
        await service.get_seat_map_assignments("act-1", "2026-11-06T14:00", "2026-11-07T02:00")
    assert gql.calls == []

    # Same date, different times is fine.
    gql.queue(assignments_response())
    result = await service.get_seat_map_assignments(
        "act-1", "2026-11-06T23:00:00Z", "2026-11-06T23:30"
    )
    assert result is not None
    assert len(gql.calls) == 1


async def test_get_seat_map_assignments_propagates_an_unknown_seat_status_from_the_converter(gql):
    bad = copy.deepcopy(assignments_response())
    block = bad["activity"]["seatingMaps"][0]["sections"][0]["groups"][0]["blocks"][0]
    block["availability"]["status"] = "HELD"
    gql.queue(bad)

    with pytest.raises(UnknownSeatmapBlockStatusError):
        await build_service(gql).get_seat_map_assignments(
            "csm_1", "2026-11-06T14:00", "2026-11-06T16:00"
        )


# ─── assignable_bookings ──────────────────────────────────────────────────────


def bookings_response() -> dict[str, Any]:
    """An assignable-bookings response with one booking holding one assigned ticket."""
    return {
        "bookings": [
            {
                "id": "bk_1",
                "displayId": "ABC123",
                "startsAt": "2026-11-06T14:00:00.000000",
                "endsAt": "2026-11-06T15:00:00.000000",
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
        ]
    }


async def test_assignable_bookings_returns_overlapping_bookings_and_sends_id_and_range(gql):
    gql.queue(bookings_response())

    bookings = await build_service(gql, full_customer_access=True).assignable_bookings(
        "act-1", "2026-11-06T14:00:00", "2026-11-06T15:00:00"
    )

    assert len(bookings) == 1
    booking = bookings[0]
    assert (booking.id, booking.display_id, booking.guest_name, booking.notes) == (
        "bk_1",
        "ABC123",
        "Ada Lovelace",
        "VIP — window seat",
    )
    assert booking.starts_at == "2026-11-06T14:00:00"
    current = booking.assignable_tickets[0].currently_assigned_to
    assert current is not None
    assert current.block_name == "Table 12, Seat 1"

    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.variables == {
        "id": "act-1",
        "range": "[2026-11-06T14:00:00,2026-11-06T15:00:00)",
    }


async def test_assignable_bookings_selects_primary_guest_only_when_full_customer_access():
    with_pii = FakeGraphQLClient().queue(bookings_response())
    await build_service(with_pii, full_customer_access=True).assignable_bookings(
        "act-1", "2026-11-06T14:00", "2026-11-06T15:00"
    )
    assert PRIMARY_GUEST in with_pii.last_call.query

    no_pii = FakeGraphQLClient().queue(bookings_response())
    await build_service(no_pii, full_customer_access=False).assignable_bookings(
        "act-1", "2026-11-06T14:00", "2026-11-06T15:00"
    )
    assert PRIMARY_GUEST not in no_pii.last_call.query


async def test_assignable_bookings_returns_an_empty_list_when_no_bookings_match(gql):
    gql.queue({"bookings": None})
    assert (
        await build_service(gql).assignable_bookings(
            "act-1", "2026-11-06T14:00", "2026-11-06T15:00"
        )
        == []
    )


async def test_assignable_bookings_raises_on_a_blank_product_id_or_bad_range_without_network(gql):
    service = build_service(gql)

    with pytest.raises(ValueError, match=re.escape("A non-empty product id is required.")):
        await service.assignable_bookings("  ", "2026-11-06T14:00", "2026-11-06T15:00")
    with pytest.raises(ValueError, match="rangeStart"):
        await service.assignable_bookings("act-1", "nope", "2026-11-06T15:00")
    with pytest.raises(
        ValueError, match=re.escape("rangeStart and rangeEnd must fall on the same date.")
    ):
        await service.assignable_bookings("act-1", "2026-11-06T23:00", "2026-11-07T01:00")
    assert gql.calls == []


# ─── assign_tickets_to_seats ──────────────────────────────────────────────────

ASSIGNMENTS = [
    SeatmapBlockAssignment(assignable_id="t_A1", block_id="csb_A1"),
    SeatmapBlockAssignment(assignable_id="t_B1", block_id="csb_B1"),
]


async def test_assign_tickets_to_seats_batches_one_aliased_call_per_assignment_partial(gql):
    gql.queue(
        {
            "a0": {
                "__typename": "AssignmentResponse",
                "assignments": [
                    {"id": "asa_1", "parent": {"__typename": "Ticket", "hashid": "t_A1"}}
                ],
            },
            "a1": {"__typename": "AssignBlocksErrorOverbooking", "message": "booked"},
        }
    )

    result = await build_service(gql).assign_tickets_to_seats(ASSIGNMENTS)

    assert result == AssignmentResponse(
        status="PARTIAL",
        successful_assignments=[SuccessfulAssignment(assignable_id="t_A1", assignment_id="asa_1")],
        failed_assignments=["t_B1"],
    )
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert (
        "a0: assignBlocks(assignableId: $assignable0, blockIds: $blocks0, fieldResponses: [])"
        in gql.last_call.query
    )
    assert (
        "a1: assignBlocks(assignableId: $assignable1, blockIds: $blocks1, fieldResponses: [])"
        in gql.last_call.query
    )
    assert gql.last_call.variables == {
        "assignable0": "t_A1",
        "blocks0": ["csb_A1"],
        "assignable1": "t_B1",
        "blocks1": ["csb_B1"],
    }


async def test_assign_tickets_to_seats_returns_success_when_all_assignments_succeed(gql):
    gql.queue(
        {"a0": {"__typename": "AssignmentResponse"}, "a1": {"__typename": "AssignmentResponse"}}
    )
    result = await build_service(gql).assign_tickets_to_seats(ASSIGNMENTS)
    assert result.status == "SUCCESS"


async def test_assign_tickets_to_seats_raises_on_empty_input_without_hitting_the_network(gql):
    with pytest.raises(ValueError, match=re.escape("At least one assignment is required.")):
        await build_service(gql).assign_tickets_to_seats([])
    assert gql.calls == []


async def test_assign_tickets_to_seats_raises_on_a_bad_assignable_id_or_block_id_prefix(gql):
    service = build_service(gql)

    with pytest.raises(ValueError, match=re.escape('Each assignableId must start with "t_".')):
        await service.assign_tickets_to_seats(
            [SeatmapBlockAssignment(assignable_id="x_A1", block_id="csb_A1")]
        )
    with pytest.raises(ValueError, match=re.escape('Each blockId must start with "csb_".')):
        await service.assign_tickets_to_seats(
            [SeatmapBlockAssignment(assignable_id="t_A1", block_id="seat_A1")]
        )
    assert gql.calls == []


async def test_assign_tickets_to_seats_propagates_a_top_level_graphql_error_as_an_exception(gql):
    gql.queue_error(PeekGraphQLError([{"message": "boom"}]))
    with pytest.raises(PeekGraphQLError):
        await build_service(gql).assign_tickets_to_seats(ASSIGNMENTS)


# ─── delete_seat_assignments ──────────────────────────────────────────────────


def delete_success() -> dict[str, Any]:
    return {
        "deleteAssignments": {
            "__typename": "DeleteAssignmentsSuccess",
            "assignments": [
                {
                    "id": "asa_9kQ2mNv",
                    "block": {"id": "csb_A1", "fullBlockName": "Zone A · Row 1 · Seat 1"},
                    "parent": {"__typename": "Ticket", "hashid": "t_pmwj9xbb"},
                }
            ],
        }
    }


async def test_delete_seat_assignments_deletes_by_id_and_returns_the_now_deleted_assignments(gql):
    gql.queue(delete_success())

    deleted = await build_service(gql).delete_seat_assignments(["asa_9kQ2mNv", "asa_7hL4pXw"])

    assert deleted == [
        DeletedSeatAssignment(
            assignment_id="asa_9kQ2mNv",
            block_id="csb_A1",
            block_name="Zone A · Row 1 · Seat 1",
            ticket_hash_id="t_pmwj9xbb",
        )
    ]
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert "deleteAssignments(assignmentIds: $assignmentIds)" in gql.last_call.query
    assert gql.last_call.variables == {"assignmentIds": ["asa_9kQ2mNv", "asa_7hL4pXw"]}


async def test_delete_seat_assignments_raises_seatmap_delete_error_on_a_non_success_member(gql):
    gql.queue(
        {
            "deleteAssignments": {
                "__typename": "AssignBlocksErrorInvalidBlockCount",
                "message": "wrong count",
                "numNeeded": 2,
                "numProvided": 1,
            }
        }
    )
    with pytest.raises(SeatmapDeleteError, match="wrong count"):
        await build_service(gql).delete_seat_assignments(["asa_1"])


async def test_delete_seat_assignments_raises_seatmap_delete_error_default_on_missing_result(gql):
    gql.queue({"deleteAssignments": None})
    with pytest.raises(SeatmapDeleteError, match=re.escape("Deleting seat assignments failed.")):
        await build_service(gql).delete_seat_assignments(["asa_1"])


async def test_delete_seat_assignments_raises_on_empty_input_or_a_bad_id_prefix_without_network(
    gql,
):
    service = build_service(gql)

    with pytest.raises(ValueError, match=re.escape("At least one assignment id is required.")):
        await service.delete_seat_assignments([])
    with pytest.raises(ValueError, match=re.escape('Each assignment id must start with "asa_".')):
        await service.delete_seat_assignments(["csb_nope"])
    assert gql.calls == []
