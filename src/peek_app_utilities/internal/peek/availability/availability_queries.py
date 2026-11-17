"""Raw Peek GraphQL query and response shape for availability times. Internal.
The raw node is mapped to the public :class:`AvailabilityTime` model by the
availability converter.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.availability_time import AvailabilityTimesQuery

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
      price {
        amount
        currency
        formatted
      }
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


class MoneyNode(TypedDict, total=False):
    amount: str | None
    currency: str | None
    formatted: str | None


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
        "price": MoneyNode | None,
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
