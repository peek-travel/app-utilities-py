"""Pure functions mapping raw account-user nodes into the clean
:class:`AccountUser` model. Inactive users are dropped (mapped to ``None``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from peek_app_utilities.internal.peek.account_users.account_user_queries import (
    AccountUserNode,
    AssignedActivityNode,
)
from peek_app_utilities.models.peek.account_user import AccountUser, AssignedActivity

ACTIVE_STATUS: Final = "ACTIVE"
"""Only users in this status are surfaced."""


def from_account_user_node(node: AccountUserNode | None) -> AccountUser | None:
    """Converts a single node into an :class:`AccountUser`, or ``None`` when the
    node is missing or the user is not active."""
    if not node or node.get("status") != ACTIVE_STATUS:
        return None
    return AccountUser(
        id=node.get("id") or "",
        name=node.get("name") or "",
        email=node.get("email") or "",
        phone=node.get("phone") or "",
        assigned_activities=[
            _from_assigned_activity(activity) for activity in node.get("assignedActivities") or []
        ],
    )


def from_account_user_nodes(nodes: Iterable[AccountUserNode | None]) -> list[AccountUser]:
    """Converts a list of nodes into active :class:`AccountUser` models, dropping
    the rest."""
    users: list[AccountUser] = []
    for node in nodes:
        user = from_account_user_node(node)
        if user is not None:
            users.append(user)
    return users


def _from_assigned_activity(activity: AssignedActivityNode) -> AssignedActivity:
    return AssignedActivity(id=activity.get("id") or "", name=activity.get("name") or "")
