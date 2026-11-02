"""Port of test/peek/timeslots/guide-matcher.test.ts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from peek_app_utilities.internal.peek.timeslots.guide_matcher import match_guide_to_resource_pool
from peek_app_utilities.models.peek.resource_pool import ResourcePool, ResourcePoolAccountUser


@dataclass(frozen=True)
class User:
    id: str
    name: str


def pool(**overrides: Any) -> ResourcePool:
    fields: dict[str, Any] = {
        "id": "pool-x",
        "name": "Pool X",
        "image_url": None,
        "mode": "ALL",
        "color_hex": None,
        "quantity": None,
        "category": "guide",
        "capacity": None,
        "resource_tracking_mode": None,
        "account_user": None,
    }
    fields.update(overrides)
    return ResourcePool(**fields)


POOLS = [
    pool(id="pool-1", name="Ada", account_user=ResourcePoolAccountUser(id="u1", name="Ada User")),
    pool(id="pool-2", name="Grace", account_user=None),
]
ACCOUNT_USERS = [User("u1", "Ada User"), User("u9", "Nobody")]


def test_matches_by_resource_pool_id():
    assert match_guide_to_resource_pool("pool-2", POOLS, ACCOUNT_USERS) == "pool-2"


def test_matches_by_backing_account_user_id():
    assert match_guide_to_resource_pool("u1", POOLS, ACCOUNT_USERS) == "pool-1"


def test_matches_by_pool_name():
    assert match_guide_to_resource_pool("Grace", POOLS, ACCOUNT_USERS) == "pool-2"


def test_resolves_via_account_user_then_matches_pool_by_account_user_id():
    only_user_linked = [
        pool(id="pool-3", name="X", account_user=ResourcePoolAccountUser(id="u5", name="Eve"))
    ]
    assert match_guide_to_resource_pool("u5", only_user_linked, [User("u5", "Eve")]) == "pool-3"


def test_resolves_via_account_user_then_matches_pool_by_the_users_name():
    named_pool = [pool(id="pool-4", name="Eve", account_user=None)]
    assert match_guide_to_resource_pool("u7", named_pool, [User("u7", "Eve")]) == "pool-4"


def test_returns_none_when_nothing_matches():
    assert match_guide_to_resource_pool("nope", POOLS, ACCOUNT_USERS) is None


def test_returns_none_when_the_resolved_user_has_no_matching_pool():
    assert match_guide_to_resource_pool("u9", POOLS, ACCOUNT_USERS) is None
