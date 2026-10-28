"""Shared verification core for the ``app_registry_v2`` JWT family.

Every token Peek's app registry mints — the per-session **peek-auth token**
(``PeekAccessService.verify_peek_auth_token``) and the **install-status webhook
token** (``parse_install_webhook``) — is signed with the app's HMAC secret and
carries the same ``issuer``/``audience`` and the same snake_case ``user`` block.
This module owns those shared constants and the signature check so the entry
points can't drift apart.

Internal only — never re-exported from the package root.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

import jwt

from peek_app_utilities.models.peek.auth_token import (
    PEEK_PLATFORMS,
    PeekAuthTokenUser,
    PeekPlatform,
)

PEEK_TOKEN_ISSUER: Final = "app_registry_v2"
"""JWT issuer set by the Peek app registry on all tokens it issues."""
PEEK_TOKEN_AUDIENCE: Final = "Joken"
"""JWT audience set by the Peek app registry on all tokens it issues."""
_BEARER_PREFIX: Final = "bearer "
_ALGORITHMS: Final = ("HS256", "HS384", "HS512")
_NULLISH_STRINGS: Final = frozenset({"", "null"})

RawPeekTokenUser = Mapping[str, Any]
"""The raw, snake_case ``user`` block of an ``app_registry_v2`` token. Every
field is optional/nullable — untrusted input."""


def strip_bearer(token: str) -> str:
    """Strips a leading ``Bearer `` prefix (case-insensitive) so every caller can
    pass the raw ``x-peek-auth`` request header value straight through."""
    trimmed = token.strip()
    if trimmed.lower().startswith(_BEARER_PREFIX):
        return trimmed[len(_BEARER_PREFIX) :].strip()
    return trimmed


def clean_token_string(value: Any) -> str | None:
    """Normalizes an untrusted string claim: trims it, then collapses an empty
    string or the literal ``"null"`` (case-insensitive) — both of which Peek has
    been seen to send for an absent value — to ``None``. A non-string also
    becomes ``None``."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return None if trimmed.lower() in _NULLISH_STRINGS else trimmed


def clean_token_platform(value: Any) -> PeekPlatform | None:
    """Narrows an untrusted platform claim to a known :data:`PeekPlatform`, else ``None``."""
    cleaned = clean_token_string(value)
    if cleaned is not None and cleaned in PEEK_PLATFORMS:
        return cast("PeekPlatform", cleaned)
    return None


def verify_peek_jwt(token: str, secret: str) -> dict[str, Any]:
    """Verifies an ``app_registry_v2`` token's HMAC signature, expiry, issuer and
    ``Joken`` audience, returning the decoded payload.

    Raises :class:`jwt.InvalidTokenError` subclasses from PyJWT on any failure
    (``ExpiredSignatureError``, ``InvalidSignatureError``, ``InvalidIssuerError``,
    ``InvalidAudienceError``, ``ImmatureSignatureError``, ``DecodeError``).

    The ``token`` argument accepts the raw ``x-peek-auth`` header value: a
    leading ``Bearer `` scheme prefix is stripped before verification.
    """
    payload = jwt.decode(
        strip_bearer(token),
        secret,
        algorithms=list(_ALGORITHMS),
        issuer=PEEK_TOKEN_ISSUER,
        audience=PEEK_TOKEN_AUDIENCE,
    )
    return payload


def map_peek_token_user(raw: RawPeekTokenUser | None) -> PeekAuthTokenUser | None:
    """Maps the raw snake_case user block to the clean :class:`PeekAuthTokenUser`.

    An absent block yields ``None``; a present block yields a user whose every
    field is independently nullable (garbage strings normalized to ``None`` via
    :func:`clean_token_string`). Never raises.
    """
    if not raw or not isinstance(raw, Mapping):
        return None
    is_admin = raw.get("is_admin")
    return PeekAuthTokenUser(
        email=clean_token_string(raw.get("email")),
        id=clean_token_string(raw.get("id")),
        is_admin=is_admin if isinstance(is_admin, bool) else None,
        locale=clean_token_string(raw.get("locale")),
        name=clean_token_string(raw.get("name")),
        platform=clean_token_platform(raw.get("platform")),
    )
