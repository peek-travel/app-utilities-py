"""Claims carried by the ``app_registry_v2`` JWT family — the per-session
peek-auth token and the install-webhook token."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

PEEK_PLATFORMS: Final[tuple[str, ...]] = ("peek", "cng", "acme")
"""Every platform this package knows about. Exported as a value so runtime code
can recognise a reported platform without restating the list."""

PeekPlatform = Literal["peek", "cng", "acme"]
"""Platform that embedded the app for this session. One peek-auth JWT is minted
for every platform, so this claim is what identifies the originating platform."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PeekAuthTokenUser:
    """User context embedded in a Peek auth token.

    Every field is nullable: the token is untrusted even after its signature
    verifies, so a claim may be absent, ``None``, or a sentinel (``""``,
    ``"null"``) that this package normalizes to ``None``.
    """

    email: str | None
    """User's email address, or ``None`` if the token omits it."""
    id: str | None
    """The user's own Peek user ID — the signed-in person, **not** the account or
    partner they belong to. ``None`` when the token omits it."""
    is_admin: bool | None
    """Whether the user has admin privileges, or ``None`` if the token omits it."""
    locale: str | None
    """User's locale (e.g. ``"en"``), or ``None`` if the token omits it."""
    name: str | None
    """User's display name, or ``None`` if the token omits it."""
    platform: PeekPlatform | None
    """Which platform embedded the app for this session, or ``None`` when the
    token omits it or reports one this package does not recognize."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PeekAuthTokenClaims:
    """Claims returned by ``PeekAccessService.verify_peek_auth_token``."""

    install_id: str
    """Install ID — the JWT subject (``sub``). Peek-assigned UUID."""
    display_version: str
    """App display version at time of issuance."""
    user: PeekAuthTokenUser | None
    """Authenticated user context, or ``None`` when the token carries no ``user``
    block. Do not assume a session token always names a user."""
