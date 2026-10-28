"""Pricing-engine and pricing-override operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_pricing_service()`` rather than
constructing it directly.

Scope: this service is a thin, faithful wrapper over the Peek pricing
primitives. It creates/updates/deletes engines and upserts/clears overrides,
validating inputs and mapping the typed-error unions to raised ``ValueError``s.
It does **not** own the domain logic that decides what the overrides should be —
segmenting activities across time windows, ordering override tiers, or computing
``spots_taken`` bounds. Callers build the :class:`UpsertOverridesInput` (see the
model docs) and this service sends it as-is.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any, Final

from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.pricing.pricing_converter import from_activity_contexts
from peek_app_utilities.internal.peek.pricing.pricing_queries import (
    CREATE_ENGINE_SUCCESS_TYPENAME,
    CREATE_PRICING_ENGINE_MUTATION,
    DELETE_PRICING_ENGINE_MUTATION,
    TYPENAME_KEY,
    UPDATE_ENGINE_SUCCESS_TYPENAME,
    UPDATE_PRICING_ENGINE_MUTATION,
    UPSERT_OVERRIDES_SUCCESS_TYPENAME,
    UPSERT_PRICING_OVERRIDES_MUTATION,
    build_clear_input,
    build_create_engine_input,
    build_update_engine_input,
    build_upsert_input,
)
from peek_app_utilities.models.peek.pricing import (
    ClearOverridesInput,
    CreatedPricingEngine,
    CreateEngineInput,
    FixedResourceOptionOverride,
    PricingEngine,
    ResourceOptionOverride,
    UpdateEngineInput,
    UpsertOverridesInput,
    UpsertOverridesResult,
)

CURRENCY_PATTERN: Final = re.compile(r"^[A-Z]{3}$")
"""ISO 4217 currency codes are three uppercase letters."""
PERCENTAGE_FLOOR: Final = -100
"""A percentage adjustment must be strictly greater than this floor."""

ERROR_NAME_REQUIRED: Final = "name is required"
ERROR_ENGINE_ID_REQUIRED: Final = "engineId is required"
ERROR_DATE_RANGE_REQUIRED: Final = "dateRange is required"
ERROR_ACTIVITIES_REQUIRED: Final = "activities is required"
ERROR_ACTIVITY_ID_REQUIRED: Final = "activityId is required"
ERROR_TICKET_ID_REQUIRED: Final = "resource-option id is required"
ERROR_CURRENCY_FORMAT: Final = "currency must be 3 uppercase letters"
ERROR_AMOUNT_NUMBER: Final = "price amount must be a valid number"
ERROR_PERCENTAGE_NUMBER: Final = "percentageAdjustment must be a valid number"
ERROR_PERCENTAGE_FLOOR: Final = "percentageAdjustment must be greater than -100"
ERROR_NO_DATA: Final = "pricing mutation returned no data"

_CREATE_ENGINE_FIELD: Final = "createPricingEngine"
_UPDATE_ENGINE_FIELD: Final = "updatePricingEngine"
_UPSERT_OVERRIDES_FIELD: Final = "upsertPricingOverridesActivityContexts"


class PricingService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def create_engine(self, input: CreateEngineInput) -> CreatedPricingEngine:
        """Creates a pricing engine. Store the returned id and reuse it on every
        subsequent override upsert.

        :raises ValueError: on a blank ``name``, when Peek returns an
            ``InvalidDataError`` (carrying Peek's message), or when the mutation
            returns no data
        """
        if not input.name:
            raise ValueError(ERROR_NAME_REQUIRED)

        body = await self._client.request(
            SALES_ENDPOINT,
            CREATE_PRICING_ENGINE_MUTATION,
            {"input": build_create_engine_input(input)},
        )
        result = _require_success(body, _CREATE_ENGINE_FIELD, CREATE_ENGINE_SUCCESS_TYPENAME)
        engine = result.get("engine") or {}
        return CreatedPricingEngine(id=engine.get("id") or "")

    async def update_engine(self, input: UpdateEngineInput) -> PricingEngine:
        """Updates a pricing engine's name and/or activity scope. An empty or
        omitted ``activity_ids`` clears the scope.

        :raises ValueError: on a blank ``engine_id`` or ``name``, when Peek
            returns an ``InvalidDataError`` or ``NotFoundError`` (carrying Peek's
            message), or when the mutation returns no data
        """
        if not input.engine_id:
            raise ValueError(ERROR_ENGINE_ID_REQUIRED)
        if not input.name:
            raise ValueError(ERROR_NAME_REQUIRED)

        body = await self._client.request(
            SALES_ENDPOINT,
            UPDATE_PRICING_ENGINE_MUTATION,
            {"input": build_update_engine_input(input)},
        )
        result = _require_success(body, _UPDATE_ENGINE_FIELD, UPDATE_ENGINE_SUCCESS_TYPENAME)
        engine = result.get("engine") or {}
        return PricingEngine(id=engine.get("id") or "", name=engine.get("name") or "")

    async def delete_engine(self, engine_id: str) -> None:
        """Deletes a pricing engine. Idempotent — resolves whether the engine
        existed or was already gone (Peek's ``NotFoundError`` is treated as
        success).

        :raises ValueError: on a blank ``engine_id``
        """
        if not engine_id:
            raise ValueError(ERROR_ENGINE_ID_REQUIRED)

        await self._client.request(
            SALES_ENDPOINT, DELETE_PRICING_ENGINE_MUTATION, {"id": engine_id}
        )

    async def upsert_overrides(self, input: UpsertOverridesInput) -> UpsertOverridesResult:
        """Upserts pricing overrides for the engine and date range in ``input`` —
        a **full replace** for each ``(date_range, activity)``. Returns the
        resolved contexts Peek stored.

        :raises ValueError: on invalid input (blank ``engine_id`` / ``date_range``
            / ``activity_id`` / ticket id, a currency that is not 3 uppercase
            letters, a non-numeric price amount, a non-numeric
            ``percentage_adjustment`` or one ``<= -100``), when Peek returns an
            ``InvalidDataError``, or when the mutation returns no data
        """
        _validate_upsert_input(input)
        return await self._send_upsert(build_upsert_input(input))

    async def clear_overrides(self, input: ClearOverridesInput) -> UpsertOverridesResult:
        """Clears all overrides for the given activities across a date range.
        This is an upsert with empty overrides — never clear by omitting an
        activity.

        :raises ValueError: on a blank ``engine_id`` / ``date_range`` /
            ``activity_id``, when Peek returns an ``InvalidDataError``, or when
            the mutation returns no data
        """
        if not input.engine_id:
            raise ValueError(ERROR_ENGINE_ID_REQUIRED)
        if not input.date_range:
            raise ValueError(ERROR_DATE_RANGE_REQUIRED)
        _require_list(input.activity_ids, ERROR_ACTIVITIES_REQUIRED)
        for activity_id in input.activity_ids:
            if not activity_id:
                raise ValueError(ERROR_ACTIVITY_ID_REQUIRED)
        return await self._send_upsert(build_clear_input(input))

    async def _send_upsert(self, raw_input: Mapping[str, Any]) -> UpsertOverridesResult:
        body = await self._client.request(
            SALES_ENDPOINT, UPSERT_PRICING_OVERRIDES_MUTATION, {"input": raw_input}
        )
        result = _require_success(body, _UPSERT_OVERRIDES_FIELD, UPSERT_OVERRIDES_SUCCESS_TYPENAME)
        return UpsertOverridesResult(
            activity_contexts=from_activity_contexts(result.get("activityContexts") or [])
        )


def _require_success(
    body: Mapping[str, Any], field: str, success_typename: str
) -> Mapping[str, Any]:
    """Unwraps ``data.<field>``: raises on a missing payload or a non-success
    union member (carrying Peek's ``message``), otherwise returns the node."""
    data = body.get("data") or {}
    result: Mapping[str, Any] | None = data.get(field)
    if not result:
        raise ValueError(ERROR_NO_DATA)
    if result.get(TYPENAME_KEY) != success_typename:
        raise ValueError(str(result.get("message") or ""))
    return result


def _require_list(value: object, message: str) -> None:
    if not isinstance(value, list | tuple):
        raise ValueError(message)


def _validate_upsert_input(input: UpsertOverridesInput) -> None:
    if not input.engine_id:
        raise ValueError(ERROR_ENGINE_ID_REQUIRED)
    if not input.date_range:
        raise ValueError(ERROR_DATE_RANGE_REQUIRED)
    _require_list(input.activities, ERROR_ACTIVITIES_REQUIRED)

    for activity in input.activities:
        if not activity.activity_id:
            raise ValueError(ERROR_ACTIVITY_ID_REQUIRED)
        for override in activity.overrides:
            for option in override.resource_options:
                _validate_resource_option(option)


def _validate_resource_option(option: ResourceOptionOverride) -> None:
    if not option.id:
        raise ValueError(ERROR_TICKET_ID_REQUIRED)

    if isinstance(option, FixedResourceOptionOverride):
        if not CURRENCY_PATTERN.match(option.price.currency):
            raise ValueError(ERROR_CURRENCY_FORMAT)
        if parse_decimal(option.price.amount) is None:
            raise ValueError(ERROR_AMOUNT_NUMBER)
        return

    percentage = parse_decimal(option.percentage_adjustment)
    if percentage is None:
        raise ValueError(ERROR_PERCENTAGE_NUMBER)
    if percentage <= PERCENTAGE_FLOOR:
        raise ValueError(ERROR_PERCENTAGE_FLOOR)


def parse_decimal(value: str) -> float | None:
    """Parses a decimal string the way the validation needs it: ``None`` when the
    string is not a finite number."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed
