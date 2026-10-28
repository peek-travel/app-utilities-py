from typing import Any

import pytest

from peek_app_utilities.internal.peek.bookings.addon_converter import (
    AddonItem,
    AddonItemOption,
    parse_sale_node,
    to_booking_addon,
)
from peek_app_utilities.models.peek.booking_addon import (
    BookingAddon,
    BookingAddonMoney,
    BookingAddonOption,
)

MONEY = {"amount": "10.00", "currency": "USD", "formatted": "$10.00"}
MONEY_MODEL = BookingAddonMoney(amount="10.00", currency="USD", formatted="$10.00")


def node(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "b_1",
        "displayId": "B-1",
        "refid": "bq-1",
        "reservationStatus": "CONFIRMED",
        "order": {"id": "o_1", "displayId": "O-1"},
        "items": [],
        **overrides,
    }


class TestParseSaleNode:
    def test_maps_items_and_options_into_the_internal_model(self):
        items = parse_sale_node(
            node(
                items=[
                    {
                        "id": "it-1",
                        "refid": "ir-1",
                        "reservationStatus": "CONFIRMED",
                        "value": {"total": MONEY},
                        "options": [
                            {
                                "refid": "or-1",
                                "reservationStatus": "CONFIRMED",
                                "price": MONEY,
                                "itemOptionSnapshot": {"id": "opt-1", "name": "Helmet"},
                                "itemSnapshot": {"id": "item-1", "name": "Safety Gear"},
                            }
                        ],
                    }
                ]
            )
        )

        assert items == [
            AddonItem(
                booking_id="b_1",
                display_id="B-1",
                order_id="o_1",
                total=MONEY_MODEL,
                booking_quote_refid="bq-1",
                booking_quote_reservation_status="CONFIRMED",
                addon_item_options=[
                    AddonItemOption(
                        item_id="item-1",
                        option_id="opt-1",
                        item_name="Safety Gear",
                        option_name="Helmet",
                        option_refid="or-1",
                        option_reservation_status="CONFIRMED",
                        item_reservation_status="CONFIRMED",
                        item_refid="ir-1",
                    )
                ],
            )
        ]

    def test_defaults_missing_booking_level_and_snapshot_fields_to_empty_strings(self):
        items = parse_sale_node(
            {
                "id": "",
                "displayId": "",
                "refid": "",
                "reservationStatus": "",
                "order": None,
                "items": [
                    {
                        "id": "it-1",
                        "refid": "",
                        "reservationStatus": "",
                        "value": None,
                        "options": [
                            {
                                "refid": "",
                                "reservationStatus": "",
                                "price": None,
                                "itemOptionSnapshot": None,
                                "itemSnapshot": None,
                            }
                        ],
                    }
                ],
            }
        )

        assert items[0].booking_id == ""
        assert items[0].order_id == ""
        assert items[0].total is None
        opt = items[0].addon_item_options[0]
        assert (opt.item_id, opt.option_id, opt.item_name, opt.option_name, opt.option_refid) == (
            "",
            "",
            "",
            "",
            "",
        )

    def test_treats_null_items_options_as_empty_arrays(self):
        assert parse_sale_node(node(items=None)) == []
        items = parse_sale_node(
            node(
                items=[
                    {
                        "id": "it-1",
                        "refid": "ir-1",
                        "reservationStatus": "CONFIRMED",
                        "value": {"total": MONEY},
                        "options": None,
                    }
                ]
            )
        )
        assert items[0].addon_item_options == []


def opt(**overrides: Any) -> AddonItemOption:
    base: dict[str, Any] = {
        "item_id": "item-1",
        "option_id": "opt-1",
        "item_name": "Safety Gear",
        "option_name": "Helmet",
        "option_refid": "or-1",
        "option_reservation_status": "CONFIRMED",
        "item_reservation_status": "CONFIRMED",
        "item_refid": "ir-1",
    }
    return AddonItemOption(**{**base, **overrides})


def item(options: list[AddonItemOption]) -> AddonItem:
    return AddonItem(
        booking_id="b_1",
        display_id="B-1",
        order_id="o_1",
        total=MONEY_MODEL,
        booking_quote_refid="bq-1",
        booking_quote_reservation_status="CONFIRMED",
        addon_item_options=options,
    )


class TestToBookingAddon:
    def test_returns_none_when_there_are_no_options(self):
        assert to_booking_addon(item([])) is None

    def test_groups_options_by_id_with_a_quantity_and_carries_the_total(self):
        result = to_booking_addon(item([opt(option_refid="or-1"), opt(option_refid="or-2")]))
        assert result == BookingAddon(
            addon_id="item-1",
            addon_name="Safety Gear",
            total=MONEY_MODEL,
            addon_options=[
                BookingAddonOption(addon_option_id="opt-1", addon_option_name="Helmet", quantity=2)
            ],
        )

    def test_drops_canceled_options_and_returns_none_when_all_are_canceled(self):
        assert to_booking_addon(item([opt(option_reservation_status="CANCELED")])) is None

    def test_raises_when_options_reference_mismatched_item_ids(self):
        with pytest.raises(ValueError, match="mismatched item IDs"):
            to_booking_addon(item([opt(), opt(item_id="item-2")]))
