"""Pure, I/O-free helpers for the install webhook: narrowing an unknown request
body to the raw JSON mapping, and narrowing a delivered ``status``/``platform``
string to its known literal. No network, no logging, no clock.

Internal only — never re-exported from the package root.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from peek_app_utilities.models.peek.auth_token import PEEK_PLATFORMS, PeekPlatform
from peek_app_utilities.models.peek.install import INSTALL_STATUSES, InstallStatus

InstallWebhookBody = Mapping[str, Any]
"""The raw, snake_case JSON body delivered alongside the install webhook token:
``status``, ``install_id``, ``display_version``, ``account {id,name,platform,
timezone,is_test}``, ``api {url}``, ``modified_by {…user…}``. Any key may be
absent."""


def extract_install_webhook_body(payload: Any) -> InstallWebhookBody:
    """Narrows an unknown request body to a mapping, tolerating a JSON string
    (parsed first) and returning ``{}`` for anything non-object or unparseable,
    so the caller never has to guard."""
    body = payload
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {}
    if not isinstance(body, Mapping):
        return {}
    return body


def to_install_status(raw: str) -> InstallStatus | None:
    """Narrows a delivered status to :data:`InstallStatus`, or ``None`` when the
    registry sent one this version of the package does not know."""
    return cast("InstallStatus", raw) if raw in INSTALL_STATUSES else None


def to_peek_platform(raw: str) -> PeekPlatform | None:
    """Narrows a reported platform to :data:`PeekPlatform`, or ``None`` when the
    registry sent one this version of the package does not know."""
    return cast("PeekPlatform", raw) if raw in PEEK_PLATFORMS else None
