"""Port of test/peek/account-users/account-user-converter.test.ts."""

from __future__ import annotations

from typing import Any, cast

from peek_app_utilities.internal.peek.account_users.account_user_converter import (
    from_account_user_node,
    from_account_user_nodes,
)
from peek_app_utilities.internal.peek.account_users.account_user_queries import AccountUserNode
from peek_app_utilities.models.peek.account_user import AccountUser, AssignedActivity

ACTIVE_NODE_RAW: dict[str, Any] = {
    "id": "u1",
    "name": "Ada Guide",
    "email": "ada@example.com",
    "phone": "+1000",
    "status": "ACTIVE",
    "assignedActivities": [{"id": "act-1", "name": "Kayak Tour"}],
}


def node(**overrides: Any) -> AccountUserNode:
    """A copy of the active raw node with ``overrides`` applied."""
    return cast("AccountUserNode", {**ACTIVE_NODE_RAW, **overrides})


ACTIVE_NODE = node()


def test_maps_an_active_node_dropping_status():
    assert from_account_user_node(ACTIVE_NODE) == AccountUser(
        id="u1",
        name="Ada Guide",
        email="ada@example.com",
        phone="+1000",
        assigned_activities=[AssignedActivity(id="act-1", name="Kayak Tour")],
    )


def test_returns_none_for_an_inactive_user():
    assert from_account_user_node(node(status="INACTIVE")) is None


def test_returns_none_for_a_missing_node():
    assert from_account_user_node(None) is None
    assert from_account_user_node({}) is None


def test_defaults_assigned_activities_to_an_empty_list():
    user = from_account_user_node(node(assignedActivities=None))
    assert user is not None
    assert user.assigned_activities == []


def test_defaults_missing_scalar_fields_to_empty_strings():
    user = from_account_user_node(
        cast("AccountUserNode", {"status": "ACTIVE", "assignedActivities": [{}]})
    )
    assert user == AccountUser(
        id="", name="", email="", phone="", assigned_activities=[AssignedActivity(id="", name="")]
    )


def test_from_account_user_nodes_keeps_active_users_and_drops_inactive_ones():
    result = from_account_user_nodes(
        [
            ACTIVE_NODE,
            {**ACTIVE_NODE, "id": "u2", "status": "INACTIVE"},
            {**ACTIVE_NODE, "id": "u3"},
        ]
    )
    assert [u.id for u in result] == ["u1", "u3"]
