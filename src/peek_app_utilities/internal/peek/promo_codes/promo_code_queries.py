"""Raw Peek GraphQL query/mutation and response shapes for promo codes.
Internal. The promo-code node matches the public :class:`PromoCode` model
one-to-one, so the only mapping is the camelCase → snake_case rename done by
:func:`from_promo_code_node`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.promo_code import PromoCode, PromoCodeFixedAmount

PROMO_CODES_QUERY: Final = """
  query Sales($first: Int, $after: String) {
    promoCodes(first: $first, after: $after) {
      edges {
        node {
          id
          name
          percentAmount
          perTicketDiscount
          redemptionCode
          fixedAmount {
            amount
            currency
            formatted
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
"""Fetches a cursor-paginated page of promo codes."""

CREATE_PROMO_CODE_MUTATION: Final = """
  mutation Sales($input: CreatePromoCodeInput!) {
    createPromoCode(input: $input) {
      ... on InvalidDataError {
        message
      }
      ... on PromoCode {
        id
        name
      }
    }
  }
"""
"""Creates a promo code. Returns the new code's id/name or an InvalidDataError."""


class FixedAmountNode(TypedDict, total=False):
    amount: float | int | None
    currency: str | None
    formatted: str | None


class PromoCodeNode(TypedDict, total=False):
    """A single promo-code node as returned by :data:`PROMO_CODES_QUERY`."""

    id: str
    name: str
    percentAmount: float | int | None
    perTicketDiscount: bool
    redemptionCode: str
    fixedAmount: FixedAmountNode | None


class PromoCodeEdge(TypedDict, total=False):
    node: PromoCodeNode


class PageInfo(TypedDict, total=False):
    hasNextPage: bool
    endCursor: str | None


class PromoCodesConnection(TypedDict, total=False):
    edges: list[PromoCodeEdge]
    pageInfo: PageInfo


class PromoCodesResponse(TypedDict, total=False):
    """``data`` payload of :data:`PROMO_CODES_QUERY`."""

    promoCodes: PromoCodesConnection


class CreatePromoCodeResult(TypedDict, total=False):
    """The union payload of :data:`CREATE_PROMO_CODE_MUTATION`: a ``PromoCode``
    carrying ``id``/``name``, or an ``InvalidDataError`` carrying ``message``."""

    id: str
    name: str
    message: str


class CreatePromoCodeResponse(TypedDict, total=False):
    """``data`` payload of :data:`CREATE_PROMO_CODE_MUTATION`."""

    createPromoCode: CreatePromoCodeResult


def from_promo_code_node(node: Mapping[str, Any]) -> PromoCode:
    """Renames a raw promo-code node (a :class:`PromoCodeNode`) into the clean
    :class:`PromoCode`."""
    percent = node.get("percentAmount")
    return PromoCode(
        id=node.get("id") or "",
        name=node.get("name") or "",
        percent_amount=None if percent is None else float(percent),
        per_ticket_discount=bool(node.get("perTicketDiscount")),
        redemption_code=node.get("redemptionCode") or "",
        fixed_amount=_from_fixed_amount(node.get("fixedAmount")),
    )


def _from_fixed_amount(node: Mapping[str, Any] | None) -> PromoCodeFixedAmount | None:
    if not node:
        return None
    return PromoCodeFixedAmount(
        amount=float(node.get("amount") or 0),
        currency=node.get("currency") or "",
        formatted=node.get("formatted") or "",
    )
