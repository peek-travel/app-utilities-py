"""Availability-times operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_availability_service()``.
"""

from __future__ import annotations

from peek_app_utilities.internal.peek.availability.availability_queries import (
    AVAILABILITY_TIMES_QUERY,
    build_availability_times_variables,
    from_availability_time_node,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.models.peek.availability_time import (
    AvailabilityTime,
    AvailabilityTimesQuery,
)


class AvailabilityService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_availability_times(self, query: AvailabilityTimesQuery) -> list[AvailabilityTime]:
        """Returns the availability times for an activity/date and requested
        quantities. Returns ``[]`` when the response carries no data."""
        body = await self._client.request(
            SALES_ENDPOINT, AVAILABILITY_TIMES_QUERY, build_availability_times_variables(query)
        )
        data = body.get("data") or {}
        return [from_availability_time_node(node) for node in data.get("availabilityTimes") or []]
