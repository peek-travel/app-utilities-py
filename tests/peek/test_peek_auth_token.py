import time

import jwt
import pytest

from peek_app_utilities.internal.peek.peek_auth_token import (
    PEEK_TOKEN_AUDIENCE,
    PEEK_TOKEN_ISSUER,
    clean_token_platform,
    clean_token_string,
    map_peek_token_user,
    strip_bearer,
    verify_peek_jwt,
)
from peek_app_utilities.models.peek.auth_token import PeekAuthTokenUser

SECRET = "s3cret"


def mint(payload: dict, secret: str = SECRET, **claims: object) -> str:
    now = int(time.time())
    body = {"iss": PEEK_TOKEN_ISSUER, "aud": PEEK_TOKEN_AUDIENCE, "exp": now + 60, **payload}
    body.update(claims)
    return jwt.encode(body, secret, algorithm="HS256")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc", "abc"),
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("  BEARER   abc  ", "abc"),
        ("  abc  ", "abc"),
    ],
)
def test_strip_bearer(raw: str, expected: str):
    assert strip_bearer(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("x", "x"),
        ("  padded ", "padded"),
        ("", None),
        ("   ", None),
        ("null", None),
        ("NULL", None),
        (None, None),
        (42, None),
    ],
)
def test_clean_token_string(raw: object, expected: str | None):
    assert clean_token_string(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("peek", "peek"), ("cng", "cng"), ("acme", "acme"), ("Peek", None), ("", None), (None, None)],
)
def test_clean_token_platform(raw: object, expected: str | None):
    assert clean_token_platform(raw) == expected


def test_map_peek_token_user_returns_none_for_absent_block():
    assert map_peek_token_user(None) is None
    assert map_peek_token_user({}) is None
    assert map_peek_token_user("junk") is None  # type: ignore[arg-type]


def test_map_peek_token_user_normalizes_every_field():
    user = map_peek_token_user(
        {
            "email": " a@b.c ",
            "id": "null",
            "is_admin": "yes",
            "locale": "",
            "name": "Ann",
            "platform": "cng",
        }
    )
    assert user == PeekAuthTokenUser(
        email="a@b.c", id=None, is_admin=None, locale=None, name="Ann", platform="cng"
    )


def test_map_peek_token_user_keeps_boolean_is_admin():
    assert map_peek_token_user({"is_admin": False}).is_admin is False


def test_verify_peek_jwt_returns_payload_and_accepts_bearer_prefix():
    token = mint({"sub": "install-1"})
    assert verify_peek_jwt(token, SECRET)["sub"] == "install-1"
    assert verify_peek_jwt(f"Bearer {token}", SECRET)["sub"] == "install-1"


def test_verify_peek_jwt_rejects_wrong_secret_issuer_audience_expiry_and_garbage():
    with pytest.raises(jwt.InvalidSignatureError):
        verify_peek_jwt(mint({}, secret="other"), SECRET)
    with pytest.raises(jwt.InvalidIssuerError):
        verify_peek_jwt(mint({}, iss="wrong"), SECRET)
    with pytest.raises(jwt.InvalidAudienceError):
        verify_peek_jwt(mint({}, aud="wrong"), SECRET)
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_peek_jwt(mint({}, exp=int(time.time()) - 10), SECRET)
    with pytest.raises(jwt.InvalidTokenError):
        verify_peek_jwt("not.a.jwt", SECRET)
