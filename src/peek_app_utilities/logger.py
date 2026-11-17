"""Minimal structured logger protocol the package writes diagnostics to.

Consumers may supply their own implementation (e.g. wrapping an existing
application logger). When none is provided the package stays completely silent
via :data:`noop_logger`. :func:`logging_adapter` wraps a standard-library
:class:`logging.Logger` so the common case is one line.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

LogContext = Mapping[str, Any]


@runtime_checkable
class Logger(Protocol):
    """Structured logger: a message plus an optional context mapping per level."""

    def info(self, message: str, context: LogContext | None = None) -> None: ...

    def warn(self, message: str, context: LogContext | None = None) -> None: ...

    def error(self, message: str, context: LogContext | None = None) -> None: ...


class _NoopLogger:
    """A :class:`Logger` that discards everything. Used as the default."""

    def info(self, message: str, context: LogContext | None = None) -> None:
        return None

    def warn(self, message: str, context: LogContext | None = None) -> None:
        return None

    def error(self, message: str, context: LogContext | None = None) -> None:
        return None


noop_logger: Logger = _NoopLogger()


class _StdlibLogger:
    """Adapts a :class:`logging.Logger`; the context mapping goes out as ``extra``."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def info(self, message: str, context: LogContext | None = None) -> None:
        self._logger.info(message, extra={"context": dict(context or {})})

    def warn(self, message: str, context: LogContext | None = None) -> None:
        self._logger.warning(message, extra={"context": dict(context or {})})

    def error(self, message: str, context: LogContext | None = None) -> None:
        self._logger.error(message, extra={"context": dict(context or {})})


def logging_adapter(logger: logging.Logger) -> Logger:
    """Wraps a standard-library logger as a package :class:`Logger`.

    Each call forwards the message at the matching level and passes the context
    mapping as ``extra={"context": {...}}`` so formatters/handlers can pick it up.
    """
    return _StdlibLogger(logger)
