"""Raw Peek GraphQL mutations, response shapes, and clean→raw variable builders
for pricing engines and pricing overrides. Internal — never re-exported.

The public :class:`UpsertOverridesInput` mirrors the wire input almost exactly;
the only transform the builders apply is stripping the ``mode`` discriminant off
each resource-option override down to the bare ``price`` /
``percentageAdjustment`` key the API expects, and spelling the filters in their
camelCase wire form.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from peek_app_utilities.models.peek.pricing import (
    ClearOverridesInput,
    CreateEngineInput,
    FixedResourceOptionOverride,
    PricingOverrideFilter,
    ResourceOptionOverride,
    SpotsTakenFilter,
    UpdateEngineInput,
    UpsertOverridesInput,
)

# ─── Mutations ───────────────────────────────────────────────────────────────

CREATE_PRICING_ENGINE_MUTATION: Final = """
  mutation CreatePricingEngine($input: CreatePricingEngineInput!) {
    createPricingEngine(input: $input) {
      __typename
      ... on CreatePricingEngineSuccess {
        engine {
          id
        }
      }
      ... on InvalidDataError {
        message
      }
    }
  }
"""
"""Creates a pricing engine, optionally scoped to a set of activity ids."""

UPDATE_PRICING_ENGINE_MUTATION: Final = """
  mutation UpdatePricingEngine($input: UpdatePricingEngineInput!) {
    updatePricingEngine(input: $input) {
      __typename
      ... on UpdatePricingEngineSuccess {
        engine {
          id
          name
        }
      }
      ... on InvalidDataError {
        message
      }
      ... on NotFoundError {
        id
        message
      }
    }
  }
"""
"""Updates a pricing engine's name and/or activity-id scope."""

DELETE_PRICING_ENGINE_MUTATION: Final = """
  mutation DeletePricingEngine($id: ID!) {
    deletePricingEngine(id: $id) {
      __typename
      ... on DeletePricingEngineSuccess {
        engine {
          id
          name
        }
      }
      ... on NotFoundError {
        id
        message
      }
    }
  }
"""
"""Deletes a pricing engine. Idempotent — a NotFoundError is treated as success."""

UPSERT_PRICING_OVERRIDES_MUTATION: Final = """
  mutation UpsertPricingOverridesActivityContexts($input: UpsertPricingOverridesActivityContextsInput!) {
    upsertPricingOverridesActivityContexts(input: $input) {
      __typename
      ... on UpsertPricingOverridesActivityContextsSuccess {
        activityContexts {
          date
          activity {
            id
            name
          }
          engine {
            id
            name
          }
          overrides {
            order
            resourceOptions {
              resourceOption {
                id
                name
              }
              override {
                ... on PricingOverridesActivityContextResourceOptionPriceOverride {
                  price {
                    amount
                    currency
                    formatted
                  }
                }
                ... on PricingOverridesActivityContextResourceOptionPercentageAdjustmentOverride {
                  percentageAdjustment
                }
              }
            }
            filters {
              __typename
              ... on PricingOverridesActivityContextStartTimeRangeFilter {
                startTimeRange
              }
              ... on PricingOverridesActivityContextSpotsTakenFilter {
                minSpots
                maxSpots
              }
            }
          }
        }
      }
      ... on InvalidDataError {
        message
      }
    }
  }
"""
"""Upserts (or clears, via empty overrides) pricing overrides for a date range."""

# ─── Typenames (used to branch on the response unions) ───────────────────────

CREATE_ENGINE_SUCCESS_TYPENAME: Final = "CreatePricingEngineSuccess"
UPDATE_ENGINE_SUCCESS_TYPENAME: Final = "UpdatePricingEngineSuccess"
DELETE_ENGINE_SUCCESS_TYPENAME: Final = "DeletePricingEngineSuccess"
UPSERT_OVERRIDES_SUCCESS_TYPENAME: Final = "UpsertPricingOverridesActivityContextsSuccess"

START_TIME_RANGE_FILTER_TYPENAME: Final = "PricingOverridesActivityContextStartTimeRangeFilter"
"""``__typename`` of the start-time-range filter in a pricing-override response."""
SPOTS_TAKEN_FILTER_TYPENAME: Final = "PricingOverridesActivityContextSpotsTakenFilter"
"""``__typename`` of the spots-taken filter in a pricing-override response."""

# ─── Wire keys ───────────────────────────────────────────────────────────────

TYPENAME_KEY: Final = "__typename"
PRICE_KEY: Final = "price"
PERCENTAGE_ADJUSTMENT_KEY: Final = "percentageAdjustment"
SPOTS_TAKEN_KEY: Final = "spotsTaken"
MIN_SPOTS_KEY: Final = "minSpots"
MAX_SPOTS_KEY: Final = "maxSpots"
START_TIME_RANGE_KEY: Final = "startTimeRange"
ACTIVITY_IDS_KEY: Final = "activityIds"

# ─── Raw wire shapes: engine mutations ───────────────────────────────────────


class RawEngineRef(TypedDict, total=False):
    id: str
    name: str


class RawEngineResult(TypedDict, total=False):
    """The union payload of the engine mutations: a success carrying ``engine``,
    or an ``InvalidDataError`` / ``NotFoundError`` carrying ``message``."""

    __typename: str
    engine: RawEngineRef
    id: str
    message: str


