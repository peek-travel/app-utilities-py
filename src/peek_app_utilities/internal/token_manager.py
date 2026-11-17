"""Mints and caches the short-lived JWT used to authenticate with the Peek
platform APIs. The token is signed on demand and reused until it nears expiry.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import jwt

_ALGORITHM: Final = "HS256"


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenManagerOptions:
    secret: str
    """HMAC secret used to sign the JWT."""
    issuer: str
    """JWT issuer (the app name)."""
    install_id: str
    """JWT subject (the install ID)."""
    ttl_seconds: int
    """Token lifetime in seconds."""
    leeway_seconds: int
    """Re-mint the cached token this many seconds before its expiry."""


class TokenManager:
    """Signs a short-lived HS256 JWT (``sub`` = install id, ``iss`` = issuer,
    empty payload otherwise) and caches it until it is within
    ``leeway_seconds`` of expiry."""

    def __init__(
        self,
        options: TokenManagerOptions,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._options = options
        self._clock = clock
        self._cached: tuple[str, float] | None = None

    def get_token(self) -> str:
        """Returns a valid bearer token, reusing the cached one until it is
        within ``leeway_seconds`` of expiring, at which point a fresh token is
        minted."""
        now = self._clock()
        if self._cached is not None and now < self._cached[1]:
            return self._cached[0]

        opts = self._options
        issued_at = int(now)
        token = jwt.encode(
            {
                "iat": issued_at,
                "exp": issued_at + opts.ttl_seconds,
                "iss": opts.issuer,
                "sub": opts.install_id,
            },
            opts.secret,
            algorithm=_ALGORITHM,
        )
        self._cached = (token, now + (opts.ttl_seconds - opts.leeway_seconds))
        return token
