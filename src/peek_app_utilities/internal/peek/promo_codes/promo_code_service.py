"""Promo-code operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_promo_code_service()``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Final

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.promo_codes.promo_code_queries import (
    CREATE_PROMO_CODE_MUTATION,
    PROMO_CODES_QUERY,
    from_promo_code_node,
)
from peek_app_utilities.models.peek.promo_code import (
    PROMO_DISCOUNT_TYPES,
    CreatedPromoCode,
    CreatePromoCodeInput,
    PromoCode,
)

DEFAULT_PAGE_SIZE: Final = 50
"""Default page size for cursor-paginated promo codes."""
DEFAULT_CURRENCY: Final = "USD"
"""Default currency for fixed-amount discounts."""
CURRENCY_PATTERN: Final = re.compile(r"^[A-Z]{3}$")
"""ISO currency codes are three uppercase letters."""
_FIXED_DISCOUNT_TYPE: Final = "fixed"

ERROR_NAME_REQUIRED: Final = "name is required"
ERROR_CODE_REQUIRED: Final = "code is required"
ERROR_AMOUNT_REQUIRED: Final = "amount is required"
ERROR_DISCOUNT_TYPE_REQUIRED: Final = "discountType is required"
ERROR_DISCOUNT_TYPE_INVALID: Final = "discountType must be either 'percent' or 'fixed'"
ERROR_AMOUNT_NUMBER: Final = "amount must be a valid number"
ERROR_CURRENCY_FORMAT: Final = "currency must be 3 uppercase letters"
ERROR_NO_DATA: Final = "createPromoCode returned no data"


@dataclass(frozen=True, slots=True, kw_only=True)
class PromoCodeServiceOptions:
    """Tuning options for a :class:`PromoCodeService`."""

    page_size: int | None = None
    """Page size for cursor pagination. Default: 50."""


class PromoCodeService:
    def __init__(
        self, client: GraphQLClient, options: PromoCodeServiceOptions | None = None
    ) -> None:
        self._client = client
        page_size = options.page_size if options is not None else None
        self._page_size = DEFAULT_PAGE_SIZE if page_size is None else page_size

    async def get_all(self) -> list[PromoCode]:
        """Returns all promo codes, walking the cursor pagination to the end."""
        all_codes: list[PromoCode] = []
        after: str | None = None

        while True:
            body = await self._client.request(
                SALES_ENDPOINT, PROMO_CODES_QUERY, {"first": self._page_size, "after": after}
            )
            data = body.get("data") or {}
            connection = data.get("promoCodes") or {}
            for edge in connection.get("edges") or []:
                all_codes.append(from_promo_code_node(edge.get("node") or {}))

            page_info = connection.get("pageInfo") or {}
            end_cursor = page_info.get("endCursor")
            if page_info.get("hasNextPage") and end_cursor:
                after = end_cursor
            else:
                break

        return all_codes

    async def create(self, input: CreatePromoCodeInput) -> CreatedPromoCode:
        """Creates a promo code.

        :raises ValueError: on invalid input (blank ``name``/``code``/``amount``/
            ``discount_type``, an unknown discount type, a non-numeric amount, or
            a currency that is not 3 uppercase letters), when Peek returns an
            ``InvalidDataError`` (carrying Peek's message), or when the mutation
            returns no data
        """
        if not input.name:
            raise ValueError(ERROR_NAME_REQUIRED)
        if not input.code:
            raise ValueError(ERROR_CODE_REQUIRED)
        if not input.amount:
            raise ValueError(ERROR_AMOUNT_REQUIRED)
        if not input.discount_type:
            raise ValueError(ERROR_DISCOUNT_TYPE_REQUIRED)
        if input.discount_type not in PROMO_DISCOUNT_TYPES:
            raise ValueError(ERROR_DISCOUNT_TYPE_INVALID)
        if not _is_number(input.amount):
            raise ValueError(ERROR_AMOUNT_NUMBER)
        currency = input.currency or DEFAULT_CURRENCY
        if not CURRENCY_PATTERN.match(currency):
            raise ValueError(ERROR_CURRENCY_FORMAT)

        raw_input: dict[str, Any] = {"code": input.code, "name": input.name}
        if input.max_redemptions:
            raw_input["maxRedeemCount"] = int(input.max_redemptions)
        if input.discount_type == _FIXED_DISCOUNT_TYPE:
            raw_input["fixedAmount"] = {"amount": input.amount, "currency": currency}
        else:
            raw_input["percentAmount"] = input.amount

        body = await self._client.request(
            SALES_ENDPOINT, CREATE_PROMO_CODE_MUTATION, {"input": raw_input}
        )
        data = body.get("data") or {}
        result = data.get("createPromoCode")
        if result and "message" in result:
            raise ValueError(str(result["message"]))
        if not result:
            raise ValueError(ERROR_NO_DATA)
        return CreatedPromoCode(id=result.get("id") or "", name=result.get("name") or "")


def _is_number(value: str) -> bool:
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False
