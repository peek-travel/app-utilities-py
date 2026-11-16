"""Seating-map operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_seatmap_service()`` rather than
constructing it directly — the access service wires in the authenticated,
shared transport and the resolved access options. This class is where
seating-map business logic lives.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.errors import SeatmapDeleteError
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.seatmaps.seatmap_converter import (
    from_assignable_bookings,
    from_assigned_seatmap_nodes,
    from_deleted_assignments,
    from_seatmap_nodes,
    from_seatmap_summary_nodes,
    to_assignment_response,
)
from peek_app_utilities.internal.peek.seatmaps.seatmap_queries import (
    DELETE_ASSIGNMENTS_MUTATION,
    DELETE_ASSIGNMENTS_SUCCESS_TYPENAME,
    SEATMAP_IDS_QUERY,
    SEATMAPS_QUERY,
    assign_blocks_variables,
    build_assign_blocks_mutation,
    build_assignable_bookings_query,
    build_seatmap_assignments_query,
    delete_assignments_variables,
)
from peek_app_utilities.models.peek.seatmap import (
    AssignableBooking,
    AssignedSeatmap,
    AssignmentResponse,
    DeletedSeatAssignment,
    Seatmap,
    SeatmapBlockAssignment,
    SeatmapSummary,
)

ERROR_PRODUCT_ID_REQUIRED: Final = "A non-empty product id is required."
"""Raised-error message when a product id is missing or blank."""

ASSIGNABLE_ID_PREFIX: Final = "t_"
"""Required id prefix for a bookable ticket handle (``assignable_id``)."""
BLOCK_ID_PREFIX: Final = "csb_"
"""Required id prefix for a seat (block) id."""
ASSIGNMENT_ID_PREFIX: Final = "asa_"
"""Required id prefix for a seating-assignment record id."""

ERROR_NO_ASSIGNMENTS: Final = "At least one assignment is required."
ERROR_ASSIGNABLE_ID_PREFIX: Final = f'Each assignableId must start with "{ASSIGNABLE_ID_PREFIX}".'
ERROR_BLOCK_ID_PREFIX: Final = f'Each blockId must start with "{BLOCK_ID_PREFIX}".'
ERROR_NO_ASSIGNMENT_IDS: Final = "At least one assignment id is required."
ERROR_ASSIGNMENT_ID_PREFIX: Final = f'Each assignment id must start with "{ASSIGNMENT_ID_PREFIX}".'
ERROR_RANGE_SAME_DATE: Final = "rangeStart and rangeEnd must fall on the same date."

RANGE_START_LABEL: Final = "rangeStart"
RANGE_END_LABEL: Final = "rangeEnd"

_DATE_PREFIX_LENGTH: Final = 10
"""Length of the ``YYYY-MM-DD`` date prefix of a naive datetime."""

_DEFAULT_SECONDS: Final = "00"
_MAX_MONTH: Final = 12
_MAX_DAY: Final = 31
_MAX_HOUR: Final = 23
_MAX_MINUTE: Final = 59
_MAX_SECOND: Final = 59

_NAIVE_DATETIME_RE: Final = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)
"""Matches a naive datetime, tolerating an optional seconds component, optional
fractional seconds, and an optional trailing timezone (``Z`` or ``±HH[:]MM``) —
all of which :func:`_normalize_naive_datetime` strips. Captures date, hour,
minute, and (optional) second."""


def _normalize_naive_datetime(value: str, label: str) -> str:
    """Normalizes a caller-supplied datetime to the API's naive
    ``YYYY-MM-DDTHH:MM:SS`` form: adds ``:00`` seconds when omitted and strips
    any fractional seconds and timezone. Raises ``ValueError`` when the input is
    blank, unparseable, or carries an out-of-range component."""
    trimmed = (value or "").strip()
    if not trimmed:
        raise ValueError(f"{label} is required.")
    match = _NAIVE_DATETIME_RE.match(trimmed)
    if match is None:
        raise ValueError(f'{label} must be a datetime like "YYYY-MM-DDTHH:MM:SS" (got "{value}").')
    year, month, day, hour, minute, second = match.groups()
    sec = second if second is not None else _DEFAULT_SECONDS
    if (
        not 1 <= int(month) <= _MAX_MONTH
        or not 1 <= int(day) <= _MAX_DAY
        or int(hour) > _MAX_HOUR
        or int(minute) > _MAX_MINUTE
        or int(sec) > _MAX_SECOND
    ):
        raise ValueError(f'{label} has an out-of-range component (got "{value}").')
    return f"{year}-{month}-{day}T{hour}:{minute}:{sec}"


def _build_naive_range(range_start: str, range_end: str) -> str:
    """Normalizes both range bounds (see :func:`_normalize_naive_datetime`),
    enforces that they fall on the same date, and returns the API's half-open
    ``[start,end)`` range literal. Shared by every range-scoped read so they
    apply identical parsing and validation."""
    start = _normalize_naive_datetime(range_start, RANGE_START_LABEL)
    end = _normalize_naive_datetime(range_end, RANGE_END_LABEL)
    if start[:_DATE_PREFIX_LENGTH] != end[:_DATE_PREFIX_LENGTH]:
        raise ValueError(ERROR_RANGE_SAME_DATE)
    return f"[{start},{end})"


def _require_product_id(product_id: str) -> None:
    if not (product_id or "").strip():
        raise ValueError(ERROR_PRODUCT_ID_REQUIRED)


def _require_prefix(value: str, prefix: str, message: str) -> None:
    """Raises ``ValueError`` (``"<message> Got "<value>"."``) unless ``value`` starts with ``prefix``."""
    if not (value or "").startswith(prefix):
        raise ValueError(f'{message} Got "{value}".')


def _seating_maps(body: dict[str, Any]) -> list[Any]:
    """The ``data.activity.seatingMaps`` list of a response body, or ``[]``."""
    data = body.get("data") or {}
    activity = data.get("activity") or {}
    maps: list[Any] = activity.get("seatingMaps") or []
    return maps


class SeatmapService:
    """Reads the seating maps configured on a product, seat assignments over a
    datetime range, and the bookings assignable to seats; assigns tickets to
    seats and deletes assignments.

    Obtain an instance via ``PeekAccessService.get_seatmap_service()``.
    """

    def __init__(self, client: GraphQLClient, access_options: ResolvedAccessOptions) -> None:
        self._client = client
        # Whether the booking's primary-guest name (PII) is requested.
        self._full_customer_access = access_options.full_customer_access

    async def get_seatmap_for_product(self, product_id: str) -> list[Seatmap]:
        """Returns every :class:`Seatmap` configured on a single activity
        (product), in the order Peek reports them. A product can have zero, one,
        or many maps.

        Seating maps are structural layout definitions — zones, sections,
        tables, and seats — not customer data, so the result is unaffected by
        ``full_customer_access``.

        :param product_id: The activity's id.
        :returns: The product's seating maps, or an empty list when the product
            has none or is not found.
        :raises ValueError: when ``product_id`` is missing or blank.
        :raises UnknownSeatmapDisplayTypeError: when the API returns a section
            ``display.type`` the package does not recognize.

        Example::

            maps = await peek.get_seatmap_service().get_seatmap_for_product("act-1")
        """
        _require_product_id(product_id)
        body = await self._client.request(SALES_ENDPOINT, SEATMAPS_QUERY, {"id": product_id})
        return from_seatmap_nodes(_seating_maps(body))

    async def get_seatmap_ids_for_product(self, product_id: str) -> list[SeatmapSummary]:
        """Returns the id and name of every seating map configured on a product
        — a lightweight alternative to :meth:`get_seatmap_for_product` for
        callers that only need to list the maps assigned to a product, not their
        zone/section/seat layout. The query is trimmed to match (id + name only).

        Like :meth:`get_seatmap_for_product`, seating maps are structural layout,
        not customer data, so the result is unaffected by ``full_customer_access``.

        :param product_id: The activity's id.
        :returns: The product's seating maps as :class:`SeatmapSummary` id/name
            pairs, or an empty list when the product has none or is not found.
        :raises ValueError: when ``product_id`` is missing or blank.

        Example::

            maps = await peek.get_seatmap_service().get_seatmap_ids_for_product("act-1")
            # → [SeatmapSummary(id="csm_8j734", name="Main Floor"), …]
        """
        _require_product_id(product_id)
        body = await self._client.request(SALES_ENDPOINT, SEATMAP_IDS_QUERY, {"id": product_id})
        return from_seatmap_summary_nodes(_seating_maps(body))

    async def get_seat_map_assignments(
        self, product_id: str, range_start: str, range_end: str
    ) -> list[AssignedSeatmap]:
        """Returns every seating map configured on a product, each with its seats
        enriched by occupancy over a datetime range: :class:`AssignedSeatmap` s
        carrying the same structural data as :meth:`get_seatmap_for_product`
        plus each seat's ``status`` and ``assigned_to`` occupants.

        ``range_start``/``range_end`` are flexible: they may omit seconds
        (``...T14:00``) and may carry a timezone or fractional seconds — all
        normalized to the API's naive ``YYYY-MM-DDTHH:MM:SS`` form (seconds
        added, timezone and fractional seconds stripped). The range is queried
        half-open — inclusive ``range_start``, exclusive ``range_end`` — and
        both bounds must fall on the **same date**.

        A guest's name is **customer PII**: when this access service was created
        without ``full_customer_access``, a GUEST occupant's ``guest_name`` is
        always ``None`` (the field is never requested). Staff (ACCOUNT_USER)
        names are not gated.

        :param product_id: The activity's id.
        :param range_start: Inclusive start of the range (naive datetime).
        :param range_end: Exclusive end of the range (naive datetime).
        :returns: The product's seating maps with occupancy, or an empty list
            when the product has none or is not found.
        :raises ValueError: when ``product_id`` is blank, a range bound is
            blank, unparseable, or out of range, or the two bounds fall on
            different dates.
        :raises UnknownSeatmapDisplayTypeError: on an unrecognized section ``display.type``.
        :raises UnknownSeatmapBlockStatusError: on an unrecognized seat status.
        :raises UnknownSeatmapAssignmentParentError: on an unrecognized
            assignment parent ``__typename``.

        Example::

            maps = await peek.get_seatmap_service().get_seat_map_assignments(
                "act-1", "2026-11-06T14:00", "2026-11-06T16:00"
            )
        """
        _require_product_id(product_id)
        range_literal = _build_naive_range(range_start, range_end)
        body = await self._client.request(
            SALES_ENDPOINT,
            build_seatmap_assignments_query(self._full_customer_access),
            {"id": product_id, "range": range_literal},
        )
        return from_assigned_seatmap_nodes(_seating_maps(body))

    async def assignable_bookings(
        self, product_id: str, range_start: str, range_end: str
    ) -> list[AssignableBooking]:
        """Returns the confirmed bookings on a product that overlap a datetime
        range, each with the tickets that can be assigned to seats (and the seat
        a ticket currently holds, when it has one). Use it to drive seat
        assignment: pick an :class:`AssignableBooking`'s ticket by its
        ``assignable_id``.

        ``range_start``/``range_end`` are parsed and validated exactly like
        :meth:`get_seat_map_assignments` (seconds optional, timezone and
        fractional seconds stripped, components range-checked, both bounds on
        the same date) and sent half-open — inclusive ``range_start``,
        exclusive ``range_end``.

        A guest's name is **customer PII**: when this access service was created
        without ``full_customer_access``, ``guest_name`` is always ``None``
        (never requested).

        :param product_id: The activity's id.
        :param range_start: Inclusive start of the range (naive datetime).
        :param range_end: Exclusive end of the range (naive datetime).
        :returns: The overlapping confirmed bookings, or an empty list when none match.
        :raises ValueError: when ``product_id`` is blank, a range bound is
            blank, unparseable, or out of range, or the two bounds fall on
            different dates.

        Example::

            bookings = await peek.get_seatmap_service().assignable_bookings(
                "act-1", "2026-11-06T14:00", "2026-11-06T15:00"
            )
        """
        _require_product_id(product_id)
        range_literal = _build_naive_range(range_start, range_end)
        body = await self._client.request(
            SALES_ENDPOINT,
            build_assignable_bookings_query(self._full_customer_access),
            {"id": product_id, "range": range_literal},
        )
        return from_assignable_bookings((body.get("data") or {}).get("bookings") or [])

    async def assign_tickets_to_seats(
        self, assignments: Sequence[SeatmapBlockAssignment]
    ) -> AssignmentResponse:
        """Assigns bookable tickets to seats in bulk — one ``assignBlocks`` call
        per :class:`SeatmapBlockAssignment`, batched into a single mutation.

        The result summarizes per-assignment outcomes: ``status`` is
        ``"SUCCESS"`` when every assignment succeeded, ``"FAILED"`` when every
        one failed, and ``"PARTIAL"`` when some of each, with
        ``successful_assignments`` / ``failed_assignments`` listing the
        ``assignable_id`` s. Per-assignment failures (overbooking, invalid type,
        …) are reported here, **not** raised; only transport/GraphQL-level
        errors raise (as ``PeekGraphQLError`` / ``PeekHttpError`` / etc.).

        :param assignments: The ticket→seat bindings to request (at least one).
        :returns: The bulk outcome.
        :raises ValueError: when ``assignments`` is empty, or any
            ``assignable_id`` does not start with ``"t_"`` or any ``block_id``
            does not start with ``"csb_"`` — all checked before any network call.

        Example::

            result = await peek.get_seatmap_service().assign_tickets_to_seats([
                SeatmapBlockAssignment(assignable_id="t_A1", block_id="csb_A1"),
                SeatmapBlockAssignment(assignable_id="t_A2", block_id="csb_A2"),
            ])
        """
        if not assignments:
            raise ValueError(ERROR_NO_ASSIGNMENTS)
        for assignment in assignments:
            _require_prefix(
                assignment.assignable_id, ASSIGNABLE_ID_PREFIX, ERROR_ASSIGNABLE_ID_PREFIX
            )
            _require_prefix(assignment.block_id, BLOCK_ID_PREFIX, ERROR_BLOCK_ID_PREFIX)

        body = await self._client.request(
            SALES_ENDPOINT,
            build_assign_blocks_mutation(len(assignments)),
            assign_blocks_variables(assignments),
        )
        return to_assignment_response(body.get("data") or {}, assignments)

    async def delete_seat_assignments(
        self, assignment_ids: Sequence[str]
    ) -> list[DeletedSeatAssignment]:
        """Deletes seat assignments by id, returning the now-deleted assignments
        so a caller can reload state without a refetch.

        :param assignment_ids: The seating-assignment record ids to delete (each
            must start with ``"asa_"``); at least one.
        :returns: The deleted assignments (seat id/name and freed ticket handle).
        :raises ValueError: when ``assignment_ids`` is empty or any id does not
            start with ``"asa_"`` — checked before any network call.
        :raises SeatmapDeleteError: when the API reports a batch-level failure
            (a non-success union member); transport/GraphQL errors raise as usual.

        Example::

            deleted = await peek.get_seatmap_service().delete_seat_assignments(
                ["asa_9kQ2mNv", "asa_7hL4pXw"]
            )
        """
        if not assignment_ids:
            raise ValueError(ERROR_NO_ASSIGNMENT_IDS)
        for assignment_id in assignment_ids:
            _require_prefix(assignment_id, ASSIGNMENT_ID_PREFIX, ERROR_ASSIGNMENT_ID_PREFIX)

        body = await self._client.request(
            SALES_ENDPOINT,
            DELETE_ASSIGNMENTS_MUTATION,
            delete_assignments_variables(assignment_ids),
        )
        result = (body.get("data") or {}).get("deleteAssignments") or {}
        if result.get("__typename") != DELETE_ASSIGNMENTS_SUCCESS_TYPENAME:
            raise SeatmapDeleteError(result.get("message"))
        return from_deleted_assignments(result.get("assignments") or [])