class CreateEngineResponse(TypedDict, total=False):
    """``data`` payload of :data:`CREATE_PRICING_ENGINE_MUTATION`."""

    createPricingEngine: RawEngineResult


class UpdateEngineResponse(TypedDict, total=False):
    """``data`` payload of :data:`UPDATE_PRICING_ENGINE_MUTATION`."""

    updatePricingEngine: RawEngineResult


class DeleteEngineResponse(TypedDict, total=False):
    """``data`` payload of :data:`DELETE_PRICING_ENGINE_MUTATION`."""

    deletePricingEngine: RawEngineResult


# ─── Raw wire shapes: upsert mutation ────────────────────────────────────────


class RawNamedRef(TypedDict, total=False):
    id: str
    name: str


class RawResolvedMoney(TypedDict, total=False):
    amount: str
    currency: str
    formatted: str | None


class RawResolvedOverride(TypedDict, total=False):
    """A single resolved resource-option override as returned by the API —
    either a ``price`` object or a bare ``percentageAdjustment``."""

    price: RawResolvedMoney
    percentageAdjustment: str


class RawResolvedFilter(TypedDict, total=False):
    """A single resolved filter as returned by the API (tagged by ``__typename``)."""

    __typename: str
    startTimeRange: str
    minSpots: int | None
    maxSpots: int | None


class RawResolvedResourceOption(TypedDict, total=False):
    resourceOption: RawNamedRef
    override: RawResolvedOverride


class RawResolvedPricingOverride(TypedDict, total=False):
    order: int
    resourceOptions: list[RawResolvedResourceOption]
    filters: list[RawResolvedFilter]


class RawActivityContext(TypedDict, total=False):
    """A single resolved activity context as returned by the API."""

    date: str
    activity: RawNamedRef
    engine: RawNamedRef
    overrides: list[RawResolvedPricingOverride]


class RawUpsertResult(TypedDict, total=False):
    """The union payload of the upsert mutation: a success carrying
    ``activityContexts``, or an ``InvalidDataError`` carrying ``message``."""

    __typename: str
    activityContexts: list[RawActivityContext]
    message: str


class UpsertOverridesResponse(TypedDict, total=False):
    """``data`` payload of :data:`UPSERT_PRICING_OVERRIDES_MUTATION`."""

    upsertPricingOverridesActivityContexts: RawUpsertResult


# ─── Clean → raw variable builders ───────────────────────────────────────────


def build_create_engine_input(input: CreateEngineInput) -> dict[str, Any]:
    """Builds the raw create-engine input, attaching an activity-ids filter when scoped."""
    activity_ids = list(input.activity_ids or [])
    raw: dict[str, Any] = {"name": input.name}
    if activity_ids:
        raw["filters"] = [{ACTIVITY_IDS_KEY: activity_ids}]
    return raw


def build_update_engine_input(input: UpdateEngineInput) -> dict[str, Any]:
    """Builds the raw update-engine input. An empty/omitted scope clears the filter."""
    activity_ids = list(input.activity_ids or [])
    return {
        "id": input.engine_id,
        "name": input.name,
        "filters": [{ACTIVITY_IDS_KEY: activity_ids}] if activity_ids else [],
    }


def build_upsert_input(input: UpsertOverridesInput) -> dict[str, Any]:
    """Maps a clean :class:`UpsertOverridesInput` to the raw wire input."""
    return {
        "engineId": input.engine_id,
        "dateRange": input.date_range,
        "activities": [
            {
                "activityId": activity.activity_id,
                "overrides": [
                    {
                        "order": override.order,
                        "resourceOptions": [
                            build_resource_option_override(option)
                            for option in override.resource_options
                        ],
                        "filters": [build_filter(f) for f in override.filters],
                    }
                    for override in activity.overrides
                ],
            }
            for activity in input.activities
        ],
    }


def build_clear_input(input: ClearOverridesInput) -> dict[str, Any]:
    """Builds the raw upsert input that clears all overrides for the given activities."""
    return {
        "engineId": input.engine_id,
        "dateRange": input.date_range,
        "activities": [
            {"activityId": activity_id, "overrides": []} for activity_id in input.activity_ids
        ],
    }


def build_resource_option_override(option: ResourceOptionOverride) -> dict[str, Any]:
    """Strips the ``mode`` tag down to the bare ``price`` / ``percentageAdjustment``
    wire key. Only the wire money fields are sent — ``display_price`` is read-only."""
    if isinstance(option, FixedResourceOptionOverride):
        return {
            "id": option.id,
            PRICE_KEY: {"amount": option.price.amount, "currency": option.price.currency},
        }
    return {"id": option.id, PERCENTAGE_ADJUSTMENT_KEY: option.percentage_adjustment}


def build_filter(filter: PricingOverrideFilter) -> dict[str, Any]:
    """Spells a clean filter in its camelCase wire form, omitting absent spots bounds."""
    if isinstance(filter, SpotsTakenFilter):
        bounds: dict[str, int] = {}
        if filter.spots_taken.min_spots is not None:
            bounds[MIN_SPOTS_KEY] = filter.spots_taken.min_spots
        if filter.spots_taken.max_spots is not None:
            bounds[MAX_SPOTS_KEY] = filter.spots_taken.max_spots
        return {SPOTS_TAKEN_KEY: bounds}
    return {START_TIME_RANGE_KEY: filter.start_time_range}
