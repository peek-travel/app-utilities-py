"""Membership operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_membership_service()``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final
from uuid import uuid4

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.memberships.membership_converter import (
    from_memberships_response,
)
from peek_app_utilities.internal.peek.memberships.membership_queries import (
    CREATE_MEMBERSHIP_ORDER_FROM_QUOTE_MUTATION,
    CREATE_QUOTE_V2_MUTATION,
    MEMBERSHIPS_QUERY,
    MembershipMember,
)
from peek_app_utilities.models.peek.membership import (
    Membership,
    MembershipPurchaseInput,
    PurchasedMembership,
)

QUOTE_STATUS_CONFIRMED: Final = "CONFIRMED"
DEFAULT_BALANCE_AMOUNT: Final = "0.00"
DEFAULT_BALANCE_CURRENCY: Final = "USD"
DEFAULT_BALANCE_FORMATTED: Final = "$0.00"
EMAIL_REGEX: Final = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
COUNTRY_REGEX: Final = re.compile(r"^[A-Z]{2}$", re.IGNORECASE)
PHONE_REGEX: Final = re.compile(r"^[0-9+\s()\-.]+$")

ERROR_VARIANT_ID_REQUIRED: Final = "membershipVariantId is required"
ERROR_EMAIL_REQUIRED: Final = "email is required"
ERROR_EMAIL_INVALID: Final = "email is invalid"
ERROR_COUNTRY_INVALID: Final = "country is invalid"
ERROR_PHONE_INVALID: Final = "phone is invalid"
ERROR_QUOTE_FAILED_PREFIX: Final = "Failed to create membership quote: "
ERROR_QUOTE_ID_MISSING: Final = "Membership quote created but missing quote id"
ERROR_ORDER_FAILED_PREFIX: Final = "Failed to create membership order: "
ERROR_ORDER_NO_SALES: Final = "Membership order created but no sales found"
_ERROR_SEPARATOR: Final = ", "


class MembershipService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_all(self) -> list[Membership]:
        """Returns all membership variants, flattened into :class:`Membership` records."""
        body = await self._client.request(SALES_ENDPOINT, MEMBERSHIPS_QUERY, {})
        return from_memberships_response(body.get("data"))

    async def purchase(self, input: MembershipPurchaseInput) -> PurchasedMembership:
        """Purchases a membership via the two-step quote → order flow.

        :raises ValueError: on invalid input (every problem joined into one
            message: blank ``membership_variant_id``, blank or malformed ``email``,
            a ``country`` that is not two letters, a ``phone`` with characters
            other than digits, ``+``, spaces, parentheses, ``-`` or ``.``), or
            when Peek returns errors on the quote or the order
        """
        _validate_purchase_input(input)

        quote_body = await self._client.request(
            SALES_ENDPOINT,
            CREATE_QUOTE_V2_MUTATION,
            {
                "input": {
                    "quoteInput": {
                        "membershipQuotes": [
                            {
                                "member": _build_member(input),
                                "membershipVariantId": input.membership_variant_id,
                                "refid": str(uuid4()),
                                "status": QUOTE_STATUS_CONFIRMED,
                            }
                        ]
                    }
                }
            },
        )
        quote_result: Mapping[str, Any] = (quote_body.get("data") or {}).get("createQuoteV2") or {}
        _raise_on_errors(quote_result.get("errors"), ERROR_QUOTE_FAILED_PREFIX)
        quote_id = (quote_result.get("quote") or {}).get("id")
        if not quote_id:
            raise ValueError(ERROR_QUOTE_ID_MISSING)

        order_body = await self._client.request(
            SALES_ENDPOINT,
            CREATE_MEMBERSHIP_ORDER_FROM_QUOTE_MUTATION,
            {"input": {"quoteId": quote_id}},
        )
        order_result: Mapping[str, Any] = (order_body.get("data") or {}).get(
            "createOrderFromQuote"
        ) or {}
        _raise_on_errors(order_result.get("errors"), ERROR_ORDER_FAILED_PREFIX)

        order = order_result.get("order")
        sales = (order or {}).get("sales") or []
        if not order or not sales:
            raise ValueError(ERROR_ORDER_NO_SALES)
        sale: Mapping[str, Any] = sales[0]
        primary_member = sale.get("primaryMember") or {}
        total = (sale.get("balance") or {}).get("total") or {}

        return PurchasedMembership(
            order_id=order.get("id") or "",
            membership_id=sale.get("id") or "",
            display_id=sale.get("displayId") or "",
            primary_member_id=primary_member.get("id"),
            primary_member_name=primary_member.get("name"),
            balance_amount=total.get("amount") or DEFAULT_BALANCE_AMOUNT,
            balance_currency=total.get("currency") or DEFAULT_BALANCE_CURRENCY,
            balance_formatted=total.get("formatted") or DEFAULT_BALANCE_FORMATTED,
        )


def _raise_on_errors(errors: Any, prefix: str) -> None:
    if errors:
        raise ValueError(f"{prefix}{errors[0].get('detail')}")


def _build_member(input: MembershipPurchaseInput) -> MembershipMember:
    """Builds the wire member, including only non-empty optional fields."""
    member: MembershipMember = {"email": input.email}
    if input.country and input.country.strip():
        member["country"] = input.country
    if input.formatted_address and input.formatted_address.strip():
        member["formattedAddress"] = input.formatted_address
    if input.membership_code and input.membership_code.strip():
        member["membershipCode"] = input.membership_code
    if input.name and input.name.strip():
        member["name"] = input.name
    if input.phone and input.phone.strip():
        member["phone"] = input.phone
    return member


def _validate_purchase_input(input: MembershipPurchaseInput) -> None:
    errors: list[str] = []

    if not input.membership_variant_id or not input.membership_variant_id.strip():
        errors.append(ERROR_VARIANT_ID_REQUIRED)
    if not input.email or not input.email.strip():
        errors.append(ERROR_EMAIL_REQUIRED)
    elif not EMAIL_REGEX.match(input.email):
        errors.append(ERROR_EMAIL_INVALID)
    if input.country and not COUNTRY_REGEX.match(input.country):
        errors.append(ERROR_COUNTRY_INVALID)
    if input.phone and not PHONE_REGEX.match(input.phone):
        errors.append(ERROR_PHONE_INVALID)

    if errors:
        raise ValueError(_ERROR_SEPARATOR.join(errors))
