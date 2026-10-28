"""Shared HTTP transport core for every platform client (Peek GraphQL, CNG REST,
ACME REST).

The retry/backoff loop and the 418/429 status mapping are identical across the
platforms — only URL construction, request method/body, and success-body
handling differ. Those differences are supplied by the caller: it builds the
request, and its ``on_response`` callback runs for every non-418/429 status to
produce the final value (or raise a platform-specific error).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx

from peek_app_utilities.errors import (
    ADMIN_ACCOUNT_REQUIRED_STATUS,
    RATE_LIMIT_STATUS,
    AdminAccountRequiredError,
    RateLimitError,
)
from peek_app_utilities.logger import Logger

T = TypeVar("T")

SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class HttpRetryOptions:
    """The subset of client options the shared retry loop needs."""

    retry_delays_ms: Sequence[int]
    """Backoff delays (ms) applied on successive HTTP 429 responses."""
    logger: Logger
    """Diagnostics sink."""
    http_client: httpx.AsyncClient
    """The HTTP client to send requests through (injectable for tests)."""
    sleep: SleepFn = asyncio.sleep
    """Sleep implementation used between retries (injectable for tests)."""


def parse_body(response: httpx.Response) -> Any:
    """Reads a response body as JSON, falling back to the raw text when it is not
    valid JSON. Never raises — a non-JSON error page (e.g. a ``404`` with a
    plain-text body) is returned verbatim as a string rather than blowing up the
    caller with a decode error that hides the real HTTP status."""
    text = response.text
    try:
        return json.loads(text)
    except ValueError:
        return text


async def request_with_retry(
    http: HttpRetryOptions,
    method: str,
    url: str,
    label: str,
    on_response: Callable[[httpx.Response], Awaitable[T]],
    *,
    headers: Mapping[str, str],
    json_body: Any | None = None,
) -> T:
    """Runs a request through the shared retry loop.

    Maps HTTP 418 → :class:`AdminAccountRequiredError` and HTTP 429 → retry then
    :class:`RateLimitError`; delegates every other response to ``on_response``.

    ``label`` is a short identifier for the request (endpoint name / REST path),
    used only in the warn/error log messages.
    """
    delays = list(http.retry_delays_ms)
    logger = http.logger

    for attempt in range(len(delays) + 1):
        response = await http.http_client.request(
            method, url, headers=dict(headers), json=json_body
        )

        if response.status_code == ADMIN_ACCOUNT_REQUIRED_STATUS:
            logger.warn(f"Admin account required for {label} (HTTP 418)", {"url": url})
            raise AdminAccountRequiredError()

        if response.status_code == RATE_LIMIT_STATUS:
            if attempt < len(delays):
                delay = delays[attempt]
                logger.warn(
                    f"Rate limited on {label}, retrying in {delay}ms "
                    f"(attempt {attempt + 1}/{len(delays)})"
                )
                await http.sleep(delay / 1000)
                continue
            logger.error(f"Rate limit exceeded for {label}", {"url": url})
            raise RateLimitError()

        return await on_response(response)

    raise RateLimitError()  # pragma: no cover - unreachable: the 429 branch always returns/raises
