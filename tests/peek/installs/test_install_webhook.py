import dataclasses
import json
import time
from typing import Any

import jwt
import pytest

from peek_app_utilities.errors import InstallWebhookError
from peek_app_utilities.internal.peek.installs.install_webhook import parse_install_webhook
from peek_app_utilities.models.peek.auth_token import PeekAuthTokenUser
from peek_app_utilities.models.peek.install import InstallWebhook

SECRET = "install-webhook-secret"
ISSUER = "app_registry_v2"
AUDIENCE = "Joken"
INSTALL_ID = "8c1f32b4-ab3c-4e20-82b7-844ea9e03bc9"
ACCOUNT_ID = "acct_42"
OTHER_INSTALL_ID = "cf34832d-16ea-4197-86fd-bf63e6917348"
BODY_ACCOUNT_ID = "4b52e9d2-7411-4d47-9100-71bebb55d151"
API_URL = "https://app-registry.sandbox.peeklabs.com/installations-api/demo"

SAMPLE_USER = {
    "email": "admin@peek.com",
    "id": "u_1",
    "is_admin": True,
    "locale": "en",
    "name": "Admin User",
    "platform": "peek",
}
SAMPLE_MODIFIED_BY = {
    "email": "oskar@peek.com",
    "id": "u_body",
    "is_admin": False,
    "locale": "en",
    "name": "Oskar",
    "platform": "peek",
}
TOKEN_USER = PeekAuthTokenUser(
    email="admin@peek.com", id="u_1", is_admin=True, locale="en", name="Admin User", platform="peek"
)


def mint(secret: str = SECRET, overrides: dict[str, Any] | None = None, **sign: Any) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "display_version": "1.2.3",
        "status": "installed",
        "account": {"id": ACCOUNT_ID},
        "user": SAMPLE_USER,
        "sub": INSTALL_ID,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": now + 60,
    }
    payload.update(overrides or {})
    payload.update(sign)
    return jwt.encode(payload, secret, algorithm="HS256")


def build_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "status": "installed",
        "install_id": INSTALL_ID,
        "display_version": "1.0.3",
        "api": {"url": API_URL},
        "account": {
            "id": BODY_ACCOUNT_ID,
            "name": "Oskar's Boat Tours",
            "timezone": "America/New_York",
            "is_test": True,
            "platform": "peek",
        },
    }
    body.update(overrides)
    return body


def test_merges_the_verified_token_and_the_json_body_into_one_flat_event():
    event = parse_install_webhook(mint(), build_body(), SECRET)
    assert event == InstallWebhook(
        install_id=INSTALL_ID,
        account_id=BODY_ACCOUNT_ID,
        account_name="Oskar's Boat Tours",
        platform="peek",
        is_test=True,
        timezone="America/New_York",
        api_url=API_URL,
        status="installed",
        raw_status="installed",
        display_version="1.0.3",
        user=TOKEN_USER,
    )


def test_takes_account_status_and_version_from_the_body_not_the_token():
    token = mint(
        overrides={
            "status": "uninstalled",
            "account": {"id": "token-account-id"},
            "display_version": "9.9.9",
        }
    )
    event = parse_install_webhook(token, build_body(), SECRET)
    assert event.install_id == INSTALL_ID
    assert event.account_id == BODY_ACCOUNT_ID
    assert event.status == "installed"
    assert event.display_version == "1.0.3"


def test_takes_install_id_from_the_token_sub_when_the_body_matches_or_omits_it():
    assert (
        parse_install_webhook(mint(), build_body(install_id=INSTALL_ID), SECRET).install_id
        == INSTALL_ID
    )
    assert (
        parse_install_webhook(mint(), build_body(install_id=None), SECRET).install_id == INSTALL_ID
    )
    assert parse_install_webhook(mint(), build_body(install_id=""), SECRET).install_id == INSTALL_ID


