from dataclasses import replace
from typing import Any

import pytest

from peek_app_utilities.internal.peek.pricing.pricing_service import PricingService
from peek_app_utilities.models.peek.pricing import (
    ActivityOverrides,
    ClearOverridesInput,
    CreatedPricingEngine,
    CreateEngineInput,
    FixedResourceOptionOverride,
    PercentageResourceOptionOverride,
    PricingEngine,
    PricingMoney,
    PricingOverride,
    ResolvedPercentageOverride,
    ResourceOptionOverride,
    SpotsTakenBounds,
    SpotsTakenFilter,
    StartTimeRangeFilter,
    UpdateEngineInput,
    UpsertOverridesInput,
)
from tests.conftest import FakeGraphQLClient

UPSERT_INPUT = UpsertOverridesInput(
    engine_id="eng-1",
    date_range="[2025-07-04,2025-07-04]",
    activities=[
        ActivityOverrides(
            activity_id="act-1",
            overrides=[
                PricingOverride(
                    order=0,
                    resource_options=[
                        FixedResourceOptionOverride(
                            id="r1", price=PricingMoney(amount="80.00", currency="USD")
                        )
                    ],
                    filters=[
                        SpotsTakenFilter(spots_taken=SpotsTakenBounds(min_spots=4)),
                        StartTimeRangeFilter(start_time_range="[09:00:00,11:00:00]"),
                    ],
                ),
                PricingOverride(
                    order=1,
                    resource_options=[
                        PercentageResourceOptionOverride(id="r1", percentage_adjustment="-25")
                    ],
                    filters=[],
                ),
            ],
        )
    ],
)


def sent_input(gql: FakeGraphQLClient) -> Any:
    """Reads the `variables.input` sent on the first recorded call."""
    return gql.calls[0].variables["input"]


def upsert_success(activity_contexts: list[Any] | None = None) -> dict[str, Any]:
    return {
        "upsertPricingOverridesActivityContexts": {
            "__typename": "UpsertPricingOverridesActivityContextsSuccess",
            "activityContexts": activity_contexts or [],
        }
    }


def with_single_option(option: ResourceOptionOverride) -> UpsertOverridesInput:
    return replace(
        UPSERT_INPUT,
        activities=[
            ActivityOverrides(
                activity_id="act-1",
                overrides=[PricingOverride(order=0, resource_options=[option], filters=[])],
            )
        ],
    )


def create_success():
    return {
        "createPricingEngine": {
            "__typename": "CreatePricingEngineSuccess",
            "engine": {"id": "eng-9"},
        }
    }


def update_success():
    return {
        "updatePricingEngine": {
            "__typename": "UpdatePricingEngineSuccess",
            "engine": {"id": "eng-1", "name": "Renamed"},
        }
    }


# ─── create_engine ────────────────────────────────────────────────────────────


async def test_create_engine_creates_an_unfiltered_engine_and_returns_the_id(gql):
    gql.queue(create_success())

    result = await PricingService(gql).create_engine(CreateEngineInput(name="Schedule"))

    assert result == CreatedPricingEngine(id="eng-9")
    assert sent_input(gql) == {"name": "Schedule"}
    assert gql.calls[0].endpoint_name == "sales"
    assert "mutation CreatePricingEngine" in gql.calls[0].query


async def test_create_engine_scopes_the_engine_to_activity_ids_when_provided(gql):
    gql.queue(create_success())

    await PricingService(gql).create_engine(
        CreateEngineInput(name="Schedule", activity_ids=["act-1", "act-2"])
    )

    assert sent_input(gql) == {
        "name": "Schedule",
        "filters": [{"activityIds": ["act-1", "act-2"]}],
    }


async def test_create_engine_raises_the_invalid_data_error_message(gql):
    gql.queue({"createPricingEngine": {"__typename": "InvalidDataError", "message": "bad name"}})

    with pytest.raises(ValueError, match="bad name"):
        await PricingService(gql).create_engine(CreateEngineInput(name="x"))


async def test_create_engine_raises_when_the_mutation_returns_no_data(gql):
    gql.queue_body({})
    with pytest.raises(ValueError, match="no data"):
        await PricingService(gql).create_engine(CreateEngineInput(name="x"))


async def test_create_engine_requires_a_name(gql):
    with pytest.raises(ValueError, match="name is required"):
        await PricingService(gql).create_engine(CreateEngineInput(name=""))
    assert gql.calls == []


# ─── update_engine ────────────────────────────────────────────────────────────


async def test_update_engine_updates_name_and_scope_returning_the_echoed_engine(gql):
    gql.queue(update_success())

    result = await PricingService(gql).update_engine(
        UpdateEngineInput(engine_id="eng-1", name="Renamed", activity_ids=["act-1"])
    )

    assert result == PricingEngine(id="eng-1", name="Renamed")
    assert sent_input(gql) == {
        "id": "eng-1",
        "name": "Renamed",
        "filters": [{"activityIds": ["act-1"]}],
    }


