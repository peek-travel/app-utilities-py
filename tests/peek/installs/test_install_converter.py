import json

import pytest

from peek_app_utilities.internal.peek.installs.install_converter import (
    extract_install_webhook_body,
    to_install_status,
    to_peek_platform,
)


@pytest.mark.parametrize("status", ["installed", "uninstalled", "update_installed"])
def test_to_install_status_narrows_known_values(status: str):
    assert to_install_status(status) == status


@pytest.mark.parametrize("raw", ["", "suspended", "INSTALLED"])
def test_to_install_status_returns_none_for_unknown(raw: str):
    assert to_install_status(raw) is None


@pytest.mark.parametrize("platform", ["peek", "cng", "acme"])
def test_to_peek_platform_narrows_known_values(platform: str):
    assert to_peek_platform(platform) == platform


@pytest.mark.parametrize("raw", ["", "newbrand", "Peek"])
def test_to_peek_platform_returns_none_for_unknown(raw: str):
    assert to_peek_platform(raw) is None


def test_extract_returns_a_mapping_body_unchanged():
    body = {"account": {"id": "acct_42", "name": "Sunset Kayak Tours"}}
    assert extract_install_webhook_body(body) is body


def test_extract_parses_a_json_string_body():
    body = {"account": {"id": "acct_42", "is_test": True}}
    assert extract_install_webhook_body(json.dumps(body)) == body


@pytest.mark.parametrize("payload", [None, 42, "{not json", "[1, 2]", ["list"]])
def test_extract_returns_an_empty_body_for_non_objects(payload: object):
    assert extract_install_webhook_body(payload) == {}