def test_raises_install_webhook_error_when_the_body_install_id_is_not_the_token_sub():
    with pytest.raises(InstallWebhookError) as info:
        parse_install_webhook(mint(), build_body(install_id=OTHER_INSTALL_ID), SECRET)
    assert info.value.reason == "install_id_mismatch"
    assert isinstance(info.value, jwt.InvalidTokenError)
    assert "install_id does not match" in str(info.value)


def test_raises_when_the_body_install_id_differs_only_in_case():
    with pytest.raises(InstallWebhookError):
        parse_install_webhook(mint(), build_body(install_id=INSTALL_ID.upper()), SECRET)


@pytest.mark.parametrize(
    "url",
    [
        "https://apps.peek.com/installations-api/app-1",
        "https://registry.apps.peek.com/apis",
        "https://peek.com/installations-api/app-1",
        "https://app-registry.sandbox.peeklabs.com/installations-api/demo",
        "https://APPS.PEEK.COM/installations-api/app-1",
        "registry.apps.peek.com/apis",
    ],
)
def test_accepts_an_api_url_on_a_peek_owned_host(url: str):
    assert parse_install_webhook(mint(), build_body(api={"url": url}), SECRET).api_url == url


@pytest.mark.parametrize(
    "url",
    [
        "https://registry.hackerdomain.com/api",
        "https://registry.hackerdomain.com/peek.com",
        "https://peek.com.evil.com/api",
        "https://peek.com@evil.com/api",
        "https://notpeek.com/api",
        "registry.hackerdomain.com/api",
        "::::",
        "https://[::1/api",
    ],
)
def test_raises_install_webhook_error_on_a_foreign_api_url(url: str):
    with pytest.raises(InstallWebhookError) as info:
        parse_install_webhook(mint(), build_body(api={"url": url}), SECRET)
    assert info.value.reason == "invalid_api_url"
    assert "Peek-owned domain" in str(info.value)


def test_does_not_validate_an_absent_api_url():
    assert parse_install_webhook(mint(), build_body(api=None), SECRET).api_url == ""


def test_falls_back_to_the_token_for_fields_the_body_omits():
    body = build_body(install_id=None, display_version=None, status=None)
    body["account"] = {"name": "Oskar's Boat Tours"}
    event = parse_install_webhook(mint(), body, SECRET)
    assert event.install_id == INSTALL_ID
    assert event.account_id == ACCOUNT_ID
    assert event.status == "installed"
    assert event.display_version == "1.2.3"


def test_reads_timezone_and_api_url_from_the_body():
    event = parse_install_webhook(mint(), build_body(), SECRET)
    assert event.timezone == "America/New_York"
    assert event.api_url == API_URL


def test_defaults_timezone_and_api_url_when_the_body_omits_them():
    event = parse_install_webhook(mint(), build_body(api=None, account={"id": "x"}), SECRET)
    assert event.timezone == ""
    assert event.api_url == ""


def test_prefers_the_bodys_modified_by_for_the_acting_user():
    event = parse_install_webhook(mint(), build_body(modified_by=SAMPLE_MODIFIED_BY), SECRET)
    assert event.user == PeekAuthTokenUser(
        email="oskar@peek.com",
        id="u_body",
        is_admin=False,
        locale="en",
        name="Oskar",
        platform="peek",
    )


def test_falls_back_to_the_token_user_when_the_body_has_no_modified_by():
    assert parse_install_webhook(mint(), build_body(), SECRET).user.id == "u_1"


def test_ignores_a_modified_by_without_an_id():
    event = parse_install_webhook(mint(), build_body(modified_by={"name": "No Id"}), SECRET)
    assert event.user.id == "u_1"


def test_accepts_the_body_as_a_json_string():
    event = parse_install_webhook(mint(), json.dumps(build_body()), SECRET)
    assert event.account_name == "Oskar's Boat Tours"
    assert event.is_test is True


def test_tolerates_a_null_user():
    event = parse_install_webhook(
        mint(overrides={"user": None}), build_body(status="uninstalled"), SECRET
    )
    assert event.user is None
    assert event.status == "uninstalled"


