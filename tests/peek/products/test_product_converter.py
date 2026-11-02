from peek_app_utilities.internal.peek.money import to_pricing_money
from peek_app_utilities.internal.peek.products.product_converter import (
    from_activities,
    from_item_option_nodes,
)
from peek_app_utilities.internal.peek.products.product_queries import (
    ActivityNode,
    ItemOptionNode,
)
from peek_app_utilities.models.peek.pricing import PricingMoney
from peek_app_utilities.models.peek.product import (
    ADD_ON_PRODUCT_TYPE,
    Product,
    ProductMeetingLocation,
    ProductTicket,
)

# ─── from_activities ─────────────────────────────────────────────────────────


def test_maps_an_activity_into_a_clean_product():
    activities: list[ActivityNode] = [
        {
            "name": "Kayak Tour",
            "id": "act-1",
            "legacyId": "legacy-1",
            "type": "ACTIVITY",
            "colorHex": "#1A2B3C",
            "currency": "USD",
            "imageUrl": "https://img.peek.com/act-1.jpg",
            "description": "<p>Paddle the bay.</p>",
            "meetingLocationFormattedAddress": "1 Dock St, Bay City",
            "meetingLocationUrl": "https://maps.example.com/dock",
            "infoMeetingLocation": "Meet at the boathouse.",
            "resourceOptions": [
                {
                    "id": "r1",
                    "name": "Single",
                    "priceRange": {
                        "min": {"currency": "USD", "amount": "50.00", "formatted": "$50.00"},
                        "max": {"currency": "USD", "amount": "80.00", "formatted": "$80.00"},
                    },
                },
                {"id": "r2", "name": "Double"},
            ],
        }
    ]

    assert from_activities(activities) == [
        Product(
            product_id="act-1",
            name="Kayak Tour",
            type="ACTIVITY",
            color="#1A2B3C",
            currency="USD",
            image_url="https://img.peek.com/act-1.jpg",
            description="<p>Paddle the bay.</p>",
            meeting_location=ProductMeetingLocation(
                summary="Meet at the boathouse.",
                address="1 Dock St, Bay City",
                url="https://maps.example.com/dock",
            ),
            tickets=[
                ProductTicket(
                    id="r1",
                    name="Single",
                    min_price=PricingMoney(amount="50.00", currency="USD", display_price="$50.00"),
                    max_price=PricingMoney(amount="80.00", currency="USD", display_price="$80.00"),
                ),
                ProductTicket(id="r2", name="Double", min_price=None, max_price=None),
            ],
        )
    ]


def test_maps_a_price_range_with_no_formatted_string_omitting_display_price():
    activities: list[ActivityNode] = [
        {
            "name": "Kayak Tour",
            "id": "act-1",
            "type": "ACTIVITY",
            "colorHex": "#000000",
            "currency": "USD",
            "resourceOptions": [
                {
                    "id": "r1",
                    "name": "Single",
                    "priceRange": {"min": {"currency": "USD", "amount": "50.00"}, "max": None},
                }
            ],
        }
    ]

    assert from_activities(activities)[0].tickets == [
        ProductTicket(
            id="r1",
            name="Single",
            min_price=PricingMoney(amount="50.00", currency="USD"),
            max_price=None,
        )
    ]
    min_price = from_activities(activities)[0].tickets[0].min_price
    assert min_price is not None
    assert min_price.display_price is None


def test_falls_back_to_legacy_id_and_empty_color_and_tolerates_missing_resource_options():
    activities: list[ActivityNode] = [
        {
            "name": "No Primary Id",
            "id": "",
            "legacyId": "legacy-9",
            "type": "ACTIVITY",
            "colorHex": "",
        }
    ]

    assert from_activities(activities) == [
        Product(
            product_id="legacy-9",
            name="No Primary Id",
            type="ACTIVITY",
            color="",
            currency="",
            image_url=None,
            description=None,
            meeting_location=None,
            tickets=[],
        )
    ]


