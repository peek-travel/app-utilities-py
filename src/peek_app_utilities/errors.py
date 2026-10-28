"""Typed errors raised by the package.

Each mirrors a failure mode of the Peek backoffice API (or the CNG / ACME REST
APIs) so callers can branch on the exception type rather than parsing messages.

Every error derives from :class:`AppUtilitiesError`, so ``except
AppUtilitiesError`` catches anything this package raises on its own (token
verification failures come from ``PyJWT`` and are documented separately).

``AdminAccountRequiredError`` and ``RateLimitError`` are shared by all
platforms. ``PeekGraphQLError`` / ``PeekHttpError`` are Peek-only;
``CngApiError`` / ``CngPermissionError`` are CNG-only; ``AcmeApiError`` is
ACME-only.
"""

from __future__ import annotations

from typing import Any, Final

# The HTTP status the CNG gateway uses for a missing-permission rejection.
FORBIDDEN_STATUS: Final = 403
ADMIN_ACCOUNT_REQUIRED_STATUS: Final = 418
RATE_LIMIT_STATUS: Final = 429

_PERMISSION_MESSAGE_PREFIX: Final = (
    "CNG request forbidden: the app is missing the required permission"
)
_PERMISSION_MESSAGE_UNKNOWN: Final = (
    "CNG request forbidden: the app is missing a required permission"
)
_DEFAULT_ADMIN_MESSAGE: Final = "Admin account required"
_DEFAULT_RATE_LIMIT_MESSAGE: Final = "Rate limit exceeded"
_DEFAULT_GRAPHQL_MESSAGE: Final = "GraphQL request failed"


def _build_permission_message(permissions: list[str]) -> str:
    if not permissions:
        return _PERMISSION_MESSAGE_UNKNOWN
    plural = "s" if len(permissions) > 1 else ""
    return f"{_PERMISSION_MESSAGE_PREFIX}{plural}: {', '.join(permissions)}"


class AppUtilitiesError(Exception):
    """Base class for every error this package raises."""


class AdminAccountRequiredError(AppUtilitiesError):
    """HTTP 418: the install may not perform the request without an admin account."""

    status_code: Final = ADMIN_ACCOUNT_REQUIRED_STATUS

    def __init__(self, message: str = _DEFAULT_ADMIN_MESSAGE) -> None:
        super().__init__(message)


class RateLimitError(AppUtilitiesError):
    """HTTP 429 after every configured retry has been exhausted."""

    status_code: Final = RATE_LIMIT_STATUS

    def __init__(self, message: str = _DEFAULT_RATE_LIMIT_MESSAGE) -> None:
        super().__init__(message)


class PeekGraphQLError(AppUtilitiesError):
    """A GraphQL response carried an ``errors`` array.

    The raw errors are preserved on :attr:`graphql_errors` for inspection.
    """

    def __init__(self, graphql_errors: list[Any], message: str = _DEFAULT_GRAPHQL_MESSAGE) -> None:
        super().__init__(message)
        self.graphql_errors: list[Any] = graphql_errors


class PeekHttpError(AppUtilitiesError):
    """The Peek API returned a non-2xx response that is not 418/429 and carries
    no GraphQL ``errors`` array — a transport-level failure (401 wrong secret, 404
    wrong app id, 5xx, …) as opposed to :class:`PeekGraphQLError`.

    :attr:`status_code`, :attr:`url`, and the raw :attr:`body` (parsed JSON when
    possible, otherwise text) tell the caller which config is wrong.
    """

    def __init__(self, status_code: int, url: str, body: Any, message: str | None = None) -> None:
        super().__init__(message or f"Peek request failed with HTTP {status_code}")
        self.status_code = status_code
        self.url = url
        self.body = body


class PiiAccessDisabledError(AppUtilitiesError):
    """A payment / booking-modification operation was called on an access
    service constructed without ``full_customer_access``.

    These operations — pulling payment sources, charging/refunding, creating
    invoice links, adding/removing add-ons — touch customer financial data, so
    they are gated behind the same flag as customer PII. :attr:`operation` names
    the blocked method (e.g. ``"make_payment"``).
    """

    def __init__(self, operation: str) -> None:
        super().__init__(
            f'"{operation}" is disabled because this access service was created '
            'without "full_customer_access"; enable it to allow payment and '
            "booking-modification operations"
        )
        self.operation = operation


class CngApiError(AppUtilitiesError):
    """The CNG REST API returned a non-2xx response that is not 418/429/403."""

    def __init__(self, status_code: int, body: Any, message: str | None = None) -> None:
        super().__init__(message or f"CNG request failed with HTTP {status_code}")
        self.status_code = status_code
        self.body = body


class CngPermissionError(AppUtilitiesError):
    """HTTP 403 from the CNG REST API: the app lacks a permission the endpoint
    requires (e.g. ``products:read``).

    An **expected** failure for a misconfigured install — not a bug — so the
    transport logs it at ``warn`` rather than ``error``. The permission names the
    gateway reported are on :attr:`permissions` (empty when the body names none).
    """

    status_code: Final = FORBIDDEN_STATUS

    def __init__(self, permissions: list[str], body: Any, message: str | None = None) -> None:
        super().__init__(message or _build_permission_message(permissions))
        self.permissions = permissions
        self.body = body


class AcmeApiError(AppUtilitiesError):
    """The ACME REST API returned a non-2xx response that is not 418/429."""

    def __init__(self, status_code: int, body: Any, message: str | None = None) -> None:
        super().__init__(message or f"ACME request failed with HTTP {status_code}")
        self.status_code = status_code
        self.body = body
