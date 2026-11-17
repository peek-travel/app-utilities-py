"""Public webhook surface for waivers.

Unlike bookings, a waiver webhook needs **no registration query** — Peek
delivers a fixed payload (the App Store ``waiver_webhook_data`` output format),
so there is nothing to register beyond subscribing to the
``agreement_signature_created`` event. The package's only job is to parse the
delivered payload into a clean :class:`Waiver`.

Like the booking parser, this is a pure transform — no auth, no network, no
client — so it is a standalone function rather than a method on
``PeekAccessService`` (the receiver may not hold API credentials).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final, TypedDict

from peek_app_utilities.access_options import AccessOptions, resolve_access_options
from peek_app_utilities.models.peek.waiver import Waiver

PAYLOAD_WAIVER_KEY: Final = "waiver"
"""The envelope key the webhook delivery wraps the waiver node under."""
REDACTED_FILE_URL: Final = ""
"""What :attr:`Waiver.file_url` is set to when PII is not enabled."""


class WaiverDataNode(TypedDict, total=False):
    participant_name: str | None
    participant_optin_marketing: bool | None
    participant_optin_sms: bool | None


class WaiverNode(TypedDict, total=False):
    """Raw, snake_case waiver payload as delivered by the webhook. Internal."""

    agreement_template_id: str | None
    booking_id: str | None
    file_url: str | None
    signed_at: str | None
    signed_by_guardian: bool | None
    waiver_data: WaiverDataNode | None


def parse_waiver_webhook(payload: Any, options: AccessOptions | None = None) -> Waiver:
    """Parses a delivered waiver webhook payload into a clean :class:`Waiver`.

    Accepts the raw request body — either the ``{"waiver": …}`` envelope or a
    bare waiver node, and a JSON string is parsed first. Never raises on
    malformed input: a missing/garbled body yields a :class:`Waiver` with empty
    fields.

    Because a waiver webhook has no selection to trim (Peek delivers a fixed
    payload), the PII fields — the participant ``guest_name`` and the signed
    document ``file_url`` — are instead redacted here at parse time when
    ``options`` does not enable PII. Pass
    ``AccessOptions(full_customer_access=True)`` to keep them.
    """
    waiver = from_waiver_node(_extract_waiver_node(payload))
    if not resolve_access_options(options).full_customer_access:
        return replace(waiver, guest_name=None, file_url=REDACTED_FILE_URL)
    return waiver


def from_waiver_node(node: Mapping[str, Any] | None) -> Waiver:
    """Pure mapping of a raw waiver node into the clean :class:`Waiver` model."""
    data: Mapping[str, Any] = node or {}
    waiver_data: Mapping[str, Any] = data.get("waiver_data") or {}
    return Waiver(
        template_id=data.get("agreement_template_id") or "",
        booking_id=data.get("booking_id") or "",
        file_url=data.get("file_url") or "",
        signed_at=data.get("signed_at") or "",
        is_signed_by_guardian=bool(data.get("signed_by_guardian")),
        guest_name=waiver_data.get("participant_name") or None,
        is_optin_marketing=bool(waiver_data.get("participant_optin_marketing")),
        is_optin_sms=bool(waiver_data.get("participant_optin_sms")),
    )


def _extract_waiver_node(payload: Any) -> Mapping[str, Any]:
    """Narrows the raw request body down to the waiver node, tolerating both shapes."""
    body = payload
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {}
    if not isinstance(body, Mapping):
        return {}
    inner = body.get(PAYLOAD_WAIVER_KEY)
    if isinstance(inner, Mapping):
        return inner
    return body