def test_defaults_body_only_fields_when_the_body_is_missing_entirely():
    event = parse_install_webhook(mint(), None, SECRET)
    assert event.install_id == INSTALL_ID
    assert event.account_id == ACCOUNT_ID
    assert event.account_name == ""
    assert event.platform is None
    assert event.is_test is False
    assert event.timezone == ""
    assert event.api_url == ""


def test_defaults_is_test_to_false_when_the_account_omits_it():
    body = build_body(account={"id": "x", "name": "Acme", "platform": "peek"})
    assert parse_install_webhook(mint(), body, SECRET).is_test is False


@pytest.mark.parametrize("platform", ["cng", "acme"])
def test_recognises_other_platforms(platform: str):
    body = build_body(account={"id": "x", "name": "Acme", "platform": platform})
    assert parse_install_webhook(mint(), body, SECRET).platform == platform


def test_surfaces_an_unknown_platform_as_none():
    body = build_body(account={"id": "x", "name": "Acme", "platform": "newbrand"})
    assert parse_install_webhook(mint(), body, SECRET).platform is None


def test_surfaces_an_unknown_status_as_none_and_preserves_the_wire_value():
    event = parse_install_webhook(mint(), build_body(status="suspended"), SECRET)
    assert event.status is None
    assert event.raw_status == "suspended"


def test_returns_an_event_that_round_trips_through_json_unchanged():
    event = parse_install_webhook(mint(), build_body(), SECRET)
    as_dict = dataclasses.asdict(event)
    assert json.loads(json.dumps(as_dict)) == as_dict


def test_raises_on_an_invalid_token_before_touching_the_body():
    with pytest.raises(jwt.InvalidTokenError):
        parse_install_webhook(mint(secret="wrong-secret"), build_body(), SECRET)


def test_accepts_the_raw_x_peek_auth_header_value_with_a_bearer_prefix():
    token = mint()
    for header in (f"Bearer {token}", f"bearer {token}", f"  {token}  "):
        assert parse_install_webhook(header, build_body(), SECRET).install_id == INSTALL_ID


def test_raises_install_webhook_error_when_the_verified_token_has_no_sub():
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60}, SECRET, algorithm="HS256"
    )
    with pytest.raises(InstallWebhookError) as info:
        parse_install_webhook(token, build_body(), SECRET)
    assert info.value.reason == "missing_subject"


@pytest.mark.parametrize("subject", ["   ", "null"])
def test_raises_when_the_token_sub_is_a_sentinel(subject: str):
    with pytest.raises(InstallWebhookError) as info:
        parse_install_webhook(mint(sub=subject), build_body(), SECRET)
    assert info.value.reason == "missing_subject"


def test_defaults_every_other_field_to_empty_when_the_token_carries_only_a_sub():
    token = jwt.encode(
        {"sub": INSTALL_ID, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60},
        SECRET,
        algorithm="HS256",
    )
    event = parse_install_webhook(token, None, SECRET)
    assert event == InstallWebhook(
        install_id=INSTALL_ID,
        account_id="",
        account_name="",
        platform=None,
        is_test=False,
        timezone="",
        api_url="",
        status=None,
        raw_status="",
        display_version="",
        user=None,
    )


def test_non_mapping_account_and_api_blocks_are_ignored():
    event = parse_install_webhook(mint(), build_body(account="junk", api=["x"]), SECRET)
    assert event.account_id == ACCOUNT_ID
    assert event.api_url == ""


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"iss": "wrong-issuer"}, jwt.InvalidIssuerError),
        ({"aud": "wrong-audience"}, jwt.InvalidAudienceError),
        ({"exp": int(time.time()) - 1}, jwt.ExpiredSignatureError),
    ],
)
def test_rejects_wrong_issuer_audience_or_expired(kwargs: dict[str, Any], error: type[Exception]):
    with pytest.raises(error):
        parse_install_webhook(mint(**kwargs), build_body(), SECRET)


def test_rejects_a_malformed_token_string():
    with pytest.raises(jwt.InvalidTokenError):
        parse_install_webhook("not.a.jwt", build_body(), SECRET)
