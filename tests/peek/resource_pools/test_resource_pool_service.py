"""Port of test/peek/resource-pools/resource-pool-service.test.ts."""

from __future__ import annotations

from typing import Any

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.resource_pools.resource_pool_queries import (
    RESOURCE_POOLS_QUERY,
)
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)

POOL: dict[str, Any] = {
    "id": "pool-1",
    "name": "Ada",
    "imageUrl": None,
    "mode": "ALL",
    "colorHex": None,
    "quantity": None,
    "category": "guide",
    "capacity": 5,
    "resourceTrackingMode": None,
    "accountUser": {"id": "u1", "name": "Ada"},
}


async def test_get_all_defaults_to_the_all_mode_filter_and_converts_the_response(gql):
    gql.queue({"resourcePools": [POOL]})

    pools = await ResourcePoolService(gql).get_all()

    assert len(pools) == 1
    assert pools[0].id == "pool-1"
    assert gql.last_call.variables["filter"]["mode"] == "ALL"
    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.query == RESOURCE_POOLS_QUERY


async def test_get_all_passes_through_an_explicit_mode_filter(gql):
    gql.queue({"resourcePools": []})

    pools = await ResourcePoolService(gql).get_all("ACTIVITY")

    assert pools == []
    assert gql.last_call.variables["filter"]["mode"] == "ACTIVITY"


async def test_get_all_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await ResourcePoolService(gql).get_all() == []
