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

import re
from typing import Any, Final
from urllib.parse import urlsplit

from peek_app_utilities.errors import (
    INSTALL_WEBHOOK_INSTALL_ID_MISMATCH,
    INSTALL_WEBHOOK_INVALID_API_URL,
    INSTALL_WEBHOOK_MISSING_SUBJECT,
    InstallWebhookError,
)
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

ALLOWED_API_URL_DOMAINS: Final[tuple[str, ...]] = ("peek.com", "peeklabs.com")
"""The Peek-owned domains an install webhook's ``api_url`` may target: ``peek.com``
is the production registry, ``peeklabs.com`` the sandbox/staging registry. A
delivered ``api_url`` must have one of these as its host, or a subdomain of one,
so a spoofed webhook can't point the app at an attacker-controlled gateway."""

_URL_SCHEME_RE: Final = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_HTTPS_PREFIX: Final = "https://"


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def parse_install_webhook(token: str, body: Any, secret: str) -> InstallWebhook:
    """Verifies an install-status webhook token and merges it with the delivered
    JSON body into one flat :class:`InstallWebhook`.

    ``install_id`` is **always the token** ``sub``. The body ``install_id`` never
    sets it: a body carrying a non-empty ``install_id`` that is not equal to
    ``sub`` raises :class:`InstallWebhookError` (``reason="install_id_mismatch"``);
    a verified token with no usable ``sub`` raises it with
    ``reason="missing_subject"``. A body without ``install_id`` parses normally.

    The **JSON body** is the source of the other event data. The **verified
    token** is the **fallback** for the fields it also carries (``account_id``,
    ``status``, ``display_version``, ``user``) when the body omits them. A missing
    or malformed body degrades the body-only fields to ``""``/``None``/``False``.

    A non-empty body ``api_url`` must point at a Peek-owned domain (``peek.com``
    or ``peeklabs.com``, or a subdomain of either); a value without a scheme is
    treated as ``https``. Anything else raises :class:`InstallWebhookError`
    (``reason="invalid_api_url"``). An absent ``api_url`` is not validated.

    Signature verification is strict: the HMAC signature (with ``secret``), the
    expiry, the ``"app_registry_v2"`` issuer, and the ``"Joken"`` audience are all
    checked. Any failure raises a :class:`jwt.InvalidTokenError` subclass from
    PyJWT (``ExpiredSignatureError``, ``InvalidSignatureError``,
    ``InvalidIssuerError``, ``InvalidAudienceError``, ``DecodeError``, …).

    :class:`InstallWebhookError` subclasses :class:`jwt.InvalidTokenError`, so a
    handler that treats every failed token check as a rejected delivery
    (respond 401) covers it with no change.

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
    install_id = _resolve_install_id(payload.get("sub"), parsed.get("install_id"))
    account = _mapping_or_empty(parsed.get("account"))
    api = _mapping_or_empty(parsed.get("api"))
    token_account = _mapping_or_empty(payload.get("account"))
    # The JSON body is the source of the other event data; the verified token is
    # the fallback. `or` so an empty body value falls through to the token.
    raw_status = str(parsed.get("status") or payload.get("status") or "")
    api_url = str(api.get("url") or "")
    _assert_allowed_api_url(api_url)
    return InstallWebhook(
        install_id=install_id,
        account_id=str(account.get("id") or token_account.get("id") or ""),
        account_name=str(account.get("name") or ""),
        platform=to_peek_platform(str(account.get("platform") or "")),
        is_test=bool(account.get("is_test")),
        timezone=str(account.get("timezone") or ""),
        api_url=api_url,
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


def _resolve_install_id(raw_subject: Any, body_install_id: Any) -> str:
    """The install id from the verified token ``sub``. Raises
    :class:`InstallWebhookError` when the token has no usable ``sub`` (absent,
    non-string, blank, or ``"null"``), or when the body carries a non-empty
    ``install_id`` that is not equal to it."""
    token_subject = clean_token_string(raw_subject)
    if token_subject is None:
        raise InstallWebhookError(INSTALL_WEBHOOK_MISSING_SUBJECT)
    if body_install_id and body_install_id != token_subject:
        raise InstallWebhookError(INSTALL_WEBHOOK_INSTALL_ID_MISMATCH)
    return token_subject


def _assert_allowed_api_url(api_url: str) -> None:
    """Rejects a delivery whose ``api_url`` targets a host outside
    :data:`ALLOWED_API_URL_DOMAINS`. An empty ``api_url`` is left alone — there
    is nothing to point the app at, so nothing to validate."""
    if not api_url:
        return
    host = _api_url_host(api_url)
    if host is None or not _is_allowed_api_url_host(host):
        raise InstallWebhookError(INSTALL_WEBHOOK_INVALID_API_URL)


def _api_url_host(api_url: str) -> str | None:
    """The host of ``api_url``, assuming ``https`` when no scheme is present.
    ``None`` when the value cannot be parsed as a URL with a host."""
    candidate = api_url if _URL_SCHEME_RE.match(api_url) else f"{_HTTPS_PREFIX}{api_url}"
    try:
        return urlsplit(candidate).hostname or None
    except ValueError:
        return None


def _is_allowed_api_url_host(host: str) -> bool:
    """Whether ``host`` is one of the allowed domains or a subdomain of one
    (case-insensitive). ``apps.peek.com`` and ``peek.com`` match;
    ``peek.com.evil.com`` and ``notpeek.com`` do not."""
    lower = host.lower()
    return any(lower == d or lower.endswith(f".{d}") for d in ALLOWED_API_URL_DOMAINS)
