"""Raw Peek GraphQL queries, mutations, and response shapes for memberships.
Internal.
"""

from __future__ import annotations

from typing import Final, TypedDict

MEMBERSHIPS_QUERY: Final = """
  query Sales {
    memberships {
      name
      id
      membershipVariants {
        id
        description
        imageUrl
        externalName
        internalName
      }
    }
  }
"""
"""Fetches all memberships with their variants."""

CREATE_QUOTE_V2_MUTATION: Final = """
  mutation CreateQuoteV2($input: CreateQuoteV2Input!) {
    createQuoteV2(input: $input) {
      errors { detail value code }
      quote { id }
    }
  }
"""
"""Creates a quote (used here to start a membership purchase)."""

CREATE_MEMBERSHIP_ORDER_FROM_QUOTE_MUTATION: Final = """
  mutation CreateOrderFromQuote($input: CreateOrderFromQuoteInput!) {
    createOrderFromQuote(input: $input) {
      errors { code detail value }
      order {
        id
        sales {
          id
          displayId
          ... on SoldMembership {
            id
            displayId
            primaryMember { name id }
            balance { total { amount currency formatted } }
          }
        }
      }
    }
  }
"""
"""Creates a membership order from a quote."""


class MembershipVariantNode(TypedDict, total=False):
    """A single membership variant node."""

    id: str
    description: str | None
    imageUrl: str | None
    externalName: str
    internalName: str


class MembershipNode(TypedDict, total=False):
    """A single membership node as returned by :data:`MEMBERSHIPS_QUERY`."""

    name: str
    id: str
    membershipVariants: list[MembershipVariantNode] | None


class MembershipsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`MEMBERSHIPS_QUERY`."""

    memberships: list[MembershipNode] | None


class MembershipMember(TypedDict, total=False):
    """Member details attached to a membership quote (wire shape)."""

    email: str
    country: str
    formattedAddress: str
    membershipCode: str
    name: str
    phone: str


class MutationError(TypedDict, total=False):
    code: str
    detail: str
    value: str | None


class QuoteRef(TypedDict, total=False):
    id: str


class CreateQuoteV2Result(TypedDict, total=False):
    errors: list[MutationError] | None
    quote: QuoteRef | None


class CreateQuoteV2Response(TypedDict, total=False):
    """``data`` payload of :data:`CREATE_QUOTE_V2_MUTATION`."""

    createQuoteV2: CreateQuoteV2Result


class PrimaryMemberNode(TypedDict, total=False):
    id: str
    name: str


class MoneyNode(TypedDict, total=False):
    amount: str
    currency: str
    formatted: str


class BalanceNode(TypedDict, total=False):
    total: MoneyNode | None


class SoldMembershipSale(TypedDict, total=False):
    """A sold membership returned by the order mutation."""

    id: str
    displayId: str
    primaryMember: PrimaryMemberNode | None
    balance: BalanceNode | None


class MembershipOrderNode(TypedDict, total=False):
    id: str
    sales: list[SoldMembershipSale] | None


class CreateMembershipOrderResult(TypedDict, total=False):
    errors: list[MutationError] | None
    order: MembershipOrderNode | None


class CreateMembershipOrderResponse(TypedDict, total=False):
    """``data`` payload of :data:`CREATE_MEMBERSHIP_ORDER_FROM_QUOTE_MUTATION`."""

    createOrderFromQuote: CreateMembershipOrderResult
