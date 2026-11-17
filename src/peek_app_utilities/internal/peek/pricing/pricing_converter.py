"""Pure functions mapping raw pricing-override nodes into the clean
:class:`PricingActivityContext` model. No I/O — easy to unit-test.

Two normalizations happen here, both erasing quirks of the wire format:

- Each resource-option override arrives as either a ``price`` object or a bare
  ``percentageAdjustment``; we tag it with a ``mode`` discriminant.
- Each filter arrives ``__typename``-tagged with ``null``-able bounds; we map it
  back to the same compact :data:`PricingOverrideFilter` union used on input,
  dropping absent (``null``) spots bounds.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from peek_app_utilities.internal.peek.money import to_pricing_money
from peek_app_utilities.internal.peek.pricing.pricing_queries import (
    MAX_SPOTS_KEY,
    MIN_SPOTS_KEY,
    PRICE_KEY,
    SPOTS_TAKEN_FILTER_TYPENAME,
    START_TIME_RANGE_KEY,
    TYPENAME_KEY,
    RawActivityContext,
    RawResolvedFilter,
    RawResolvedOverride,
    RawResolvedPricingOverride,
    RawResolvedResourceOption,
)
from peek_app_utilities.models.peek.pricing import (
    PricingActivityContext,
    PricingMoney,
    PricingNamedRef,
    PricingOverrideFilter,
    ResolvedFixedOverride,
    ResolvedOverride,
    ResolvedPercentageOverride,
    ResolvedPricingOverride,
    ResolvedResourceOption,
    SpotsTakenBounds,
    SpotsTakenFilter,
    StartTimeRangeFilter,
)


def from_activity_contexts(contexts: Iterable[RawActivityContext]) -> list[PricingActivityContext]:
    """Converts the raw activity contexts from an upsert response into clean models."""
    return [_from_activity_context(context) for context in contexts]


def _from_activity_context(context: RawActivityContext) -> PricingActivityContext:
    return PricingActivityContext(
        date=context.get("date") or "",
        activity=_from_named_ref(context.get("activity")),
        engine=_from_named_ref(context.get("engine")),
        overrides=[_from_override(o) for o in context.get("overrides") or []],
    )


def _from_named_ref(ref: Mapping[str, Any] | None) -> PricingNamedRef:
    node = ref or {}
    return PricingNamedRef(id=node.get("id") or "", name=node.get("name") or "")


def _from_override(override: RawResolvedPricingOverride) -> ResolvedPricingOverride:
    return ResolvedPricingOverride(
        order=int(override.get("order") or 0),
        resource_options=[_from_resource_option(o) for o in override.get("resourceOptions") or []],
        filters=[_from_filter(f) for f in override.get("filters") or []],
    )


def _from_resource_option(option: RawResolvedResourceOption) -> ResolvedResourceOption:
    return ResolvedResourceOption(
        resource_option=_from_named_ref(option.get("resourceOption")),
        override=_from_resolved_override(option.get("override") or {}),
    )


def _from_resolved_override(override: RawResolvedOverride) -> ResolvedOverride:
    if PRICE_KEY in override:
        price = to_pricing_money(override.get(PRICE_KEY)) or PricingMoney(amount="", currency="")
        return ResolvedFixedOverride(price=price)
    return ResolvedPercentageOverride(
        percentage_adjustment=override.get("percentageAdjustment") or ""
    )


def _from_filter(filter: RawResolvedFilter) -> PricingOverrideFilter:
    if filter.get(TYPENAME_KEY) == SPOTS_TAKEN_FILTER_TYPENAME:
        return SpotsTakenFilter(
            spots_taken=SpotsTakenBounds(
                min_spots=filter.get(MIN_SPOTS_KEY), max_spots=filter.get(MAX_SPOTS_KEY)
            )
        )
    return StartTimeRangeFilter(start_time_range=filter.get(START_TIME_RANGE_KEY) or "")
