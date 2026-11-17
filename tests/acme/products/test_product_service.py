from collections.abc import Callable

import httpx
import pytest

from peek_app_utilities.errors import AcmeApiError, AdminAccountRequiredError, RateLimitError
from peek_app_utilities.internal.acme.endpoints import ACME_API_ENDPOINTS
from peek_app_utilities.internal.acme.products.product_service import AcmeProductService
from peek_app_utilities.internal.rest_client import RestClient, RestClientOptions
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_VALUE
from peek_app_utilities.logger import noop_logger
from peek_app_utilities.models.acme.product import AcmeActivity
from tests.conftest import (
    RecordingLogger,
    json_response,
    mock_http_client,
    no_sleep,
    text_response,
)

PATH = "v2/b2b/event/templates/names?pageSize=-1&page=1"
TEMPLATE = {
    "id": "61f99bfe62bd1f467c39771f",
    "name": "General Admission",
    "type": "standard",
    "admissionType": "standard",
    "reviewState": "published",
    "colorCategory": {"backgroundColor": "#00695c", "textColor": "#ffffff"},
}
EXPECTED = AcmeActivity(
    product_id="61f99bfe62bd1f467c39771f",
    name="General Admission",
    type="standard",
    color="#00695c",
    tickets=[],
)


def build_service(
    handler: Callable[[httpx.Request], httpx.Response], **overrides: object
) -> tuple[AcmeProductService, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    options: dict[str, object] = {
        "base_api_url": "https://gw.test/api/app-1",
        "endpoints": ACME_API_ENDPOINTS,
        "get_token": lambda: "tok-123",
        "retry_delays_ms": [],
        "logger": noop_logger,
        "http_client": mock_http_client(recording),
        "platform_label": "ACME",
        "api_error": AcmeApiError,
        "sleep": no_sleep,
    }
    options.update(overrides)
    return AcmeProductService(RestClient(RestClientOptions(**options))), calls  # type: ignore[arg-type]


async def test_maps_a_list_envelope_and_sets_auth_headers_and_url():
    service, calls = build_service(lambda _r: json_response(200, {"list": [TEMPLATE]}))
    assert await service.get_all_activities() == [EXPECTED]

    request = calls[0]
    assert str(request.url) == f"https://gw.test/api/app-1/acme_backoffice_api-v1/{PATH}"
    assert request.method == "GET"
    assert request.headers["X-Peek-Auth"] == "Bearer tok-123"
    assert request.headers["Content-Type"] == "application/json"
    assert "pk-api-key" not in request.headers
    assert request.headers["x-peek-sdk"] == SDK_HEADER_VALUE


async def test_tolerates_a_bare_array_response():
    service, _ = build_service(lambda _r: json_response(200, [TEMPLATE]))
    assert await service.get_all_activities() == [EXPECTED]


@pytest.mark.parametrize("body", [{}, {"list": None}, "plain"])
async def test_returns_an_empty_list_when_the_payload_has_no_list(body: object):
    service, _ = build_service(lambda _r: json_response(200, body))
    assert await service.get_all_activities() == []


async def test_retries_on_429_then_succeeds():
    n = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return json_response(429, {}) if n == 1 else json_response(200, {"list": []})

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
    assert logger.entries[0][:2] == ("info", "Making ACME request")
    assert logger.entries[0][2]["path"] == PATH
    assert logger.messages("warn")


async def test_a_403_is_a_plain_acme_api_error():
    service, _ = build_service(lambda _r: json_response(403, {"m": "no"}))
    with pytest.raises(AcmeApiError) as info:
        await service.get_all_activities()
    assert info.value.status_code == 403


async def test_raises_acme_api_error_carrying_status_and_parsed_body():
    service, _ = build_service(lambda _r: json_response(500, {"error": "boom"}))
    with pytest.raises(AcmeApiError) as info:
        await service.get_all_activities()
    assert info.value.status_code == 500
    assert info.value.body == {"error": "boom"}


async def test_falls_back_to_raw_text_when_the_body_is_not_json():
    service, _ = build_service(lambda _r: text_response(502, "<html>502</html>"))
    with pytest.raises(AcmeApiError) as info:
        await service.get_all_activities()
    assert info.value.body == "<html>502</html>"
