"""Raw Peek GraphQL queries/mutations and response shapes for timeslots.
Internal — never re-exported from the public entry point.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final, NotRequired, TypedDict

from peek_app_utilities.models.peek.timeslot import TimeslotFilter

_TIMESLOT_FIELDS: Final = """
          id
          bookingCount
          availableSpots
          maxPartySize
          totalCapacity
          checkedInCount
          manifestNotes
          minuteLength
          status
          date
          inheritedResourceAllocations {
            id
            status
            quantity
            resourcePool {
              id
              name
              category
              capacity
              accountUser {
                id
              }
            }
          }
          resourceAllocations {
            quantity
            status
            resourcePool {
              id
              name
              category
              capacity
              accountUser {
                id
              }
            }
          }
          ... on VariableTimeslot {
            start
          }
          ... on FixedTimeslot {
            start
          }
"""

TIMESLOTS_QUERY: Final = f"""
  query Sales($params: TimeslotsFilter!) {{
    timeslots(filter: $params) {{
      ... on TimeslotsSuccess {{
        timeslots {{{_TIMESLOT_FIELDS}        }}
      }}
    }}
  }}
"""
"""Fetches timeslots for an activity/date via a filter."""

TIMESLOT_BY_ID_QUERY: Final = f"""
  query Sales($id: ID!) {{
    timeslot(id: $id) {{
      ... on ActivityTimeslotSuccess {{
        timeslot {{{_TIMESLOT_FIELDS}        }}
      }}
    }}
  }}
"""
"""Fetches a single timeslot by id."""

UPDATE_TIMESLOT_MUTATION: Final = """
  mutation Account($input: UpdateTimeslotInput!) {
    updateTimeslot(input: $input) {
      ... on UpdateTimeslotSuccess {
        timeslot {
          id
          manifestNotes
          status
        }
      }
    }
  }
"""
"""Updates a timeslot's manifest notes and/or status."""

FILTER_WITH_BOOKINGS: Final = "withBookings"
FILTER_WITHOUT_BOOKINGS: Final = "withoutBookings"


class TimeslotResourcePoolAccountUserNode(TypedDict, total=False):
    """The ``accountUser`` block of a :class:`TimeslotResourcePoolNode`."""

    id: str | None


class TimeslotResourcePoolNode(TypedDict, total=False):
    """The ``resourcePool`` block of a :class:`TimeslotResourceAllocationNode`."""

    id: str | None
    name: str | None
    category: str | None
    capacity: int | None
    accountUser: TimeslotResourcePoolAccountUserNode | None


class TimeslotResourceAllocationNode(TypedDict, total=False):
    """A single resource allocation on a timeslot node. Shared by both the
    ``inheritedResourceAllocations`` and ``resourceAllocations`` selections; the
    allocation-level ``id`` is only present on the inherited variant."""

    id: str | None
    quantity: int | None
    status: str | None
    resourcePool: TimeslotResourcePoolNode | None


class TimeslotNode(TypedDict, total=False):
    """A single timeslot node as returned by the timeslot queries."""

    id: str | None
    bookingCount: int | None
    availableSpots: int | None
    maxPartySize: int | None
    totalCapacity: int | None
    checkedInCount: int | None
    manifestNotes: str | None
    minuteLength: int | None
    status: str | None
    date: str | None
    start: str | None
    inheritedResourceAllocations: list[TimeslotResourceAllocationNode] | None
    resourceAllocations: list[TimeslotResourceAllocationNode] | None


class TimeslotsSuccessNode(TypedDict, total=False):
    """The ``timeslots`` block of :data:`TIMESLOTS_QUERY`."""

    timeslots: list[TimeslotNode | None] | None


class TimeslotsResponse(TypedDict, total=False):
    """``data`` payload of :data:`TIMESLOTS_QUERY`."""

    timeslots: TimeslotsSuccessNode | None


class SingleTimeslotSuccessNode(TypedDict, total=False):
    """The ``timeslot`` block of :data:`TIMESLOT_BY_ID_QUERY`."""

    timeslot: TimeslotNode | None


class SingleTimeslotResponse(TypedDict, total=False):
    """``data`` payload of :data:`TIMESLOT_BY_ID_QUERY`."""

    timeslot: SingleTimeslotSuccessNode | None


class UpdatedTimeslotNode(TypedDict, total=False):
    """The ``timeslot`` block of :data:`UPDATE_TIMESLOT_MUTATION`."""

    id: str | None
    manifestNotes: str | None
    status: str | None


class UpdateTimeslotSuccessNode(TypedDict, total=False):
    """The ``updateTimeslot`` block of :data:`UPDATE_TIMESLOT_MUTATION`."""

    timeslot: UpdatedTimeslotNode | None


class UpdateTimeslotResponse(TypedDict, total=False):
    """``data`` payload of :data:`UPDATE_TIMESLOT_MUTATION`."""

    updateTimeslot: UpdateTimeslotSuccessNode | None


class UpdateTimeslotInput(TypedDict):
    """Input for :data:`UPDATE_TIMESLOT_MUTATION` (wire keys)."""

    id: str
    manifestNotes: NotRequired[str]
    status: NotRequired[str]


def build_timeslot_variables(product_id: str, date: str, filter: TimeslotFilter) -> dict[str, Any]:
    """Builds the variables for :data:`TIMESLOTS_QUERY`. ``hasBookings`` is only
    set for the ``"withBookings"`` / ``"withoutBookings"`` filters."""
    activity_ids: Sequence[str] = [product_id]
    params: dict[str, Any] = {
        "activityIds": list(activity_ids),
        "dateRange": f"[{date},{date}]",
    }
    if filter == FILTER_WITH_BOOKINGS:
        params["hasBookings"] = True
    elif filter == FILTER_WITHOUT_BOOKINGS:
        params["hasBookings"] = False
    return {"params": params}
