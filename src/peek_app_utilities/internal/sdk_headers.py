"""The SDK identification header sent on every outbound request (Peek GraphQL,
CNG REST, ACME REST) so the downstream platforms can attribute traffic to this
package and its version.

The version is a literal rather than an ``importlib.metadata`` lookup so the
header is correct even from a source checkout and costs nothing at import time.
``tests/test_sdk_headers.py`` pins it to ``pyproject.toml`` so the two can
never drift — **bump both together**, and keep it equal to the matching
``@peektravel/app-utilities`` release.
"""

from __future__ import annotations

from typing import Final

SDK_HEADER_NAME: Final = "x-peek-sdk"
"""Header name carrying the SDK identifier."""

_SDK_PLATFORM: Final = "py"

SDK_VERSION: Final = "0.9.4"
"""Must equal ``project.version`` in ``pyproject.toml``."""

SDK_HEADER_VALUE: Final = f"{_SDK_PLATFORM}-{SDK_VERSION}"
"""The ``x-peek-sdk`` header value, e.g. ``py-0.9.4``."""