async def test_update_engine_clears_the_scope_filter_when_no_activity_ids_are_given(gql):
    gql.queue(update_success())

    await PricingService(gql).update_engine(UpdateEngineInput(engine_id="eng-1", name="Renamed"))

    assert sent_input(gql)["filters"] == []


async def test_update_engine_raises_on_not_found_error(gql):
    gql.queue(
        {
            "updatePricingEngine": {
                "__typename": "NotFoundError",
                "id": "eng-1",
                "message": "not found",
            }
        }
    )

    with pytest.raises(ValueError, match="not found"):
        await PricingService(gql).update_engine(UpdateEngineInput(engine_id="eng-1", name="x"))


async def test_update_engine_raises_when_the_mutation_returns_no_data(gql):
    gql.queue_body({})
    with pytest.raises(ValueError, match="no data"):
        await PricingService(gql).update_engine(UpdateEngineInput(engine_id="eng-1", name="x"))


@pytest.mark.parametrize(
    ("input", "pattern"),
    [
        (UpdateEngineInput(engine_id="", name="x"), "engineId is required"),
        (UpdateEngineInput(engine_id="eng-1", name=""), "name is required"),
    ],
)
async def test_update_engine_rejects_invalid_input(gql, input, pattern):
    with pytest.raises(ValueError, match=pattern):
        await PricingService(gql).update_engine(input)
    assert gql.calls == []


# ─── delete_engine ────────────────────────────────────────────────────────────


async def test_delete_engine_resolves_on_success_and_sends_the_engine_id(gql):
    gql.queue(
        {
            "deletePricingEngine": {
                "__typename": "DeletePricingEngineSuccess",
                "engine": {"id": "eng-1", "name": "Schedule"},
            }
        }
    )

    assert await PricingService(gql).delete_engine("eng-1") is None
    assert gql.calls[0].variables["id"] == "eng-1"
    assert "mutation DeletePricingEngine" in gql.calls[0].query


async def test_delete_engine_resolves_idempotent_when_the_engine_was_already_gone(gql):
    gql.queue(
        {
            "deletePricingEngine": {
                "__typename": "NotFoundError",
                "id": "eng-1",
                "message": "not found",
            }
        }
    )

    assert await PricingService(gql).delete_engine("eng-1") is None


async def test_delete_engine_requires_an_engine_id(gql):
    with pytest.raises(ValueError, match="engineId is required"):
        await PricingService(gql).delete_engine("")
    assert gql.calls == []


# ─── upsert_overrides ─────────────────────────────────────────────────────────


async def test_upsert_overrides_maps_mode_tagged_resource_options_to_the_raw_wire_shape(gql):
    gql.queue(upsert_success())

    await PricingService(gql).upsert_overrides(UPSERT_INPUT)

    assert sent_input(gql) == {
        "engineId": "eng-1",
        "dateRange": "[2025-07-04,2025-07-04]",
        "activities": [
            {
                "activityId": "act-1",
                "overrides": [
                    {
                        "order": 0,
                        "resourceOptions": [
                            {"id": "r1", "price": {"amount": "80.00", "currency": "USD"}}
                        ],
                        "filters": [
                            {"spotsTaken": {"minSpots": 4}},
                            {"startTimeRange": "[09:00:00,11:00:00]"},
                        ],
                    },
                    {
                        "order": 1,
                        "resourceOptions": [{"id": "r1", "percentageAdjustment": "-25"}],
                        "filters": [],
                    },
                ],
            }
        ],
    }
    assert "mutation UpsertPricingOverridesActivityContexts" in gql.calls[0].query


async def test_upsert_overrides_sends_both_spots_bounds_when_present(gql):
    gql.queue(upsert_success())
    input = replace(
        UPSERT_INPUT,
        activities=[
            ActivityOverrides(
                activity_id="act-1",
                overrides=[
                    PricingOverride(
                        order=0,
                        resource_options=[],
                        filters=[
                            SpotsTakenFilter(spots_taken=SpotsTakenBounds(min_spots=4, max_spots=9))
                        ],
                    )
                ],
            )
        ],
    )

    await PricingService(gql).upsert_overrides(input)

    sent = sent_input(gql)["activities"][0]["overrides"][0]["filters"]
    assert sent == [{"spotsTaken": {"minSpots": 4, "maxSpots": 9}}]


async def test_upsert_overrides_strips_a_caller_supplied_display_price_from_the_wire_input(gql):
    gql.queue(upsert_success())

    await PricingService(gql).upsert_overrides(
        with_single_option(
            FixedResourceOptionOverride(
                id="r1",
                price=PricingMoney(amount="80.00", currency="USD", display_price="$80.00"),
            )
        )
    )

    sent = sent_input(gql)["activities"][0]["overrides"][0]["resourceOptions"][0]
    assert sent == {"id": "r1", "price": {"amount": "80.00", "currency": "USD"}}


