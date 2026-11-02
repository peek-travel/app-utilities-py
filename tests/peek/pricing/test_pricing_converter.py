from peek_app_utilities.internal.peek.pricing.pricing_converter import from_activity_contexts
from peek_app_utilities.internal.peek.pricing.pricing_queries import (
    SPOTS_TAKEN_FILTER_TYPENAME,
    START_TIME_RANGE_FILTER_TYPENAME,
)
from peek_app_utilities.models.peek.pricing import (
    PricingActivityContext,
    PricingMoney,
    PricingNamedRef,
    ResolvedFixedOverride,
    ResolvedPercentageOverride,
    ResolvedPricingOverride,
    ResolvedResourceOption,
    SpotsTakenBounds,
    SpotsTakenFilter,
    StartTimeRangeFilter,
)


def test_maps_a_full_context_fixed_and_percentage_overrides_and_both_filter_kinds():
    raw = [
        {
            "date": "2025-07-04",
            "activity": {"id": "act-1", "name": "Kayak Tour"},
            "engine": {"id": "eng-1", "name": "Schedule"},
            "overrides": [
                {
                    "order": 0,
                    "resourceOptions": [
                        {
                            "resourceOption": {"id": "r1", "name": "Adult"},
                            "override": {
                                "price": {
                                    "amount": "80.00",
                                    "currency": "USD",
                                    "formatted": "$80.00",
                                }
                            },
                        }
                    ],
                    "filters": [
                        {"__typename": SPOTS_TAKEN_FILTER_TYPENAME, "minSpots": 4, "maxSpots": 9},
                        {
                            "__typename": START_TIME_RANGE_FILTER_TYPENAME,
                            "startTimeRange": "[09:00:00,11:00:00]",
                        },
                    ],
                },
                {
                    "order": 1,
                    "resourceOptions": [
                        {
                            "resourceOption": {"id": "r1", "name": "Adult"},
                            "override": {"percentageAdjustment": "-25"},
                        }
                    ],
                    "filters": [],
                },
            ],
        }
    ]

    assert from_activity_contexts(raw) == [
        PricingActivityContext(
            date="2025-07-04",
            activity=PricingNamedRef(id="act-1", name="Kayak Tour"),
            engine=PricingNamedRef(id="eng-1", name="Schedule"),
            overrides=[
                ResolvedPricingOverride(
                    order=0,
                    resource_options=[
                        ResolvedResourceOption(
                            resource_option=PricingNamedRef(id="r1", name="Adult"),
                            override=ResolvedFixedOverride(
                                price=PricingMoney(
                                    amount="80.00", currency="USD", display_price="$80.00"
                                )
                            ),
                        )
                    ],
                    filters=[
                        SpotsTakenFilter(spots_taken=SpotsTakenBounds(min_spots=4, max_spots=9)),
                        StartTimeRangeFilter(start_time_range="[09:00:00,11:00:00]"),
                    ],
                ),
                ResolvedPricingOverride(
                    order=1,
                    resource_options=[
                        ResolvedResourceOption(
                            resource_option=PricingNamedRef(id="r1", name="Adult"),
                            override=ResolvedPercentageOverride(percentage_adjustment="-25"),
                        )
                    ],
                    filters=[],
                ),
            ],
        )
    ]
    fixed = from_activity_contexts(raw)[0].overrides[0].resource_options[0].override
    percentage = from_activity_contexts(raw)[0].overrides[1].resource_options[0].override
    assert fixed.mode == "fixed"
    assert percentage.mode == "percentage"


def test_drops_null_spots_bounds_keeping_only_the_present_side():
    raw = [
        {
            "date": "2025-07-04",
            "activity": {"id": "act-1", "name": "Tour"},
            "engine": {"id": "eng-1", "name": "Schedule"},
            "overrides": [
                {
                    "order": 0,
                    "resourceOptions": [],
                    "filters": [
                        {"__typename": SPOTS_TAKEN_FILTER_TYPENAME, "minSpots": 4, "maxSpots": None}
                    ],
                },
                {
                    "order": 1,
                    "resourceOptions": [],
                    "filters": [
                        {"__typename": SPOTS_TAKEN_FILTER_TYPENAME, "minSpots": None, "maxSpots": 3}
                    ],
                },
            ],
        }
    ]

    [context] = from_activity_contexts(raw)
    assert context.overrides[0].filters == [
        SpotsTakenFilter(spots_taken=SpotsTakenBounds(min_spots=4))
    ]
    assert context.overrides[1].filters == [
        SpotsTakenFilter(spots_taken=SpotsTakenBounds(max_spots=3))
    ]


def test_maps_a_cleared_context_no_overrides():
    raw = [
        {
            "date": "2025-07-04",
            "activity": {"id": "act-1", "name": "Tour"},
            "engine": {"id": "eng-1", "name": "Schedule"},
            "overrides": [],
        }
    ]

    assert from_activity_contexts(raw) == [
        PricingActivityContext(
            date="2025-07-04",
            activity=PricingNamedRef(id="act-1", name="Tour"),
            engine=PricingNamedRef(id="eng-1", name="Schedule"),
            overrides=[],
        )
    ]


def test_returns_an_empty_list_for_no_contexts():
    assert from_activity_contexts([]) == []


def test_degrades_missing_fields_instead_of_raising():
    [context] = from_activity_contexts(
        [
            {
                "overrides": [
                    {
                        "resourceOptions": [{"override": {"price": {}}}, {}],
                        "filters": [{"__typename": START_TIME_RANGE_FILTER_TYPENAME}],
                    }
                ]
            }
        ]
    )
    assert context.date == ""
    assert context.activity == PricingNamedRef(id="", name="")
    override = context.overrides[0]
    assert override.order == 0
    assert override.resource_options[0].override == ResolvedFixedOverride(
        price=PricingMoney(amount="", currency="")
    )
    assert override.resource_options[1].override == ResolvedPercentageOverride(
        percentage_adjustment=""
    )
    assert override.filters == [StartTimeRangeFilter(start_time_range="")]
