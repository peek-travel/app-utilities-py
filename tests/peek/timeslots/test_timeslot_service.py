"""Port of test/peek/timeslots/timeslot-service.test.ts.

The resource-pool and account-user dependencies are real services wired to
their own :class:`FakeGraphQLClient`, so guide resolution runs end to end.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import pytest

from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)
from peek_app_utilities.internal.peek.timeslots.timeslot_service import TimeslotService
from peek_app_utilities.models.peek.timeslot import (
    AssignGuideError,
    AssignGuideResult,
    GuideAssignment,
    UpdateTimeslotResult,
)
from tests.conftest import FakeGraphQLClient


def guide_pool(id: str, name: str, account_user_id: str | None = None) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "imageUrl": None,
        "mode": "ALL",
        "colorHex": None,
        "quantity": None,
        "category": "guide",
        "capacity": None,
        "resourceTrackingMode": None,
        "accountUser": {"id": account_user_id, "name": name} if account_user_id else None,
    }


def user_edge(id: str, name: str) -> dict[str, Any]:
    return {
        "cursor": id,
        "node": {
            "id": id,
            "name": name,
            "email": f"{id}@example.com",
            "phone": "+1000",
            "status": "ACTIVE",
            "assignedActivities": [],
        },
    }


def build_service(
    gql: FakeGraphQLClient,
    pools: Sequence[dict[str, Any]] = (),
    users: Sequence[dict[str, Any]] = (),
) -> TimeslotService:
    pool_client = FakeGraphQLClient().queue({"resourcePools": list(pools)})
    user_client = FakeGraphQLClient().queue({"accountUsers": {"edges": list(users)}})
    return TimeslotService(
        gql,  # type: ignore[arg-type]
        resource_pool_service=ResourcePoolService(pool_client),  # type: ignore[arg-type]
        account_user_service=AccountUserService(user_client),  # type: ignore[arg-type]
    )


TIMESLOT_NODE: dict[str, Any] = {
    "id": "act-1|ts-1",
    "bookingCount": 1,
    "availableSpots": 9,
    "maxPartySize": 4,
    "totalCapacity": 10,
    "checkedInCount": 0,
    "manifestNotes": None,
    "minuteLength": 60,
    "status": "OPEN",
    "date": "2026-01-02",
    "inheritedResourceAllocations": [],
}

SUCCESS_RESULT: dict[str, Any] = {
    "resourceAllocationBulkRequest": {"__typename": "ResourceAllocationRequest", "id": "req-1"}
}


# ─── get_for_day ──────────────────────────────────────────────────────────────


async def test_get_for_day_normalizes_the_date_builds_filter_variables_and_converts_nodes(gql):
    gql.queue({"timeslots": {"timeslots": [TIMESLOT_NODE]}})

    result = await build_service(gql).get_for_day("act-1", "2026-01-02T10:00:00Z", "withBookings")

    assert [t.id for t in result] == ["act-1|ts-1"]
    assert result[0].product_id == "act-1"
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    params = gql.last_call.variables["params"]
    assert params["activityIds"] == ["act-1"]
    assert params["dateRange"] == "[2026-01-02,2026-01-02]"
    assert params["hasBookings"] is True


async def test_get_for_day_omits_has_bookings_for_the_default_all_filter(gql):
    gql.queue({"timeslots": {"timeslots": []}})

    await build_service(gql).get_for_day("act-1", "2026-01-02")

    assert "hasBookings" not in gql.last_call.variables["params"]


async def test_get_for_day_sets_has_bookings_false_for_without_bookings(gql):
    gql.queue({"timeslots": {"timeslots": []}})

    await build_service(gql).get_for_day("act-1", "2026-01-02", "withoutBookings")

    assert gql.last_call.variables["params"]["hasBookings"] is False


async def test_get_for_day_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await build_service(gql).get_for_day("act-1", "2026-01-02") == []


# ─── get_by_id ────────────────────────────────────────────────────────────────


async def test_get_by_id_returns_the_timeslot_with_the_product_id_parsed_from_the_id(gql):
    gql.queue({"timeslot": {"timeslot": TIMESLOT_NODE}})

    timeslot = await build_service(gql).get_by_id("act-1|ts-1")

    assert timeslot is not None
    assert timeslot.id == "act-1|ts-1"
    assert timeslot.product_id == "act-1"
    assert gql.last_call.variables == {"id": "act-1|ts-1"}


async def test_get_by_id_returns_none_when_there_is_no_timeslot(gql):
    gql.queue({"timeslot": None})
    assert await build_service(gql).get_by_id("x") is None


# ─── update operations ────────────────────────────────────────────────────────


async def test_set_availability_sends_status_and_returns_the_updated_values(gql):
    gql.queue(
        {"updateTimeslot": {"timeslot": {"id": "ts-1", "manifestNotes": None, "status": "CLOSED"}}}
    )

    result = await build_service(gql).set_availability("ts-1", "CLOSED")

    assert result == UpdateTimeslotResult(manifest_notes=None, status="CLOSED")
    assert gql.last_call.variables["input"] == {"id": "ts-1", "status": "CLOSED"}


async def test_set_notes_sends_manifest_notes_and_defaults_missing_fields_to_none(gql):
    gql.queue({})

    result = await build_service(gql).set_notes("ts-1", "Bring sunscreen")

    assert result == UpdateTimeslotResult(manifest_notes=None, status=None)
    assert gql.last_call.variables["input"] == {"id": "ts-1", "manifestNotes": "Bring sunscreen"}


# ─── assign_guide ─────────────────────────────────────────────────────────────


async def test_assign_guide_matches_guides_and_returns_the_allocation_request_id(gql):
    gql.queue(SUCCESS_RESULT)
    service = build_service(
        gql, pools=[guide_pool("pool-1", "Ada", "u1"), guide_pool("pool-eq", "Kayak")]
    )

    result = await service.assign_guide(
        GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["u1"], action="assign")
    )

    assert result == AssignGuideResult(
        status="success", resource_allocation_request_id="req-1", errors=None
    )
    assert gql.last_call.variables["input"] == {
        "timeslotIds": ["ts-1"],
        "resourcePoolIds": ["pool-1"],
        "status": "ACTIVE",
    }


async def test_assign_guide_resolves_a_guide_through_the_account_user_service(gql):
    gql.queue(SUCCESS_RESULT)
    service = build_service(
        gql, pools=[guide_pool("pool-1", "Ada")], users=[user_edge("u1", "Ada")]
    )

    await service.assign_guide(
        GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["u1"], action="assign")
    )

    assert gql.last_call.variables["input"]["resourcePoolIds"] == ["pool-1"]


async def test_assign_guide_ignores_pools_outside_the_guide_category(gql):
    gql.queue_body({})
    equipment = {**guide_pool("pool-1", "Ada"), "category": "equipment"}
    service = build_service(gql, pools=[equipment])

    with pytest.raises(ValueError, match="Guide not found: pool-1"):
        await service.assign_guide(
            GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["pool-1"], action="assign")
        )


async def test_assign_guide_uses_removal_status_when_unassigning(gql):
    gql.queue(
        {"resourceAllocationBulkRequest": {"__typename": "ResourceAllocationRequest", "id": "r"}}
    )
    service = build_service(gql, pools=[guide_pool("pool-1", "Ada")])

    await service.assign_guide(
        GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["pool-1"], action="unassign")
    )

    assert gql.last_call.variables["input"]["status"] == "REMOVAL"


async def test_assign_guide_returns_an_error_result_on_a_generic_error_response(gql):
    gql.queue({"resourceAllocationBulkRequest": {"__typename": "GenericError", "message": "nope"}})
    service = build_service(gql, pools=[guide_pool("pool-1", "Ada")])

    result = await service.assign_guide(
        GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["pool-1"], action="assign")
    )

    assert result == AssignGuideResult(
        status="error",
        resource_allocation_request_id=None,
        errors=[AssignGuideError(message="nope")],
    )


async def test_assign_guide_falls_back_to_a_generic_message_when_no_data_is_returned(gql):
    gql.queue_body({})
    service = build_service(gql, pools=[guide_pool("pool-1", "Ada")])

    result = await service.assign_guide(
        GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["pool-1"], action="assign")
    )

    assert result.status == "error"
    assert result.errors == [AssignGuideError(message="Unknown error")]


async def test_assign_guide_raises_when_timeslots_or_guides_are_empty(gql):
    service = build_service(gql)

    with pytest.raises(ValueError, match=re.compile("at least one timeslot and one guide", re.I)):
        await service.assign_guide(
            GuideAssignment(timeslot_ids=[], guide_ids=["u1"], action="assign")
        )
    with pytest.raises(ValueError, match=re.compile("at least one timeslot and one guide", re.I)):
        await service.assign_guide(
            GuideAssignment(timeslot_ids=["ts-1"], guide_ids=[], action="assign")
        )
    assert gql.calls == []


async def test_assign_guide_raises_on_an_invalid_action(gql):
    service = build_service(gql)

    with pytest.raises(ValueError, match=re.compile("invalid action", re.I)):
        await service.assign_guide(
            GuideAssignment(
                timeslot_ids=["ts-1"],
                guide_ids=["u1"],
                action="delete",  # type: ignore[arg-type]
            )
        )
    assert gql.calls == []


async def test_assign_guide_raises_when_a_guide_cannot_be_matched(gql):
    service = build_service(gql, pools=[guide_pool("pool-1", "Ada")])

    with pytest.raises(ValueError, match="Guide not found: ghost"):
        await service.assign_guide(
            GuideAssignment(timeslot_ids=["ts-1"], guide_ids=["ghost"], action="assign")
        )
    assert gql.calls == []
