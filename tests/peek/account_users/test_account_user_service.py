"""Port of test/peek/account-users/account-user-service.test.ts."""

from __future__ import annotations

from typing import Any

from peek_app_utilities.internal.peek.account_users.account_user_queries import (
    USER_BY_FILTER_QUERY,
    USER_QUERY,
)
from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
    AccountUserServiceOptions,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT


def active_node(id: str) -> dict[str, Any]:
    return {
        "id": id,
        "name": f"User {id}",
        "email": f"{id}@example.com",
        "phone": "+1000",
        "status": "ACTIVE",
        "assignedActivities": [],
    }


def edge(id: str, status: str = "ACTIVE") -> dict[str, Any]:
    return {"cursor": id, "node": {**active_node(id), "status": status}}


# ─── get_all ──────────────────────────────────────────────────────────────────


async def test_get_all_paginates_and_returns_only_active_users(gql):
    gql.queue(
        {
            "accountUsers": {
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                "edges": [edge("u1"), edge("u2", "INACTIVE")],
            }
        }
    ).queue(
        {
            "accountUsers": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [edge("u3")],
            }
        }
    )

    users = await AccountUserService(gql).get_all()

    assert [u.id for u in users] == ["u1", "u3"]
    assert len(gql.calls) == 2
    assert gql.calls[0].endpoint_name == SALES_ENDPOINT
    assert gql.calls[0].query == USER_QUERY
    assert gql.calls[0].variables == {"first": 50, "after": None}
    assert gql.calls[1].variables == {"first": 50, "after": "c1"}


async def test_get_all_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await AccountUserService(gql).get_all() == []


async def test_get_all_stops_after_one_page_when_page_info_is_absent_and_honors_page_size(gql):
    gql.queue({"accountUsers": {"edges": [edge("u1")]}})

    users = await AccountUserService(gql, AccountUserServiceOptions(page_size=5)).get_all()

    assert [u.id for u in users] == ["u1"]
    assert len(gql.calls) == 1
    assert gql.calls[0].variables["first"] == 5


async def test_get_all_uses_the_default_page_size_when_options_leave_it_unset(gql):
    gql.queue({"accountUsers": {"edges": []}})

    await AccountUserService(gql, AccountUserServiceOptions()).get_all()

    assert gql.calls[0].variables["first"] == 50


# ─── get_by_id ────────────────────────────────────────────────────────────────


async def test_get_by_id_returns_the_matching_active_user(gql):
    gql.queue({"accountUsers": {"edges": [edge("u1")]}})

    user = await AccountUserService(gql).get_by_id("u1")

    assert user is not None
    assert user.id == "u1"
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.query == USER_BY_FILTER_QUERY
    assert gql.last_call.variables == {"first": 50, "filter": {"ids": ["u1"]}}


async def test_get_by_id_returns_none_when_there_is_no_match(gql):
    gql.queue_body({})
    assert await AccountUserService(gql).get_by_id("missing") is None


async def test_get_by_id_returns_none_when_the_matched_user_is_inactive(gql):
    gql.queue({"accountUsers": {"edges": [edge("u1", "INACTIVE")]}})
    assert await AccountUserService(gql).get_by_id("u1") is None
