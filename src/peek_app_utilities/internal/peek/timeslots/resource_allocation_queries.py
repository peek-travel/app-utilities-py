"""Raw Peek GraphQL mutation and shapes for bulk resource-allocation requests
(used by guide assignment). Internal.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, Literal, TypedDict

RESOURCE_ALLOCATION_BULK_REQUEST_MUTATION: Final = """
  mutation ResourceAllocationBulkRequest($input: ResourceAllocationBulkRequestInput!) {
    resourceAllocationBulkRequest(input: $input) {
      __typename
      ... on ResourceAllocationRequest {
        id
      }
      ... on GenericError {
        __typename
        message
      }
    }
  }
"""
"""Bulk-(un)assigns resources (e.g. guides) to timeslots."""

ResourceAllocationStatus = Literal["ACTIVE", "REMOVAL"]
"""Allocation status: assigning (``ACTIVE``) or unassigning (``REMOVAL``)."""

ALLOCATION_STATUS_ACTIVE: Final = "ACTIVE"
ALLOCATION_STATUS_REMOVAL: Final = "REMOVAL"

TYPENAME_RESOURCE_ALLOCATION_REQUEST: Final = "ResourceAllocationRequest"
"""``__typename`` of the success variant of the bulk-request result."""
TYPENAME_GENERIC_ERROR: Final = "GenericError"
"""``__typename`` of the failure variant of the bulk-request result."""

# Functional syntax: ``__typename`` would be name-mangled in a class body.
ResourceAllocationBulkRequestResultNode = TypedDict(
    "ResourceAllocationBulkRequestResultNode",
    {"__typename": str, "id": str, "message": str},
    total=False,
)
"""The union result of the bulk request: ``{__typename: "ResourceAllocationRequest",
id}`` on success, ``{__typename: "GenericError", message}`` on failure."""


class ResourceAllocationBulkRequestResponse(TypedDict, total=False):
    """``data`` payload of :data:`RESOURCE_ALLOCATION_BULK_REQUEST_MUTATION`."""

    resourceAllocationBulkRequest: ResourceAllocationBulkRequestResultNode | None


def build_resource_allocation_variables(
    timeslot_ids: Sequence[str],
    resource_pool_ids: Sequence[str],
    status: ResourceAllocationStatus,
) -> dict[str, Any]:
    """Builds the variables for :data:`RESOURCE_ALLOCATION_BULK_REQUEST_MUTATION`."""
    return {
        "input": {
            "timeslotIds": list(timeslot_ids),
            "resourcePoolIds": list(resource_pool_ids),
            "status": status,
        }
    }
