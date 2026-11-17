"""Port of test/peek/resource-pools/resource-pool-converter.test.ts."""

from __future__ import annotations

from typing import Any, cast

from peek_app_utilities.internal.peek.resource_pools.resource_pool_converter import (
    from_resource_pools_response,
)
from peek_app_utilities.internal.peek.resource_pools.resource_pool_queries import (
    ResourcePoolsResponse,
)
from peek_app_utilities.models.peek.resource_pool import ResourcePool, ResourcePoolAccountUser


def empty_pool_node() -> dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "imageUrl": None,
        "mode": "",
        "colorHex": None,
        "quantity": None,
        "category": "",
        "capacity": None,
        "resourceTrackingMode": None,
        "accountUser": None,
    }


def response(*pools: dict[str, Any]) -> ResourcePoolsResponse:
    return cast("ResourcePoolsResponse", {"resourcePools": list(pools)})


def test_maps_a_full_resource_pool_node():
    full = response(
        {
            "id": "pool-1",
            "name": "Ada",
            "imageUrl": "https://img/ada.png",
            "mode": "ACTIVITY",
            "colorHex": "#112233",
            "quantity": 3,
            "category": "guide",
            "capacity": 10,
            "resourceTrackingMode": "INDIVIDUAL",
            "accountUser": {"id": "u1", "name": "Ada Guide"},
        }
    )

    assert from_resource_pools_response(full) == [
        ResourcePool(
            id="pool-1",
            name="Ada",
            image_url="https://img/ada.png",
            mode="ACTIVITY",
            color_hex="#112233",
            quantity=3,
            category="guide",
            capacity=10,
            resource_tracking_mode="INDIVIDUAL",
            account_user=ResourcePoolAccountUser(id="u1", name="Ada Guide"),
        )
    ]


def test_applies_none_empty_defaults_and_a_none_account_user():
    assert from_resource_pools_response(response(empty_pool_node())) == [
        ResourcePool(
            id="",
            name="",
            image_url=None,
            mode="",
            color_hex=None,
            quantity=None,
            category="",
            capacity=None,
            resource_tracking_mode=None,
            account_user=None,
        )
    ]


def test_defaults_empty_account_user_id_name_to_empty_strings():
    with_blank_user = response({**empty_pool_node(), "accountUser": {"id": "", "name": ""}})

    assert from_resource_pools_response(with_blank_user)[0].account_user == ResourcePoolAccountUser(
        id="", name=""
    )


def test_returns_an_empty_list_for_missing_data():
    assert from_resource_pools_response(None) == []
    assert from_resource_pools_response({}) == []
