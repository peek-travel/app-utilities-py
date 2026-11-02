"""Resource-pool operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_resource_pool_service()`` rather
than constructing it directly — the access service wires in the authenticated,
shared transport.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.resource_pools.resource_pool_converter import (
    from_resource_pools_response,
)
from peek_app_utilities.internal.peek.resource_pools.resource_pool_queries import (
    RESOURCE_POOLS_QUERY,
)
from peek_app_utilities.models.peek.resource_pool import ResourcePool, ResourcePoolMode

DEFAULT_MODE: Final[ResourcePoolMode] = "ALL"
"""Default mode filter (matches the connector)."""


class ResourcePoolService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_all(self, mode: ResourcePoolMode | None = None) -> list[ResourcePool]:
        """Returns all resource pools for the given mode filter (defaults to ``"ALL"``)."""
        resolved_mode = mode if mode is not None else DEFAULT_MODE
        body = await self._client.request(
            SALES_ENDPOINT, RESOURCE_POOLS_QUERY, {"filter": {"mode": resolved_mode}}
        )
        return from_resource_pools_response(body.get("data"))
