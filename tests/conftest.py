"""Shared pytest fixtures and fakes.

Tests never hit the network. Two fakes cover every service test:

- :func:`mock_http_client` builds an :class:`httpx.AsyncClient` over an
  :class:`httpx.MockTransport` (the Python analogue of injecting a fake
  ``fetch``), for transport/client tests.
- :class:`FakeGraphQLClient` stands in for ``GraphQLClient`` in resource-service
  tests: it records every ``(endpoint_name, query, variables)`` call and replays
  queued responses (a ``{"data": ...}`` body, or an exception to raise).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from peek_app_utilities.logger import LogContext, Logger

Handler = Callable[[httpx.Request], httpx.Response]


def mock_http_client(handler: Handler) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` whose every request is answered by ``handler``."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def json_response(status_code: int, body: Any) -> httpx.Response:
    return httpx.Response(status_code, json=body)


def text_response(status_code: int, text: str) -> httpx.Response:
    return httpx.Response(status_code, text=text)


def request_json(request: httpx.Request) -> Any:
    """The decoded JSON body of a captured request."""
    return json.loads(request.content.decode("utf-8"))


async def no_sleep(_seconds: float) -> None:
    """Drop-in ``sleep`` for retry tests."""
    return None


@dataclass
class RecordingLogger:
    """A :class:`Logger` that records ``(level, message, context)`` tuples."""

    entries: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def info(self, message: str, context: LogContext | None = None) -> None:
        self.entries.append(("info", message, dict(context or {})))

    def warn(self, message: str, context: LogContext | None = None) -> None:
        self.entries.append(("warn", message, dict(context or {})))

    def error(self, message: str, context: LogContext | None = None) -> None:
        self.entries.append(("error", message, dict(context or {})))

    def messages(self, level: str) -> list[str]:
        return [m for lvl, m, _ in self.entries if lvl == level]


@dataclass
class RecordedCall:
    endpoint_name: str
    query: str
    variables: dict[str, Any]


class FakeGraphQLClient:
    """Stands in for ``GraphQLClient`` in service tests.

    Queue responses with :meth:`queue` (a ``data`` payload, wrapped as
    ``{"data": data}``) or :meth:`queue_error` (an exception to raise). Each
    ``request`` pops the next one in order; running out raises
    ``AssertionError``. Every call is recorded on :attr:`calls`.
    """

    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self._responses: list[Any] = []

    def queue(self, data: Any) -> FakeGraphQLClient:
        self._responses.append({"data": data})
        return self

    def queue_body(self, body: Mapping[str, Any]) -> FakeGraphQLClient:
        """Queue a raw body (e.g. one without ``data``)."""
        self._responses.append(dict(body))
        return self

    def queue_error(self, error: Exception) -> FakeGraphQLClient:
        self._responses.append(error)
        return self

    async def request(
        self, endpoint_name: str, query: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(RecordedCall(endpoint_name, query, dict(variables)))
        if not self._responses:
            raise AssertionError(f"FakeGraphQLClient: no response queued for {endpoint_name}")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return dict(response)

    @property
    def last_call(self) -> RecordedCall:
        assert self.calls, "FakeGraphQLClient: no calls recorded"
        return self.calls[-1]


@pytest.fixture
def gql() -> FakeGraphQLClient:
    return FakeGraphQLClient()


@pytest.fixture
def recording_logger() -> RecordingLogger:
    return RecordingLogger()


__all__ = [
    "FakeGraphQLClient",
    "Logger",
    "RecordedCall",
    "RecordingLogger",
    "json_response",
    "mock_http_client",
    "no_sleep",
    "request_json",
    "text_response",
]
