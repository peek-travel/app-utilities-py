"""Pure functions mapping raw resource-pool nodes into the clean
:class:`ResourcePool` model. No I/O.
"""

from __future__ import annotations

from peek_app_utilities.internal.peek.resource_pools.resource_pool_queries import (
    ResourcePoolAccountUserNode,
    ResourcePoolNode,
    ResourcePoolsResponse,
)
from peek_app_utilities.models.peek.resource_pool import ResourcePool, ResourcePoolAccountUser


def from_resource_pools_response(response: ResourcePoolsResponse | None) -> list[ResourcePool]:
    """Converts a resource-pools response into :class:`ResourcePool` models."""
    pools = (response or {}).get("resourcePools") or []
    return [_from_resource_pool_node(pool) for pool in pools]


def _from_resource_pool_node(pool: ResourcePoolNode) -> ResourcePool:
    return ResourcePool(
        id=pool.get("id") or "",
        name=pool.get("name") or "",
        image_url=pool.get("imageUrl"),
        mode=pool.get("mode") or "",
        color_hex=pool.get("colorHex"),
        quantity=pool.get("quantity"),
        category=pool.get("category") or "",
        capacity=pool.get("capacity"),
        resource_tracking_mode=pool.get("resourceTrackingMode"),
        account_user=_from_account_user(pool.get("accountUser")),
    )


def _from_account_user(
    account_user: ResourcePoolAccountUserNode | None,
) -> ResourcePoolAccountUser | None:
    if not account_user:
        return None
    return ResourcePoolAccountUser(
        id=account_user.get("id") or "",
        name=account_user.get("name") or "",
    )
