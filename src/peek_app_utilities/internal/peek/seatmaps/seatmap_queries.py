"""Raw Peek GraphQL queries/mutations and response shapes for seating maps.
Internal — never re-exported from the public entry point.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.seatmap import SeatmapBlockAssignment

_ZONES_SELECTION: Final = """
        zones {
          id
          name
          colorHex
          resourceOptions {
            id
            name
          }
        }"""
"""The zone (pricing tier) selection shared by every full seating-map read."""

_SECTION_DISPLAY_SELECTION: Final = """
          display {
            label
            x
            y
            width
            height
            type
          }"""
"""The display geometry selected on a section."""

_GROUP_DISPLAY_SELECTION: Final = """
            display {
              x
              y
              tableWidth
              tableHeight
              table
            }"""
"""The display geometry selected on a group (table)."""

_BLOCK_FIELDS: Final = """
              fullBlockName
              name
              id
              order
              zone {
                id
              }
              display {
                x
                y
              }"""
"""The structural fields selected on a block (seat)."""

SEATMAPS_QUERY: Final = f"""
  query Sales($id: ID!) {{
    activity(id: $id) {{
      seatingMaps {{
        name
        id{_ZONES_SELECTION}
        sections {{
          id{_SECTION_DISPLAY_SELECTION}
          groups {{
            assignableTo
            name
            id{_GROUP_DISPLAY_SELECTION}
            blocks {{{_BLOCK_FIELDS}
            }}
          }}
        }}
      }}
    }}
  }}
"""
"""Fetches every seating map configured on a single activity (product)."""

SEATMAP_IDS_QUERY: Final = """
  query Sales($id: ID!) {
    activity(id: $id) {
      seatingMaps {
        id
        name
      }
    }
  }
