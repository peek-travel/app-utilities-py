import tomllib
from pathlib import Path

from peek_app_utilities.internal.sdk_headers import (
    SDK_HEADER_NAME,
    SDK_HEADER_VALUE,
    SDK_VERSION,
)

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
_PACKAGE_VERSION: str = tomllib.loads(_PYPROJECT.read_text("utf-8"))["project"]["version"]


def test_uses_the_x_peek_sdk_header_name():
    assert SDK_HEADER_NAME == "x-peek-sdk"


def test_pins_sdk_version_to_the_pyproject_version():
    # Drift guard: if this fails after a version bump, update SDK_VERSION in
    # src/peek_app_utilities/internal/sdk_headers.py.
    assert SDK_VERSION == _PACKAGE_VERSION


def test_formats_the_header_value_as_py_version():
    assert f"py-{_PACKAGE_VERSION}" == SDK_HEADER_VALUE
