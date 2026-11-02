from collections.abc import Callable

import httpx
import pytest

from peek_app_utilities.errors import (
    AdminAccountRequiredError,
    CngApiError,
    CngPermissionError,
    RateLimitError,
)
from peek_app_utilities.internal.cng.endpoints import CNG_API_ENDPOINTS
from peek_app_utilities.internal.cng.permissions import forbidden_error
from peek_app_utilities.internal.cng.products.product_service import CngProductService
from peek_app_utilities.internal.rest_client import RestClient, RestClientOptions
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_VALUE
from peek_app_utilities.logger import noop_logger
from peek_app_utilities.models.cng.product import Activity
from tests.conftest import (
    RecordingLogger,
    json_response,
    mock_http_client,
    no_sleep,
    text_response,
)

PATH = "api/v2/app-registry/products?active=1"
PRODUCT = {
    "id": 1000171,
    "name": "10 students + Complimentary chaperone",
    "slug": "10-students-complimentary-chaperone",
    "status": "ACTIVE",
    "access_control_color_hex": "#1A2B3C",
    "custom_access_control_color": True,
}
EXPECTED = Activity(
    product_id="1000171",
    name="10 students + Complimentary chaperone",
    type="ACTIVITY",
    color="#1A2B3C",
    tickets=[],
)


def build_service(
    handler: Callable[[httpx.Request], httpx.Response], **overrides: object
) -> tuple[CngProductService, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    options: dict[str, object] = {
        "base_api_url": "https://gw.test/api/app-1",
        "endpoints": CNG_API_ENDPOINTS,
        "get_token": lambda: "tok-123",
        "retry_delays_ms": [],
        "logger": noop_logger,
        "http_client": mock_http_client(recording),
        "platform_label": "CNG",
        "api_error": CngApiError,
        "on_forbidden": forbidden_error,
        "sleep": no_sleep,
    }
    options.update(overrides)
    return CngProductService(RestClient(RestClientOptions(**options))), calls  # type: ignore[arg-type]


async def test_maps_a_data_envelope_and_sets_auth_headers_and_url():
    service, calls = build_service(lambda _r: json_response(200, {"data": [PRODUCT]}))
    assert await service.get_all_activities() == [EXPECTED]

    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == f"https://gw.test/api/app-1/cng_backoffice_api-v1/{PATH}"
    assert request.method == "GET"
    assert request.headers["X-Peek-Auth"] == "Bearer tok-123"
    assert request.headers["Content-Type"] == "application/json"
    assert "pk-api-key" not in request.headers
    assert request.headers["x-peek-sdk"] == SDK_HEADER_VALUE


@pytest.mark.parametrize("body", [{}, "plain-text", [1, 2]])
async def test_returns_an_empty_list_when_the_payload_has_no_data_array(body: object):
    service, _ = build_service(lambda _r: json_response(200, body))
    assert await service.get_all_activities() == []


async def test_retries_on_429_then_succeeds():
    n = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return json_response(429, {}) if n == 1 else json_response(200, {"data": []})

    service, _ = build_service(handler, retry_delays_ms=[5])
    assert await service.get_all_activities() == []
    assert n == 2


async def test_raises_rate_limit_error_when_retries_are_exhausted():
    service, _ = build_service(lambda _r: json_response(429, {}), retry_delays_ms=[1])
    with pytest.raises(RateLimitError):
        await service.get_all_activities()


async def test_maps_418_to_admin_account_required_and_logs():
    logger = RecordingLogger()
    service, _ = build_service(lambda _r: json_response(418, {}), logger=logger)
    with pytest.raises(AdminAccountRequiredError):
        await service.get_all_activities()
    assert ("info", "Making CNG request") in [(lvl, msg) for lvl, msg, _ in logger.entries]
    assert logger.entries[0][2]["path"] == PATH
    assert logger.messages("warn")


async def test_raises_cng_permission_error_naming_the_missing_permission_on_403():
    body = {
        "errors": {"permission": ["The app does not have the required permission: products:read"]},
        "message": "Forbidden",
    }
    service, _ = build_service(lambda _r: json_response(403, body))
    with pytest.raises(CngPermissionError) as info:
        await service.get_all_activities()
    err = info.value
    assert not isinstance(err, CngApiError)
    assert err.status_code == 403
    assert err.permissions == ["products:read"]
    assert err.body == body
    assert str(err) == (
        "CNG request forbidden: the app is missing the required permission: products:read"
    )


async def test_logs_a_403_at_warn_with_the_permissions_and_never_at_error():
    logger = RecordingLogger()
    body = {"errors": {"permission": ["needs: products:read"]}, "message": "Forbidden"}
    service, _ = build_service(lambda _r: json_response(403, body), logger=logger)
    with pytest.raises(CngPermissionError):
        await service.get_all_activities()
    warn = [e for e in logger.entries if e[0] == "warn"]
    assert warn[0][1] == f"Missing permission for {PATH} (HTTP 403)"
    assert warn[0][2]["permissions"] == ["products:read"]
    assert logger.messages("error") == []


async def test_pluralizes_the_message_when_several_permissions_are_named():
    body = {
        "errors": {
            "permission": [
                "The app does not have the required permission: products:read",
                "bookings:read",
            ]
        }
    }
    service, _ = build_service(lambda _r: json_response(403, body))
    with pytest.raises(CngPermissionError) as info:
        await service.get_all_activities()
    assert info.value.permissions == ["products:read", "bookings:read"]
    assert str(info.value) == (
        "CNG request forbidden: the app is missing the required permissions: "
        "products:read, bookings:read"
    )


@pytest.mark.parametrize(
    "body",
    [
        "Forbidden",
        None,
        {"message": "Forbidden"},
        {"errors": {"permission": "products:read"}},
        {"errors": {"permission": [42, None]}},
        {"errors": {"permission": ["  "]}},
        {"errors": "nope"},
    ],
)
async def test_falls_back_to_an_unnamed_permission_message(body: object):
    service, _ = build_service(lambda _r: json_response(403, body))
    with pytest.raises(CngPermissionError) as info:
        await service.get_all_activities()
    assert info.value.permissions == []
    assert str(info.value) == "CNG request forbidden: the app is missing a required permission"


async def test_raises_cng_api_error_carrying_status_and_parsed_body():
    service, _ = build_service(lambda _r: json_response(500, {"error": "boom"}))
    with pytest.raises(CngApiError) as info:
        await service.get_all_activities()
    assert info.value.status_code == 500
    assert info.value.body == {"error": "boom"}


async def test_falls_back_to_raw_text_when_the_body_is_not_json():
    service, _ = build_service(lambda _r: text_response(502, "<html>502</html>"))
    with pytest.raises(CngApiError) as info:
        await service.get_all_activities()
    assert info.value.body == "<html>502</html>"


async def test_rest_client_uses_default_sleep_when_none_supplied():
    n = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return json_response(429, {}) if n == 1 else json_response(200, {"data": []})

    service, _ = build_service(handler, retry_delays_ms=[1], sleep=None)
    assert await service.get_all_activities() == []