"""
"""Fetches just the id + name of every seating map on a single activity
(product) — the simplified counterpart of :data:`SEATMAPS_QUERY`, selecting no
zones, sections, groups, or blocks."""

_PRIMARY_GUEST_SELECTION: Final = "primaryGuest { firstName lastName }"
"""The PII-gated primary-guest selection (name only)."""


def _primary_guest_selection(full_customer_access: bool) -> str:
    """The primary-guest selection, or nothing when PII is off."""
    return _PRIMARY_GUEST_SELECTION if full_customer_access else ""


def build_seatmap_assignments_query(full_customer_access: bool) -> str:
    """Builds the seat-assignments query for a product's seating maps over a
    datetime range. It reads the same ``activity(id).seatingMaps`` entry as
    :data:`SEATMAPS_QUERY` and selects the same structural fields (zones,
    section/group/block geometry) plus each seat's ``availability`` for the range.

    The booking's ``primaryGuest`` is **customer PII**, so it is selected only
    when ``full_customer_access`` is on — otherwise the API never returns it and
    a guest occupant's name maps to ``None``. Staff (``AccountUser``) names are
    not PII and are always selected.
    """
    primary_guest = _primary_guest_selection(full_customer_access)
    return f"""
  query SeatMapAssignments($id: ID!, $range: NaiveDatetimeRange!) {{
    activity(id: $id) {{
      seatingMaps {{
        id
        name{_ZONES_SELECTION}
        sections(datetimeRange: $range) {{
          id{_SECTION_DISPLAY_SELECTION}
          groups {{
            assignableTo
            name
            id{_GROUP_DISPLAY_SELECTION}
            blocks {{{_BLOCK_FIELDS}
              availability(datetimeRange: $range) {{
                status
                assignments {{
                  id
                  parent {{
                    __typename
                    ... on Ticket {{
                      id
                      resourceOptionSnapshot {{
                        id
                        name
                      }}
                      booking {{
                        id
                        displayId
                        activityId
                        activitySnapshot {{
                          id
                          name
                        }}
                        startsAt
                        endsAt
                        {primary_guest}
                      }}
                    }}
                    ... on AccountUser {{
                      id
                      name
                    }}
                    ... on FieldLocation {{
                      id
                    }}
                    ... on BlockedSeat {{
                      id
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
"""


SEATMAP_ASSIGNMENT_PARENTS: Final[tuple[str, ...]] = (
    "Ticket",
    "AccountUser",
    "FieldLocation",
    "BlockedSeat",
)
"""The assignment-parent typenames the converter recognizes."""

PARENT_TICKET: Final = "Ticket"
PARENT_ACCOUNT_USER: Final = "AccountUser"
PARENT_FIELD_LOCATION: Final = "FieldLocation"
PARENT_BLOCKED_SEAT: Final = "BlockedSeat"


def build_assignable_bookings_query(full_customer_access: bool) -> str:
    """Builds the assignable-bookings query: confirmed bookings on a product that
    overlap a datetime range, with the tickets that can be assigned to seats.

    The booking's ``primaryGuest`` is **customer PII**, selected only when
    ``full_customer_access`` is on; otherwise the API never returns it and the
    guest name maps to ``None``.
    """
    primary_guest = _primary_guest_selection(full_customer_access)
    return f"""
  query AssignableBookings($id: ID!, $range: NaiveDatetimeRange!) {{
    bookings(filter: {{
      activityIds: [$id]
      overlapsRange: $range
      reservationStatuses: [CONFIRMED]
    }}) {{
      id
      displayId
      startsAt
      endsAt
      operatorNotes
      {primary_guest}
      tickets {{
        hashid
        resourceOptionSnapshot {{
          id
          name
        }}
        seatingAssignment {{
          id
          block {{
            id
            fullBlockName
          }}
        }}
      }}
    }}
  }}
"""


ASSIGNMENT_SUCCESS_TYPENAME: Final = "AssignmentResponse"
"""The union member ``__typename`` the API returns for a successful assignment."""

_ALIAS_PREFIX: Final = "a"
_ASSIGNABLE_VAR_PREFIX: Final = "assignable"
_BLOCKS_VAR_PREFIX: Final = "blocks"


def assign_blocks_alias(index: int) -> str:
    """The response alias for the i-th assignment (keeps the service and converter in sync)."""
    return f"{_ALIAS_PREFIX}{index}"


def _assignable_var(index: int) -> str:
    return f"{_ASSIGNABLE_VAR_PREFIX}{index}"


def _blocks_var(index: int) -> str:
    return f"{_BLOCKS_VAR_PREFIX}{index}"


def build_assign_blocks_mutation(count: int) -> str:
    """Builds the bulk ``assignBlocks`` mutation: one aliased call per
    assignment, each selecting ``__typename`` plus the shared ``R`` fragment so a
    per-assignment error union member comes back inline (rather than as a
    top-level GraphQL error)."""
    decls = [f"${_assignable_var(i)}: ID!, ${_blocks_var(i)}: [ID!]!" for i in range(count)]
    fields = [
        f"{assign_blocks_alias(i)}: assignBlocks(assignableId: ${_assignable_var(i)}, "
        f"blockIds: ${_blocks_var(i)}, fieldResponses: []) {{ __typename ...R }}"
        for i in range(count)
    ]
    joined_fields = "\n    ".join(fields)
    return f"""
  mutation AssignBlocks({", ".join(decls)}) {{
    {joined_fields}
  }}

  fragment R on AssignBlocksResponse {{
    ... on AssignmentResponse {{
      assignments {{
        id
        block {{
          id
          fullBlockName
        }}
        parent {{
          ... on Ticket {{
            hashid
          }}
        }}
      }}
    }}
    ... on AssignBlocksErrorInvalidBlockCount {{
      message
      numNeeded
      numProvided
    }}
    ... on AssignBlocksErrorInvalidType {{
      message
    }}
    ... on AssignBlocksErrorOverbooking {{
      message
    }}
  }}
"""


def assign_blocks_variables(assignments: Iterable[SeatmapBlockAssignment]) -> dict[str, Any]:
    """Builds the GraphQL variables for :func:`build_assign_blocks_mutation`."""
    variables: dict[str, Any] = {}
    for i, assignment in enumerate(assignments):
        variables[_assignable_var(i)] = assignment.assignable_id
        variables[_blocks_var(i)] = [assignment.block_id]
    return variables


DELETE_ASSIGNMENTS_SUCCESS_TYPENAME: Final = "DeleteAssignmentsSuccess"
"""The union member ``__typename`` the API returns for a successful delete."""

DELETE_ASSIGNMENTS_MUTATION: Final = """
  mutation ClearSeats($assignmentIds: [ID!]!) {
    deleteAssignments(assignmentIds: $assignmentIds) {
      __typename
      ... on DeleteAssignmentsSuccess {
        assignments {
          id
          block {
            id
            fullBlockName
          }
          parent {
            __typename
            ... on Ticket {
              hashid
            }
          }
        }
      }
      ... on AssignBlocksErrorInvalidBlockCount {
        message
        numNeeded
        numProvided
      }
    }
  }
"""
"""Deletes seat assignments by id, returning the now-deleted assignments on success."""


def delete_assignments_variables(assignment_ids: Sequence[str]) -> dict[str, Any]:
    """Builds the GraphQL variables for :data:`DELETE_ASSIGNMENTS_MUTATION`."""
    return {"assignmentIds": list(assignment_ids)}


# ─── Raw response shapes ──────────────────────────────────────────────────────


class RawSeatmapDisplay(TypedDict, total=False):
    """Raw display geometry on the wire. Only ``x``/``y`` are always selected;
    which of the remaining fields the API returns depends on whether the display
    hangs off a section, a group, or a block."""

    x: float
    y: float
    width: float | None
    height: float | None
    tableWidth: float | None
    tableHeight: float | None
    table: bool | None
    label: str | None
    type: str | None


class RawIdName(TypedDict, total=False):
    """A bare ``{ id name }`` node (zone resource options, snapshots)."""

    id: str
    name: str


class RawIdOnly(TypedDict, total=False):
    """A bare ``{ id }`` node (a block's zone)."""

    id: str


class RawSeatmapBlock(TypedDict, total=False):
    """A single seat (block) node as returned by :data:`SEATMAPS_QUERY`."""

    id: str
    name: str
    fullBlockName: str
    order: int
    zone: RawIdOnly | None
    display: RawSeatmapDisplay


class RawSeatmapGroup(TypedDict, total=False):
    """A single group (table) node as returned by :data:`SEATMAPS_QUERY`."""

    id: str
    name: str
    assignableTo: list[str] | None
    blocks: list[RawSeatmapBlock] | None
    display: RawSeatmapDisplay


class RawSeatmapSection(TypedDict, total=False):
    """A single section node as returned by :data:`SEATMAPS_QUERY`."""

    id: str
    display: RawSeatmapDisplay
    groups: list[RawSeatmapGroup] | None


class RawSeatmapZone(TypedDict, total=False):
    """A single zone node as returned by :data:`SEATMAPS_QUERY`."""

    id: str
    name: str
    colorHex: str | None
    resourceOptions: list[RawIdName] | None


class RawSeatmapNode(TypedDict, total=False):
    """A single seating-map node as returned by :data:`SEATMAPS_QUERY`."""

    id: str
    name: str
    zones: list[RawSeatmapZone] | None
    sections: list[RawSeatmapSection] | None


class RawSeatmapSummaryNode(TypedDict, total=False):
    """A single seating-map node as returned by :data:`SEATMAP_IDS_QUERY` — id + name only."""

    id: str
    name: str


class RawSeatmapPrimaryGuest(TypedDict, total=False):
    """A booking's primary guest, as selected under a ``Ticket`` parent (PII-gated)."""

    firstName: str | None
    lastName: str | None


class RawSeatmapBooking(TypedDict, total=False):
    """A booking node, as selected under a ``Ticket`` parent."""

    id: str | None
    displayId: str | None
    activityId: str | None
    activitySnapshot: RawIdName | None
    startsAt: str | None
    endsAt: str | None
    primaryGuest: RawSeatmapPrimaryGuest | None


# Functional syntax: ``__typename`` would be name-mangled in a class body.
RawSeatmapAssignmentParent = TypedDict(
    "RawSeatmapAssignmentParent",
    {
        "__typename": str | None,
        "id": str | None,
        # ``Ticket`` only.
        "resourceOptionSnapshot": RawIdName | None,
        "booking": RawSeatmapBooking | None,
        # ``AccountUser`` only.
        "name": str | None,
    },
    total=False,
)
"""A single assignment's ``parent``, a union discriminated by ``__typename``."""


class RawSeatmapAssignment(TypedDict, total=False):
    """A single seat assignment node."""

    id: str | None
    parent: RawSeatmapAssignmentParent | None


class RawSeatmapAvailability(TypedDict, total=False):
    """A seat's availability for the queried range."""

    status: str | None
    assignments: list[RawSeatmapAssignment] | None


class RawAssignedSeatmapBlock(RawSeatmapBlock, total=False):
    """A block node under the assignments query — a :class:`RawSeatmapBlock` plus availability."""

    availability: RawSeatmapAvailability | None


class RawAssignedSeatmapGroup(TypedDict, total=False):
    """A group node under the assignments query."""

    id: str
    name: str
    assignableTo: list[str] | None
    blocks: list[RawAssignedSeatmapBlock] | None
    display: RawSeatmapDisplay


class RawAssignedSeatmapSection(TypedDict, total=False):
    """A section node under the assignments query."""

    id: str
    display: RawSeatmapDisplay
    groups: list[RawAssignedSeatmapGroup] | None


class RawAssignedSeatmapNode(TypedDict, total=False):
    """A seating-map node under the assignments query."""

    id: str
    name: str
    zones: list[RawSeatmapZone] | None
    sections: list[RawAssignedSeatmapSection] | None


class RawBlockRef(TypedDict, total=False):
    """A ``{ id fullBlockName }`` block reference on an assignment."""

    id: str
    fullBlockName: str


class RawAssignableSeatingAssignment(TypedDict, total=False):
    """A ticket's current seat assignment, as selected by the assignable-bookings query."""

    id: str
    block: RawBlockRef | None


class RawAssignableTicket(TypedDict, total=False):
    """A bookable ticket node under the assignable-bookings query."""

    hashid: str
    resourceOptionSnapshot: RawIdName | None
    seatingAssignment: RawAssignableSeatingAssignment | None


class RawAssignableBooking(TypedDict, total=False):
    """A booking node under the assignable-bookings query."""

    id: str
    displayId: str
    startsAt: str | None
    endsAt: str | None
    operatorNotes: str | None
    primaryGuest: RawSeatmapPrimaryGuest | None
    tickets: list[RawAssignableTicket] | None


RawTicketParent = TypedDict(
    "RawTicketParent",
    {"__typename": str | None, "hashid": str | None},
    total=False,
)
"""The ``parent`` of a created/deleted assignment — carries the ticket ``hashid``."""


class RawAssignBlocksAssignment(TypedDict, total=False):
    """A created seating assignment within a successful ``assignBlocks`` result."""

    id: str
    parent: RawTicketParent | None


RawAssignBlocksResult = TypedDict(
    "RawAssignBlocksResult",
    {"__typename": str | None, "assignments": list[RawAssignBlocksAssignment] | None},
    total=False,
)
"""A single aliased ``assignBlocks`` result: ``__typename`` classifies it, and on
success ``assignments`` carries the created records (id + the ticket ``hashid``)."""


AssignBlocksData = dict[str, RawAssignBlocksResult | None]
"""The ``data`` payload of the bulk assign mutation — keyed by per-assignment alias."""


class RawDeletedAssignment(TypedDict, total=False):
    """A single now-deleted assignment node, as selected by the delete mutation."""

    id: str
    block: RawBlockRef | None
    parent: RawTicketParent | None


RawDeleteAssignmentsResult = TypedDict(
    "RawDeleteAssignmentsResult",
    {
        "__typename": str | None,
        "assignments": list[RawDeletedAssignment] | None,
        "message": str | None,
    },
    total=False,
)
"""The ``deleteAssignments`` union result; carries ``assignments`` on success,
``message`` on error."""
