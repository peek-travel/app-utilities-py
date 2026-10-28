import httpx
import pytest

from peek_app_utilities.errors import AdminAccountRequiredError, RateLimitError
from peek_app_utilities.internal.http_transport import (
    HttpRetryOptions,
    parse_body,
    request_with_retry,
)
from tests.conftest import RecordingLogger, json_response, mock_http_client, text_response

URL = "https://gw.test/api"


def _options(
    handler, logger: RecordingLogger, delays: list[int], slept: list[float]
) -> HttpRetryOptions:
    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    return HttpRetryOptions(
        retry_delays_ms=delays, logger=logger, http_client=mock_http_client(handler), sleep=sleep
    )


async def _echo_status(response: httpx.Response) -> int:
    return response.status_code


def test_parse_body_returns_json_when_valid():
    assert parse_body(json_response(200, {"a": 1})) == {"a": 1}


def test_parse_body_falls_back_to_raw_text():
    assert parse_body(text_response(404, "Not Found")) == "Not Found"


async def test_delegates_non_418_429_responses_to_on_response():
    logger = RecordingLogger()
    opts = _options(lambda _r: json_response(200, {}), logger, [], [])
    status = await request_with_retry(opts, "GET", URL, "label", _echo_status, headers={})
    assert status == 200
    assert logger.entries == []


async def test_maps_418_to_admin_account_required_and_warns():
    logger = RecordingLogger()
    opts = _options(lambda _r: text_response(418, ""), logger, [1000], [])
    with pytest.raises(AdminAccountRequiredError):
        await request_with_retry(opts, "GET", URL, "sales", _echo_status, headers={})
    assert logger.entries == [("warn", "Admin account required for sales (HTTP 418)", {"url": URL})]


async def test_retries_429_using_the_configured_delays_then_succeeds():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return text_response(429, "") if attempts <= 2 else json_response(200, {})

    logger = RecordingLogger()
    slept: list[float] = []
    opts = _options(handler, logger, [100, 200, 400], slept)
    status = await request_with_retry(opts, "POST", URL, "sales", _echo_status, headers={})
    assert status == 200
    assert attempts == 3
    assert slept == [0.1, 0.2]
    assert logger.messages("warn") == [
        "Rate limited on sales, retrying in 100ms (attempt 1/3)",
        "Rate limited on sales, retrying in 200ms (attempt 2/3)",
    ]


async def test_raises_rate_limit_error_after_retries_are_exhausted():
    logger = RecordingLogger()
    slept: list[float] = []
    opts = _options(lambda _r: text_response(429, ""), logger, [5], slept)
    with pytest.raises(RateLimitError):
        await request_with_retry(opts, "GET", URL, "sales", _echo_status, headers={})
    assert slept == [0.005]
    assert logger.messages("error") == ["Rate limit exceeded for sales"]


async def test_sends_headers_and_json_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, {})

    opts = _options(handler, RecordingLogger(), [], [])
    await request_with_retry(
        opts, "POST", URL, "x", _echo_status, headers={"X-Test": "1"}, json_body={"q": 1}
    )
    assert seen[0].method == "POST"
    assert seen[0].headers["x-test"] == "1"
    assert seen[0].content == b'{"q":1}'
