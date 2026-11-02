"""Raw Peek GraphQL query and response shape for resource pools. Internal —
never re-exported from the public entry point.
"""

from __future__ import annotations

from typing import Final, TypedDict

RESOURCE_POOLS_QUERY: Final = """
  query Sales($filter: ResourcePoolsFilter) {
    resourcePools(filter: $filter) {
      id
      name
      imageUrl
      mode
      colorHex
      quantity
      category
      capacity
      resourceTrackingMode
      accountUser {
        id
        name
      }
    }
  }
"""
"""Fetches resource pools matching a mode filter."""


class ResourcePoolAccountUserNode(TypedDict, total=False):
    """The ``accountUser`` block of a :class:`ResourcePoolNode`."""

    id: str | None
    name: str | None


class ResourcePoolNode(TypedDict, total=False):
    """A single resource-pool node as returned by :data:`RESOURCE_POOLS_QUERY`."""

    id: str | None
    name: str | None
    imageUrl: str | None
    mode: str | None
    colorHex: str | None
    quantity: int | None
    category: str | None
    capacity: int | None
    resourceTrackingMode: str | None
    accountUser: ResourcePoolAccountUserNode | None


class ResourcePoolsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`RESOURCE_POOLS_QUERY`."""

    resourcePools: list[ResourcePoolNode] | None
