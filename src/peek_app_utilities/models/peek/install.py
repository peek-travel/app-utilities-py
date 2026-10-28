"""The clean data model for an app-store **install lifecycle event** — the single
flat object :func:`parse_install_webhook` returns for the webhook Peek's app
registry POSTs when an app is installed, uninstalled, or updated.

That delivery carries two things at once: a **signed ``app_registry_v2`` JWT**
(the security boundary) and a plain **JSON body** (the event payload).
``parse_install_webhook`` verifies the JWT and merges both into this shape. The
**JSON body is the source of the event data**; the verified JWT authenticates
the delivery and acts as the **fallback** for the fields it also carries
(``install_id``, ``account_id``, ``status``, ``display_version``, ``user``).

**Every install event is a full snapshot — upsert by ``install_id``.** An
``update_installed`` event carries the same complete record as the original
``installed`` event, so treat each delivery as an upsert and overwrite the
stored fields (e.g. a new ``api_url``) with the incoming ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from peek_app_utilities.models.peek.auth_token import PeekAuthTokenUser, PeekPlatform

INSTALL_STATUSES: Final[tuple[str, ...]] = ("installed", "uninstalled", "update_installed")
"""Every install lifecycle status Peek's app registry sends today."""

InstallStatus = Literal["installed", "uninstalled", "update_installed"]
"""Install lifecycle status."""


@dataclass(frozen=True, slots=True, kw_only=True)
class InstallWebhook:
    """A verified install lifecycle event as one flat, JSON-safe record.

    Flat by design: it round-trips through a datastore unchanged, so the shape
    the parser returns is the shape a consumer persists and later rehydrates.
    """

    install_id: str
    """Install ID — Peek-assigned UUID. Also the JWT subject (``sub``)."""
    account_id: str
    """Stable Peek account id — the same value Peek calls the **partner ID**.
    This event is its only source; it cannot be re-fetched later."""
    account_name: str
    """Partner display name. ``""`` when the JSON body omits it."""
    platform: PeekPlatform | None
    """Which Peek platform owns the install, or ``None`` when the registry reported
    a platform this version of the package does not know. **Persist and track
    this per install** — it decides which access service to construct
    (``PeekAccessService`` / ``CngAccessService`` / ``AcmeAccessService``)."""
    is_test: bool
    """Whether this is a test account. ``False`` when not reported."""
    timezone: str
    """The account's IANA timezone (e.g. ``"America/New_York"``), or ``""``.
    **Persist this per install** — it has no other source."""
    api_url: str
    """The **app endpoint URL** the registry serves this install from, or ``""``.
    Use it as given as the base URL for this install's API calls. **Persist it
    per install and refresh it on every install event.**"""
    status: InstallStatus | None
    """The lifecycle status, or ``None`` when the registry sent one this version
    does not know. Handle ``None`` explicitly — a no-op silently drops a
    lifecycle transition."""
    raw_status: str
    """The status exactly as delivered, for logging and for the ``None`` case."""
    display_version: str
    """App display version at the time of the event."""
    user: PeekAuthTokenUser | None
    """The user that triggered the event, or ``None`` for system-initiated events.
    Read from the body's ``modified_by``, falling back to the JWT's ``user``."""
