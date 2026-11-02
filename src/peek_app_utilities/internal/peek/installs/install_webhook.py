"""Public webhook surface for install-status events.

Peek's app registry notifies your app of install lifecycle changes (installed,
uninstalled, status changed) with a single POST that carries **two** things at
once: a **signed ``app_registry_v2`` JWT** (delivered in the ``x-peek-auth``
request header) and a plain **JSON body**. The JWT is the security boundary —
verifying its signature is what authenticates that the notification really
came from Peek. The JSON body is the **event payload**: the full account block
(name, platform, timezone, test flag), the per-install ``api.url``, the acting
user, and the install id / status / version.

:func:`parse_install_webhook` verifies the token and reads the event from the
body, falling back to the token for the fields it also carries, returning one
flat :class:`InstallWebhook`.

This is a standalone function rather than a method on ``PeekAccessService``
because the receiver has no per-install service to inherit a secret from yet —
an install webhook can arrive before the first session, or describe an install
that is being torn down. The caller passes the app's signing secret directly.
"""

from __future__ import annotations

from typing import Any

from peek_app_utilities.internal.peek.installs.install_converter import (
    extract_install_webhook_body,
    to_install_status,
    to_peek_platform,
)
from peek_app_utilities.internal.peek.peek_auth_token import (
    RawPeekTokenUser,
    clean_token_string,
    map_peek_token_user,
    verify_peek_jwt,
)
from peek_app_utilities.models.peek.auth_token import PeekAuthTokenUser
from peek_app_utilities.models.peek.install import InstallWebhook


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def parse_install_webhook(token: str, body: Any, secret: str) -> InstallWebhook:
    """Verifies an install-status webhook token and merges it with the delivered
    JSON body into one flat :class:`InstallWebhook`.

    The **JSON body** is the source of the event data. The **verified token**
    authenticates the whole delivery and is the **fallback** for the fields it
    also carries (``install_id``, ``account_id``, ``status``, ``display_version``,
    ``user``) when the body omits them. A missing or malformed body degrades the
    body-only fields to ``""``/``None``/``False``; it never raises on shape.

    Signature verification is strict: the HMAC signature (with ``secret``), the
    expiry, the ``"app_registry_v2"`` issuer, and the ``"Joken"`` audience are all
    checked. Any failure raises a :class:`jwt.InvalidTokenError` subclass from
    PyJWT (``ExpiredSignatureError``, ``InvalidSignatureError``,
    ``InvalidIssuerError``, ``InvalidAudienceError``, ``DecodeError``, …).

    An unrecognised ``status`` or ``platform`` maps to ``None`` (with the wire
    status preserved on :attr:`InstallWebhook.raw_status`) rather than being
    coerced — handle a ``None`` status explicitly.

    :param token: the JWT delivered by the install webhook. Pass the raw
        ``x-peek-auth`` header value directly — a leading ``Bearer `` is stripped.
    :param body: the delivered JSON body (a mapping or a JSON string)
    :param secret: the app's HMAC signing secret (the ``jwt_secret`` you construct
        ``PeekAccessService`` with)
    """
    payload = verify_peek_jwt(token, secret)
    parsed = extract_install_webhook_body(body)
    account = _mapping_or_empty(parsed.get("account"))
    api = _mapping_or_empty(parsed.get("api"))
    token_account = _mapping_or_empty(payload.get("account"))
    # The JSON body is the source of the event data; the verified token is the
    # fallback. `or` so an empty body value falls through to the token.
    raw_status = str(parsed.get("status") or payload.get("status") or "")
    return InstallWebhook(
        install_id=str(parsed.get("install_id") or payload.get("sub") or ""),
        account_id=str(account.get("id") or token_account.get("id") or ""),
        account_name=str(account.get("name") or ""),
        platform=to_peek_platform(str(account.get("platform") or "")),
        is_test=bool(account.get("is_test")),
        timezone=str(account.get("timezone") or ""),
        api_url=str(api.get("url") or ""),
        status=to_install_status(raw_status),
        raw_status=raw_status,
        display_version=str(parsed.get("display_version") or payload.get("display_version") or ""),
        user=_resolve_install_user(parsed.get("modified_by"), payload.get("user")),
    )


def _resolve_install_user(
    body_user: RawPeekTokenUser | None, token_user: RawPeekTokenUser | None
) -> PeekAuthTokenUser | None:
    """Prefers the body's ``modified_by`` when it carries a *real* id; otherwise
    falls back to the token's ``user``. System events carry neither → ``None``."""
    body_id = body_user.get("id") if isinstance(body_user, dict) else None
    if clean_token_string(body_id) is not None:
        return map_peek_token_user(body_user)
    return map_peek_token_user(token_user if isinstance(token_user, dict) else None)
