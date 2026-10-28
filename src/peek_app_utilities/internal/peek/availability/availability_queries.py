"""Raw Peek GraphQL query and response shape for availability times. Internal.
The node matches the public :class:`AvailabilityTime` model one-to-one, so the
only mapping is the camelCase → snake_case rename done by
:func:`from_availability_time_node`.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.availability_time import (
    Availability,
    AvailabilityTime,
    AvailabilityTimesQuery,
    Duration,
    DurationLength,
)

AVAILABILITY_TIMES_QUERY: Final = """
  query Sales($activityId: ID!, $resourceOptionQuantities: [ResourceOptionQuantityData!]!, $date: Date!) {
    availabilityTimes(activityId: $activityId, resourceOptionQuantities: $resourceOptionQuantities, date: $date) {
      id
      time
      from
      end
      duration {
        name
        length {
          amount
          unit
        }
      }
      status
      availability {
        qty
        taken
        resourceOptionId
      }
    }
  }
"""
"""Fetches availability times for an activity/date and resource-option quantities."""


class DurationLengthNode(TypedDict, total=False):
    amount: int | float | None
    unit: str | None


class DurationNode(TypedDict, total=False):
    name: str | None
    length: DurationLengthNode | None


class AvailabilityNode(TypedDict, total=False):
    qty: int | None
    taken: int | None
    resourceOptionId: str | None


# Functional form because `from` (a wire key) is a Python keyword.
AvailabilityTimeNode = TypedDict(
    "AvailabilityTimeNode",
    {
        "id": str,
        "time": str,
        "from": str,
        "end": str,
        "duration": DurationNode | None,
        "status": str,
        "availability": list[AvailabilityNode] | None,
    },
    total=False,
)
"""A single availability-time node as returned by :data:`AVAILABILITY_TIMES_QUERY`."""


class AvailabilityTimesResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`AVAILABILITY_TIMES_QUERY`."""

    availabilityTimes: list[AvailabilityTimeNode] | None


def build_availability_times_variables(query: AvailabilityTimesQuery) -> dict[str, Any]:
    """Builds the wire variables for :data:`AVAILABILITY_TIMES_QUERY`."""
    return {
        "activityId": query.activity_id,
        "resourceOptionQuantities": [
            {"resourceOptionId": q.resource_option_id, "quantity": q.quantity}
            for q in query.resource_option_quantities
        ],
        "date": query.date,
    }


def from_availability_time_node(node: AvailabilityTimeNode) -> AvailabilityTime:
    """Renames a raw availability-time node into the clean :class:`AvailabilityTime`."""
    duration: DurationNode = node.get("duration") or {}
    length: DurationLengthNode = duration.get("length") or {}
    return AvailabilityTime(
        id=node.get("id") or "",
        time=node.get("time") or "",
        from_=node.get("from") or "",
        end=node.get("end") or "",
        duration=Duration(
            name=duration.get("name") or "",
            length=DurationLength(
                amount=int(length.get("amount") or 0), unit=length.get("unit") or ""
            ),
        ),
        status=node.get("status") or "",
        availability=[_from_availability_node(a) for a in node.get("availability") or []],
    )


def _from_availability_node(node: AvailabilityNode) -> Availability:
    return Availability(
        qty=int(node.get("qty") or 0),
        taken=int(node.get("taken") or 0),
        resource_option_id=node.get("resourceOptionId") or "",
    )