def test_maps_catalog_fields_to_none_when_peek_reports_none():
    activities: list[ActivityNode] = [
        {
            "name": "Bare",
            "id": "act-2",
            "type": "ACTIVITY",
            "colorHex": "#000000",
            "currency": "USD",
            "resourceOptions": [],
        }
    ]

    product = from_activities(activities)[0]
    assert product.image_url is None
    assert product.description is None
    assert product.meeting_location is None


def test_keeps_a_partial_meeting_location_filling_absent_fields_with_none():
    activities: list[ActivityNode] = [
        {
            "name": "Partial Location",
            "id": "act-3",
            "type": "ACTIVITY",
            "colorHex": "#000000",
            "currency": "USD",
            "infoMeetingLocation": "Lobby",
            "resourceOptions": [],
        }
    ]

    assert from_activities(activities)[0].meeting_location == ProductMeetingLocation(
        summary="Lobby", address=None, url=None
    )


def test_falls_back_to_empty_product_id_when_neither_id_is_present():
    activities: list[ActivityNode] = [
        {
            "name": "Anonymous",
            "id": "",
            "type": "ACTIVITY",
            "colorHex": "#000000",
            "resourceOptions": [],
        }
    ]

    assert from_activities(activities)[0].product_id == ""


# ─── to_pricing_money (shared money helper) ──────────────────────────────────


def test_to_pricing_money_returns_none_for_absent_input():
    assert to_pricing_money(None) is None
    assert to_pricing_money({}) is None


def test_to_pricing_money_carries_formatted_as_display_price():
    assert to_pricing_money({"amount": "1.00", "currency": "EUR", "formatted": "€1.00"}) == (
        PricingMoney(amount="1.00", currency="EUR", display_price="€1.00")
    )
    assert to_pricing_money({"amount": "1.00", "currency": "EUR", "formatted": None}) == (
        PricingMoney(amount="1.00", currency="EUR")
    )


# ─── from_item_option_nodes ──────────────────────────────────────────────────


def test_groups_options_under_their_parent_item_as_add_on_products():
    nodes: list[ItemOptionNode] = [
        {
            "id": "opt-1",
            "name": "Helmet",
            "description": None,
            "item": {"id": "item-1", "name": "Safety Gear"},
        },
        {
            "id": "opt-2",
            "name": "Life Vest",
            "description": "Required",
            "item": {"id": "item-1", "name": "Safety Gear"},
        },
        {
            "id": "opt-3",
            "name": "Photo Package",
            "description": None,
            "item": {"id": "item-2", "name": "Extras"},
        },
    ]

    assert from_item_option_nodes(nodes) == [
        Product(
            product_id="item-1",
            name="Safety Gear",
            type=ADD_ON_PRODUCT_TYPE,
            color="#FFFFFF",
            currency="",
            image_url=None,
            description=None,
            meeting_location=None,
            tickets=[
                ProductTicket(id="opt-1", name="Helmet", min_price=None, max_price=None),
                ProductTicket(id="opt-2", name="Life Vest", min_price=None, max_price=None),
            ],
        ),
        Product(
            product_id="item-2",
            name="Extras",
            type=ADD_ON_PRODUCT_TYPE,
            color="#FFFFFF",
            currency="",
            image_url=None,
            description=None,
            meeting_location=None,
            tickets=[
                ProductTicket(id="opt-3", name="Photo Package", min_price=None, max_price=None)
            ],
        ),
    ]


def test_skips_nodes_without_a_parent_item_id():
    nodes: list[ItemOptionNode] = [
        {"id": "opt-x", "name": "Orphan", "description": None, "item": {"id": "", "name": ""}},
        {"id": "opt-y", "name": "No Item", "description": None},
    ]

    assert from_item_option_nodes(nodes) == []


def test_returns_an_empty_list_for_no_nodes():
    assert from_item_option_nodes([]) == []
