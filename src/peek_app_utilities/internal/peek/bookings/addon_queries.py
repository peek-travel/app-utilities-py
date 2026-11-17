"""Raw Peek GraphQL query, variables, and response shapes for listing the
add-ons (items + item options) attached to a single booking. Internal.

The :data:`SALES_ADDONS_QUERY` runs the ``sales`` query filtered by a booking's
display id (``filter.searchString``) and returns every item on the booking
together with its item options, refids, and reservation statuses — the detail
needed both to surface add-ons and to build add/cancel mutations.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

RESERVATION_STATUS_CONFIRMED: Final = "CONFIRMED"
"""Reservation status for a live (confirmed) item or option."""
ADDON_OPTION_STATUS_CANCELED: Final = "CANCELED"
"""Reservation status marking an item or option as canceled."""

_SALES_ADDONS_PAGE_SIZE: Final = 100
"""Page size for the sales add-ons query (a single booking, so one page)."""
_ORDER_BY_DIRECTION_DESC: Final = "DESC"
_ORDER_BY_FIELD_STARTS_AT: Final = "STARTS_AT"

SALES_ADDONS_QUERY: Final = """
  query Sales($after: String, $first: Int, $filter: SalesFilter!, $orderBy: SalesOrdering) {
    sales(after: $after, first: $first, filter: $filter, orderBy: $orderBy) {
      pageInfo { endCursor hasNextPage }
      edges {
        node {
          order { id displayId }
          ... on Booking {
            displayId
            id
            refid
            reservationStatus
            items {
              id
              refid
              value { total { amount currency formatted } }
              reservationStatus
              options {
                refid
                reservationStatus
                price { amount currency formatted }
                itemOptionSnapshot { id name }
                itemSnapshot { id name }
              }
            }
          }
        }
      }
    }
  }
"""
"""Fetches the items and item options for a single booking matched by
``filter.searchString`` (the booking display id)."""


def build_sales_addons_variables(search_string: str) -> dict[str, Any]:
    """Builds the variables for the sales add-ons query from a booking display id."""
    return {
        "first": _SALES_ADDONS_PAGE_SIZE,
        "after": None,
        "orderBy": {"direction": _ORDER_BY_DIRECTION_DESC, "field": _ORDER_BY_FIELD_STARTS_AT},
        "filter": {"searchString": search_string},
    }


class AddonGqlPrice(TypedDict, total=False):
    """Raw money shape returned by the ``sales`` add-ons query."""

    amount: str
    currency: str
    formatted: str


class SalesAddonItemOptionNode(TypedDict, total=False):
    refid: str
    reservationStatus: str
    price: AddonGqlPrice | None
    itemOptionSnapshot: dict[str, Any] | None
    itemSnapshot: dict[str, Any] | None


class SalesAddonItemNode(TypedDict, total=False):
    id: str
    refid: str
    value: dict[str, Any] | None
    reservationStatus: str
    options: list[SalesAddonItemOptionNode] | None


class SalesAddonBookingNode(TypedDict, total=False):
    id: str
    displayId: str
    refid: str
    reservationStatus: str
    order: dict[str, Any] | None
    items: list[SalesAddonItemNode] | None
