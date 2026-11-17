"""Timeslot operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_timeslot_service()`` rather than
constructing it directly — the access service wires in the authenticated,
shared transport. The ``assign_guide`` operation composes the resource-pool and
account-user services to resolve guides before issuing the allocation request.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)
from peek_app_utilities.internal.peek.timeslots.guide_matcher import match_guide_to_resource_pool
from peek_app_utilities.internal.peek.timeslots.resource_allocation_queries import (
    ALLOCATION_STATUS_ACTIVE,
    ALLOCATION_STATUS_REMOVAL,
    RESOURCE_ALLOCATION_BULK_REQUEST_MUTATION,
    TYPENAME_RESOURCE_ALLOCATION_REQUEST,
    ResourceAllocationStatus,
    build_resource_allocation_variables,
)
from peek_app_utilities.internal.peek.timeslots.timeslot_converter import (
    from_timeslot_node,
    from_timeslot_nodes,
)
from peek_app_utilities.internal.peek.timeslots.timeslot_queries import (
    TIMESLOT_BY_ID_QUERY,
    TIMESLOTS_QUERY,
    UPDATE_TIMESLOT_MUTATION,
    UpdateTimeslotInput,
    build_timeslot_variables,
)
from peek_app_utilities.models.peek.timeslot import (
    GUIDE_ASSIGNMENT_ACTIONS,
    AssignGuideError,
    AssignGuideResult,
    AssignGuideStatus,
    GuideAssignment,
    Timeslot,
    TimeslotFilter,
    UpdateTimeslotResult,
)

GUIDE_CATEGORY: Final = "guide"
"""Resource-pool category guides are matched within."""
DEFAULT_FILTER: Final[TimeslotFilter] = "all"
ACTION_ASSIGN: Final = "assign"
STATUS_SUCCESS: Final[AssignGuideStatus] = "success"
STATUS_ERROR: Final[AssignGuideStatus] = "error"

ERROR_MISSING_TIMESLOTS_OR_GUIDES: Final = "At least one timeslot and one guide are required"
ERROR_INVALID_ACTION: Final = "Invalid action. Must be either assign or unassign"
ERROR_GUIDE_NOT_FOUND: Final = "Guide not found"
ERROR_UNKNOWN: Final = "Unknown error"

_TIMESLOT_ID_SEPARATOR: Final = "|"
_DATE_TIME_SEPARATOR: Final = "T"


class TimeslotService:
    def __init__(
        self,
        client: GraphQLClient,
        *,
        resource_pool_service: ResourcePoolService,
        account_user_service: AccountUserService,
    ) -> None:
        self._client = client
        self._resource_pool_service = resource_pool_service
        self._account_user_service = account_user_service

    async def get_for_day(
        self, product_id: str, date: str, filter: TimeslotFilter | None = None
    ) -> list[Timeslot]:
        """Returns the timeslots for an activity on a given date. ``date`` is a
        ``YYYY-MM-DD`` string (any time component is dropped); ``filter`` defaults
        to ``"all"``."""
        resolved_filter = filter if filter is not None else DEFAULT_FILTER
        body = await self._client.request(
            SALES_ENDPOINT,
            TIMESLOTS_QUERY,
            build_timeslot_variables(product_id, _normalize_date(date), resolved_filter),
        )
        success = _data(body).get("timeslots") or {}
        return from_timeslot_nodes(success.get("timeslots") or [], product_id)

    async def get_by_id(self, timeslot_id: str) -> Timeslot | None:
        """Returns a single timeslot by id, or ``None`` when not found."""
        body = await self._client.request(SALES_ENDPOINT, TIMESLOT_BY_ID_QUERY, {"id": timeslot_id})
        success = _data(body).get("timeslot") or {}
        node = success.get("timeslot")
        if not node:
            return None
        return from_timeslot_node(node, _extract_product_id(timeslot_id))

    async def set_availability(self, timeslot_id: str, status: str) -> UpdateTimeslotResult:
        """Sets the timeslot's status (e.g. open/closed)."""
        return await self._update_timeslot({"id": timeslot_id, "status": status})

    async def set_notes(self, timeslot_id: str, manifest_notes: str) -> UpdateTimeslotResult:
        """Sets the timeslot's manifest notes."""
        return await self._update_timeslot({"id": timeslot_id, "manifestNotes": manifest_notes})

    async def assign_guide(self, assignment: GuideAssignment) -> AssignGuideResult:
        """Assigns or unassigns guides across timeslots. Guides are resolved to
        resource pools (by pool id, account-user id, or name) before the bulk
        allocation request is issued.

        Example::

            await peek.get_timeslot_service().assign_guide(GuideAssignment(
                timeslot_ids=["ts_2026_06_20_0900"],
                guide_ids=["Alex Guide"],  # pool id, account-user id, or name
                action="assign",
            ))

        :raises ValueError: when ``timeslot_ids`` or ``guide_ids`` is empty, when
            ``action`` is not ``"assign"`` / ``"unassign"``, or when a guide cannot
            be matched to a guide resource pool (``"Guide not found: <id>"``).
        """
        timeslot_ids = assignment.timeslot_ids
        guide_ids = assignment.guide_ids
        action = assignment.action

        if not timeslot_ids or not guide_ids:
            raise ValueError(ERROR_MISSING_TIMESLOTS_OR_GUIDES)
        if action not in GUIDE_ASSIGNMENT_ACTIONS:
            raise ValueError(ERROR_INVALID_ACTION)

        all_pools, account_users = await asyncio.gather(
            self._resource_pool_service.get_all(),
            self._account_user_service.get_all(),
        )
        guide_pools = [pool for pool in all_pools if pool.category == GUIDE_CATEGORY]

        resource_pool_ids: list[str] = []
        for guide_id in guide_ids:
            matched = match_guide_to_resource_pool(guide_id, guide_pools, account_users)
            if matched is None:
                raise ValueError(f"{ERROR_GUIDE_NOT_FOUND}: {guide_id}")
            resource_pool_ids.append(matched)

        status: ResourceAllocationStatus = (
            ALLOCATION_STATUS_ACTIVE if action == ACTION_ASSIGN else ALLOCATION_STATUS_REMOVAL
        )

        body = await self._client.request(
            SALES_ENDPOINT,
            RESOURCE_ALLOCATION_BULK_REQUEST_MUTATION,
            build_resource_allocation_variables(timeslot_ids, resource_pool_ids, status),
        )

        result = _data(body).get("resourceAllocationBulkRequest") or {}
        if result.get("__typename") == TYPENAME_RESOURCE_ALLOCATION_REQUEST:
            return AssignGuideResult(
                status=STATUS_SUCCESS,
                resource_allocation_request_id=result.get("id"),
                errors=None,
            )

        message = result.get("message")
        return AssignGuideResult(
            status=STATUS_ERROR,
            resource_allocation_request_id=None,
            errors=[AssignGuideError(message=message if message is not None else ERROR_UNKNOWN)],
        )

    async def _update_timeslot(self, input: UpdateTimeslotInput) -> UpdateTimeslotResult:
        body = await self._client.request(
            SALES_ENDPOINT, UPDATE_TIMESLOT_MUTATION, {"input": dict(input)}
        )
        success = _data(body).get("updateTimeslot") or {}
        timeslot = success.get("timeslot") or {}
        return UpdateTimeslotResult(
            manifest_notes=timeslot.get("manifestNotes"),
            status=timeslot.get("status"),
        )


def _data(body: dict[str, Any]) -> dict[str, Any]:
    """The ``data`` block of a response body, or ``{}``."""
    data: dict[str, Any] = body.get("data") or {}
    return data


def _extract_product_id(timeslot_id: str) -> str:
    """Activity timeslot ids are ``"<activityId>|..."``; the activity id is the
    product id."""
    return timeslot_id.split(_TIMESLOT_ID_SEPARATOR)[0]


def _normalize_date(date: str) -> str:
    """Timeslot day queries expect a ``YYYY-MM-DD`` date; drop any time component."""
    return date.split(_DATE_TIME_SEPARATOR)[0]
