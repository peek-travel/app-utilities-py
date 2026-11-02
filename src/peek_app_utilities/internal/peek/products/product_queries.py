"""Raw Peek GraphQL queries and response shapes for products. These are an
internal implementation detail of the package and are deliberately not
re-exported from the public entry point.
"""

from __future__ import annotations

from typing import Final, TypedDict

from peek_app_utilities.internal.peek.money import RawMoney

PRODUCTS_QUERY: Final = """
  query Sales {
    activities {
      name
      legacyId
      id
      deletedAt
      type
      colorHex
      currency
      imageUrl
      description
      meetingLocationFormattedAddress
      meetingLocationUrl
      infoMeetingLocation
      resourceOptions {
        id
        name
        priceRange {
          min {
            currency
            amount
            formatted
          }
          max {
            currency
            amount
            formatted
          }
        }
      }
    }
  }
"""
"""Fetches all activities (primary bookable products)."""

RawMoneyNode = RawMoney
"""A raw monetary value on the wire (a ``PricingMoney`` before conversion)."""


class PriceRangeNode(TypedDict, total=False):
    """A resource option's ``priceRange`` block."""

    min: RawMoneyNode | None
    max: RawMoneyNode | None


class ResourceOptionNode(TypedDict, total=False):
    """A single ``resourceOptions`` entry on an activity."""

    id: str
    name: str
    priceRange: PriceRangeNode | None


class ActivityNode(TypedDict, total=False):
    """A single activity node as returned by :data:`PRODUCTS_QUERY`."""

    name: str
    legacyId: str | None
    id: str
    deletedAt: str | None
    type: str
    colorHex: str | None
    currency: str | None
    imageUrl: str | None
    description: str | None
    meetingLocationFormattedAddress: str | None
    meetingLocationUrl: str | None
    infoMeetingLocation: str | None
    resourceOptions: list[ResourceOptionNode] | None


class ProductsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`PRODUCTS_QUERY`."""

    activities: list[ActivityNode] | None


ITEM_OPTIONS_QUERY: Final = """
  query GetItemOptions($first: Int, $after: String) {
    itemOptions(first: $first, after: $after) {
      edges {
        cursor
        node {
          id
          name
          description
          item {
            id
            name
          }
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
"""
"""Fetches a single cursor-paginated page of item options (add-ons)."""


class ItemNode(TypedDict, total=False):
    """The parent item an item option belongs to."""

    id: str
    name: str


class ItemOptionNode(TypedDict, total=False):
    """A single item option node as returned by :data:`ITEM_OPTIONS_QUERY`."""

    id: str
    name: str
    description: str | None
    item: ItemNode | None


class ItemOptionEdge(TypedDict, total=False):
    cursor: str
    node: ItemOptionNode


class PageInfoNode(TypedDict, total=False):
    hasNextPage: bool
    endCursor: str | None


class ItemOptionsConnection(TypedDict, total=False):
    edges: list[ItemOptionEdge] | None
    pageInfo: PageInfoNode | None


class ItemOptionsData(TypedDict, total=False):
    """The ``data`` payload of :data:`ITEM_OPTIONS_QUERY`."""

    itemOptions: ItemOptionsConnection | None
