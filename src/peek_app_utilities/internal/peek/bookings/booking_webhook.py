"""Public webhook surface for bookings.

A Peek "backoffice" booking webhook's payload shape is defined by a GraphQL
field selection registered with the hook. That registration happens once, in
an external system (the App Store ``broadcast_to_url`` config) — not from
consumer code — so this package registers nothing at runtime. It owns the two
pieces that must agree:

- :data:`BOOKING_WEBHOOK_GQL_QUERY` — the canonical selection to paste into
  that external config. A setup-time artifact surfaced through
  ``docs/webhooks.md`` and pinned by a drift-guard test; **internal**, not part
  of the runtime public API.
- :func:`parse_booking_webhook` — the only runtime export; turns a delivered
  payload into a clean :class:`Booking` using the very same converter as the
  read path.

Parsing an inbound webhook needs no auth, no network, and no client — it is a
pure transform — so it is exported as a standalone function rather than a
method on ``PeekAccessService`` (the receiver may not hold gateway credentials).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Final

from peek_app_utilities.internal.peek.bookings.booking_converter import from_booking_node
from peek_app_utilities.internal.peek.bookings.booking_queries import (
    BOOKING_GUESTS_FIELDS,
    BOOKING_QUERY_FIELDS,
    PRICE_BREAKDOWN_FIELDS,
    VALUE_OPEN_TOKEN,
)
from peek_app_utilities.models.peek.booking import Booking

_PAYLOAD_BOOKING_KEY: Final = "booking"
"""The envelope key the webhook delivery wraps the booking node under."""

_PRICE_BREAKDOWN_KEYS: Final = (
    "convenienceFee",
    "deposit",
    "discount",
    "discountedPrice",
    "fees",
    "flatPartnerFee",
    "price",
    "retailPrice",
    "taxes",
)
"""Price-breakdown field names that only appear on ``value`` when the breakdown
was requested — their presence is how :func:`parse_booking_webhook`
auto-detects it."""

_WHITESPACE_RE: Final = re.compile(r"\s+")
_BOOKING_GUESTS_KEY: Final = "bookingGuests"
_VALUE_KEY: Final = "value"


def _build_maximal_webhook_query() -> str:
    fields = BOOKING_QUERY_FIELDS.replace(
        VALUE_OPEN_TOKEN, f"{VALUE_OPEN_TOKEN} {PRICE_BREAKDOWN_FIELDS}", 1
    )
    return _WHITESPACE_RE.sub(" ", f"{{ {fields} {BOOKING_GUESTS_FIELDS} }}").strip()


BOOKING_WEBHOOK_GQL_QUERY: Final = _build_maximal_webhook_query()
"""The canonical GraphQL selection set to register with the booking webhook — the
value that goes in the external ``output_fields_gql_query`` config.

It is the **maximal** selection (guests + full price breakdown included), so a
single registration captures everything and :func:`parse_booking_webhook`
auto-detects whatever the payload actually carries. It is the bare selection
set (``{ … }``), not a wrapped ``query``, because the webhook system supplies
the operation around it; whitespace is collapsed so it drops into a JSON config
string.

Internal: the webhook is configured in an external system, so this is a
setup-time artifact (see ``docs/webhooks.md``), not a runtime API. A drift-guard
test snapshots it so the documented string can't silently rot.
"""


def parse_booking_webhook(payload: Any) -> Booking:
    """Parses a delivered booking webhook payload into a clean :class:`Booking`.

    Accepts the raw request body — either the ``{"booking": …}`` envelope or a
    bare booking node, and a JSON string is parsed first. Which optional field
    groups are present is auto-detected from the payload, so there is nothing to
    keep in sync with the registered query. Never raises on malformed input — it
    yields an empty-ish booking instead.
    """
    node = _extract_booking_node(payload)
    return from_booking_node(node, _has_guests(node), _has_price_breakdown(node))


def _extract_booking_node(payload: Any) -> Mapping[str, Any]:
    """Narrows the raw request body down to the booking node, tolerating both shapes."""
    body = payload
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {}
    if not isinstance(body, Mapping):
        return {}
    inner = body.get(_PAYLOAD_BOOKING_KEY)
    if isinstance(inner, Mapping):
        return inner
    return body


def _has_guests(node: Mapping[str, Any]) -> bool:
    return isinstance(node.get(_BOOKING_GUESTS_KEY), list)


def _has_price_breakdown(node: Mapping[str, Any]) -> bool:
    value = node.get(_VALUE_KEY)
    if not isinstance(value, Mapping):
        return False
    return any(key in value for key in _PRICE_BREAKDOWN_KEYS)
