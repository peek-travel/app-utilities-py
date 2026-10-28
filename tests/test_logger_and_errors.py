import logging

import pytest

from peek_app_utilities.errors import (
    AcmeApiError,
    AdminAccountRequiredError,
    AppUtilitiesError,
    CngApiError,
    CngPermissionError,
    PeekGraphQLError,
    PeekHttpError,
    PiiAccessDisabledError,
    RateLimitError,
)
from peek_app_utilities.logger import Logger, logging_adapter, noop_logger


def test_noop_logger_discards_everything():
    assert isinstance(noop_logger, Logger)
    noop_logger.info("a")
    noop_logger.warn("b", {"k": 1})
    noop_logger.error("c", None)


def test_logging_adapter_forwards_each_level_with_context(caplog: pytest.LogCaptureFixture):
    std = logging.getLogger("peek-test")
    adapter = logging_adapter(std)
    with caplog.at_level(logging.INFO, logger="peek-test"):
        adapter.info("hello", {"a": 1})
        adapter.warn("careful")
        adapter.error("boom", {"b": 2})

    levels = [(r.levelname, r.getMessage(), getattr(r, "context", None)) for r in caplog.records]
    assert levels == [
        ("INFO", "hello", {"a": 1}),
        ("WARNING", "careful", {}),
        ("ERROR", "boom", {"b": 2}),
    ]


def test_every_error_derives_from_the_package_base():
    errors: list[AppUtilitiesError] = [
        AdminAccountRequiredError(),
        RateLimitError(),
        PeekGraphQLError([{"message": "x"}]),
        PeekHttpError(500, "https://x", {"e": 1}),
        PiiAccessDisabledError("make_payment"),
        CngApiError(500, "body"),
        CngPermissionError([], None),
        AcmeApiError(502, "<html>"),
    ]
    assert all(isinstance(e, AppUtilitiesError) for e in errors)


def test_error_defaults_and_attributes():
    assert str(AdminAccountRequiredError()) == "Admin account required"
    assert AdminAccountRequiredError().status_code == 418
    assert str(RateLimitError()) == "Rate limit exceeded"
    assert RateLimitError().status_code == 429

    gql = PeekGraphQLError([{"message": "bad"}])
    assert gql.graphql_errors == [{"message": "bad"}]
    assert str(gql) == "GraphQL request failed"

    http = PeekHttpError(404, "https://x/y", "Not Found")
    assert (http.status_code, http.url, http.body) == (404, "https://x/y", "Not Found")
    assert str(http) == "Peek request failed with HTTP 404"
    assert str(PeekHttpError(500, "u", None, "custom")) == "custom"

    pii = PiiAccessDisabledError("make_payment")
    assert pii.operation == "make_payment"
    assert '"make_payment" is disabled' in str(pii)
    assert "full_customer_access" in str(pii)

    cng = CngApiError(503, {"x": 1})
    assert (cng.status_code, cng.body) == (503, {"x": 1})
    assert str(cng) == "CNG request failed with HTTP 503"
    assert str(CngApiError(503, None, "m")) == "m"

    acme = AcmeApiError(500, "b")
    assert str(acme) == "ACME request failed with HTTP 500"
    assert str(AcmeApiError(500, "b", "m")) == "m"


def test_cng_permission_error_messages():
    assert str(CngPermissionError([], {})) == (
        "CNG request forbidden: the app is missing a required permission"
    )
    assert str(CngPermissionError(["products:read"], {})) == (
        "CNG request forbidden: the app is missing the required permission: products:read"
    )
    many = CngPermissionError(["products:read", "bookings:read"], {"b": 1})
    assert str(many) == (
        "CNG request forbidden: the app is missing the required permissions: "
        "products:read, bookings:read"
    )
    assert many.permissions == ["products:read", "bookings:read"]
    assert many.body == {"b": 1}
    assert many.status_code == 403
    assert str(CngPermissionError([], None, "custom")) == "custom"
