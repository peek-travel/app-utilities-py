import time

import jwt

from peek_app_utilities.internal.token_manager import TokenManager, TokenManagerOptions

SECRET = "test-secret"
BASE = TokenManagerOptions(
    secret=SECRET,
    issuer="Peek Test App",
    install_id="install-123",
    ttl_seconds=3600,
    leeway_seconds=60,
)
START = float(int(time.time()))  # a fixed "now" for the fake clock


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_mints_a_verifiable_jwt_with_the_configured_issuer_and_subject():
    token = TokenManager(BASE, clock=FakeClock(START)).get_token()
    decoded = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="Peek Test App")

    assert decoded["iss"] == "Peek Test App"
    assert decoded["sub"] == "install-123"
    assert decoded["exp"] == decoded["iat"] + 3600


def test_reuses_the_cached_token_while_it_is_still_fresh():
    clock = FakeClock(START)
    manager = TokenManager(BASE, clock=clock)
    first = manager.get_token()

    clock.advance(60 * 30)  # well within (ttl - leeway)
    assert manager.get_token() == first


def test_re_mints_once_the_token_is_within_the_leeway_of_expiry():
    clock = FakeClock(START)
    manager = TokenManager(BASE, clock=clock)
    first = manager.get_token()

    clock.advance(3600 - 60 + 1)
    second = manager.get_token()

    assert second != first
    decoded = jwt.decode(second, SECRET, algorithms=["HS256"], options={"verify_iat": False})
    assert decoded["sub"] == "install-123"
