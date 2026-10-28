"""Pure mappers between the raw ``sales`` add-ons response and the add-on models.

:func:`parse_sale_node` produces the internal, detail-rich :class:`AddonItem`
model (refids + reservation statuses) that the service uses to build add/cancel
mutations. :func:`to_booking_addon` collapses one internal item into the clean,
public :class:`BookingAddon`. The internal model is intentionally not exported
from the package's public entry point.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from peek_app_utilities.internal.peek.bookings.addon_queries import ADDON_OPTION_STATUS_CANCELED
from peek_app_utilities.models.peek.booking_addon import (
    BookingAddon,
    BookingAddonMoney,
    BookingAddonOption,
)

ERROR_INCONSISTENT_ADDON_ITEM_ID: Final = "Add-on group contains options with mismatched item IDs"


@dataclass(frozen=True, slots=True, kw_only=True)
class AddonItemOption:
    """One add-on option on a booking, with the refids/statuses needed to mutate it."""

    item_id: str
    option_id: str
    item_name: str
    option_name: str
    option_refid: str
    option_reservation_status: str
    item_reservation_status: str
    item_refid: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AddonItem:
    """One add-on item on a booking (internal; grouped by add-on item)."""

    booking_id: str
    display_id: str
    order_id: str
    total: BookingAddonMoney | None
    booking_quote_refid: str
    booking_quote_reservation_status: str
    addon_item_options: list[AddonItemOption]


def _to_addon_money(raw: Any) -> BookingAddonMoney | None:
    if not raw:
        return None
    node: Mapping[str, Any] = raw
    return BookingAddonMoney(
        amount=node.get("amount") or "",
        currency=node.get("currency") or "",
        formatted=node.get("formatted") or "",
    )


def parse_sale_node(node: Mapping[str, Any]) -> list[AddonItem]:
    """Converts a single booking node into the internal :class:`AddonItem` list.
    Booking-level identifiers (booking id, display id, order id) are repeated on
    each item for convenience."""
    booking_id = node.get("id") or ""
    display_id = node.get("displayId") or ""
    order_id = (node.get("order") or {}).get("id") or ""
    booking_quote_refid = node.get("refid") or ""
    booking_quote_reservation_status = node.get("reservationStatus") or ""
    raw_items = node.get("items")
    items: list[Mapping[str, Any]] = raw_items if isinstance(raw_items, list) else []

    result: list[AddonItem] = []
    for item in items:
        raw_options = item.get("options")
        options: list[Mapping[str, Any]] = raw_options if isinstance(raw_options, list) else []
        addon_item_options = [
            AddonItemOption(
                item_id=(opt.get("itemSnapshot") or {}).get("id") or "",
                option_id=(opt.get("itemOptionSnapshot") or {}).get("id") or "",
                item_name=(opt.get("itemSnapshot") or {}).get("name") or "",
                option_name=(opt.get("itemOptionSnapshot") or {}).get("name") or "",
                option_refid=opt.get("refid") or "",
                option_reservation_status=opt.get("reservationStatus") or "",
                item_reservation_status=item.get("reservationStatus") or "",
                item_refid=item.get("refid") or "",
            )
            for opt in options
        ]
        result.append(
            AddonItem(
                booking_id=booking_id,
                display_id=display_id,
                order_id=order_id,
                total=_to_addon_money((item.get("value") or {}).get("total")),
                booking_quote_refid=booking_quote_refid,
                booking_quote_reservation_status=booking_quote_reservation_status,
                addon_item_options=addon_item_options,
            )
        )
    return result


def to_booking_addon(item: AddonItem) -> BookingAddon | None:
    """Collapses one internal :class:`AddonItem` (already grouped by add-on item
    id) into a clean public :class:`BookingAddon`. All of the item's options must
    share the same item id (a data-integrity invariant); a mismatch raises
    ``ValueError``. Canceled options are dropped and the rest are combined by
    option id with a quantity count. Returns ``None`` when no live options
    remain, so the caller can omit the add-on entirely."""
    options = item.addon_item_options
    if not options:
        return None

    addon_id = options[0].item_id
    addon_name = options[0].item_name

    if any(opt.item_id != addon_id for opt in options):
        raise ValueError(ERROR_INCONSISTENT_ADDON_ITEM_ID)

    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    for opt in options:
        if opt.option_reservation_status == ADDON_OPTION_STATUS_CANCELED:
            continue
        names.setdefault(opt.option_id, opt.option_name)
        counts[opt.option_id] = counts.get(opt.option_id, 0) + 1

    addon_options = [
        BookingAddonOption(addon_option_id=option_id, addon_option_name=names[option_id], quantity=count)
        for option_id, count in counts.items()
    ]
    if not addon_options:
        return None

    return BookingAddon(
        addon_id=addon_id, addon_name=addon_name, total=item.total, addon_options=addon_options
    )