async def test_upsert_overrides_returns_the_resolved_activity_contexts(gql):
    gql.queue(
        upsert_success(
            [
                {
                    "date": "2025-07-04",
                    "activity": {"id": "act-1", "name": "Tour"},
                    "engine": {"id": "eng-1", "name": "Schedule"},
                    "overrides": [
                        {
                            "order": 0,
                            "resourceOptions": [
                                {
                                    "resourceOption": {"id": "r1", "name": "Adult"},
                                    "override": {"percentageAdjustment": "-25"},
                                }
                            ],
                            "filters": [],
                        }
                    ],
                }
            ]
        )
    )

    result = await PricingService(gql).upsert_overrides(UPSERT_INPUT)

    override = result.activity_contexts[0].overrides[0].resource_options[0].override
    assert override == ResolvedPercentageOverride(percentage_adjustment="-25")


async def test_upsert_overrides_raises_the_invalid_data_error_message(gql):
    gql.queue(
        {
            "upsertPricingOverridesActivityContexts": {
                "__typename": "InvalidDataError",
                "message": "overlapping ranges",
            }
        }
    )

    with pytest.raises(ValueError, match="overlapping ranges"):
        await PricingService(gql).upsert_overrides(UPSERT_INPUT)


async def test_upsert_overrides_raises_when_the_mutation_returns_no_data(gql):
    gql.queue_body({})
    with pytest.raises(ValueError, match="no data"):
        await PricingService(gql).upsert_overrides(UPSERT_INPUT)


@pytest.mark.parametrize(
    ("input", "pattern"),
    [
        (replace(UPSERT_INPUT, engine_id=""), "engineId is required"),
        (replace(UPSERT_INPUT, date_range=""), "dateRange is required"),
        (replace(UPSERT_INPUT, activities=None), "activities is required"),
        (
            replace(UPSERT_INPUT, activities=[ActivityOverrides(activity_id="", overrides=[])]),
            "activityId is required",
        ),
        (
            with_single_option(PercentageResourceOptionOverride(id="", percentage_adjustment="-5")),
            "resource-option id is required",
        ),
        (
            with_single_option(
                FixedResourceOptionOverride(
                    id="r1", price=PricingMoney(amount="10", currency="usd")
                )
            ),
            "currency must be 3 uppercase letters",
        ),
        (
            with_single_option(
                FixedResourceOptionOverride(
                    id="r1", price=PricingMoney(amount="abc", currency="USD")
                )
            ),
            "price amount must be a valid number",
        ),
        (
            with_single_option(
                PercentageResourceOptionOverride(id="r1", percentage_adjustment="nope")
            ),
            "percentageAdjustment must be a valid number",
        ),
        (
            with_single_option(
                PercentageResourceOptionOverride(id="r1", percentage_adjustment="nan")
            ),
            "percentageAdjustment must be a valid number",
        ),
        (
            with_single_option(
                PercentageResourceOptionOverride(id="r1", percentage_adjustment="-100")
            ),
            "percentageAdjustment must be greater than -100",
        ),
    ],
)
async def test_upsert_overrides_rejects_invalid_input(gql, input, pattern):
    gql.queue(upsert_success())
    with pytest.raises(ValueError, match=pattern):
        await PricingService(gql).upsert_overrides(input)
    assert gql.calls == []


# ─── clear_overrides ──────────────────────────────────────────────────────────


async def test_clear_overrides_sends_empty_overrides_for_each_activity_id(gql):
    gql.queue(upsert_success())

    result = await PricingService(gql).clear_overrides(
        ClearOverridesInput(
            engine_id="eng-1",
            date_range="[2025-07-04,2025-07-04]",
            activity_ids=["act-1", "act-2"],
        )
    )

    assert result.activity_contexts == []
    assert sent_input(gql) == {
        "engineId": "eng-1",
        "dateRange": "[2025-07-04,2025-07-04]",
        "activities": [
            {"activityId": "act-1", "overrides": []},
            {"activityId": "act-2", "overrides": []},
        ],
    }


@pytest.mark.parametrize(
    ("input", "pattern"),
    [
        (
            ClearOverridesInput(engine_id="", date_range="[d,d]", activity_ids=["a"]),
            "engineId is required",
        ),
        (
            ClearOverridesInput(engine_id="eng-1", date_range="", activity_ids=["a"]),
            "dateRange is required",
        ),
        (
            ClearOverridesInput(engine_id="eng-1", date_range="[d,d]", activity_ids=None),
            "activities is required",
        ),
        (
            ClearOverridesInput(engine_id="eng-1", date_range="[d,d]", activity_ids=[""]),
            "activityId is required",
        ),
    ],
)
async def test_clear_overrides_rejects_invalid_input(gql, input, pattern):
    gql.queue(upsert_success())
    with pytest.raises(ValueError, match=pattern):
        await PricingService(gql).clear_overrides(input)
    assert gql.calls == []
