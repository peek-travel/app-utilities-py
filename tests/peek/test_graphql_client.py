import httpx
import pytest

from peek_app_utilities.errors import (
    AdminAccountRequiredError,
    PeekGraphQLError,
    PeekHttpError,
    RateLimitError,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT, peek_api_endpoints
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient, GraphQLClientOptions
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_VALUE
from peek_app_utilities.logger import noop_logger
from tests.conftest import (
    RecordingLogger,
    json_response,
    mock_http_client,
    no_sleep,
    request_json,
    text_response,
)

BASE = "https://gw.test/api/app-1"


def build_client(handler, **overrides) -> GraphQLClient:
    options = {
        "base_api_url": BASE,
        "endpoints": peek_api_endpoints(True),
        "gateway_key": "gw-key",
        "get_token": lambda: "tok-123",
        "retry_delays_ms": [],
        "logger": noop_logger,
        "http_client": mock_http_client(handler),
        "sleep": no_sleep,
    }
    options.update(overrides)
    return GraphQLClient(GraphQLClientOptions(**options))


async def test_posts_a_collapsed_query_with_auth_headers_to_the_slugged_endpoint():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, {"data": {"ok": True}})

    body = await build_client(handler).request(
        SALES_ENDPOINT, "query {\n  activities {\n id } }", {"a": 1}
    )

    assert body == {"data": {"ok": True}}
    request = seen[0]
    assert str(request.url) == f"{BASE}/peek_backoffice_api-v1"
    assert request.method == "POST"
    assert request.headers["X-Peek-Auth"] == "Bearer tok-123"
    assert request.headers["pk-api-key"] == "gw-key"
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["x-peek-sdk"] == SDK_HEADER_VALUE
    assert request_json(request) == {"query": "query { activities { id } }", "variables": {"a": 1}}


async def test_legacy_v1_routing_puts_sales_directly_under_the_base():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, {"data": {}})

    await build_client(handler, endpoints=peek_api_endpoints(False)).request(
        SALES_ENDPOINT, "{}", {}
    )
    assert str(seen[0].url) == f"{BASE}/sales"


async def test_omits_pk_api_key_when_no_gateway_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, {"data": {}})

    await build_client(handler, gateway_key=None).request(SALES_ENDPOINT, "{}", {})
    assert "pk-api-key" not in seen[0].headers


async def test_raises_peek_graphql_error_when_errors_array_present():
    logger = RecordingLogger()
    errors = [{"message": "nope"}]
    client = build_client(lambda _r: json_response(200, {"errors": errors}), logger=logger)
    with pytest.raises(PeekGraphQLError) as info:
        await client.request(SALES_ENDPOINT, "{}", {})
    assert info.value.graphql_errors == errors
    assert logger.messages("error") == ["GraphQL errors for sales"]
    assert logger.entries[-1][2]["graphqlErrors"] == '[{"message": "nope"}]'


async def test_raises_peek_http_error_with_status_url_and_body_for_non_2xx():
    client = build_client(lambda _r: text_response(404, "Not Found"))
    with pytest.raises(PeekHttpError) as info:
        await client.request(SALES_ENDPOINT, "{}", {})
    assert info.value.status_code == 404
    assert info.value.url == f"{BASE}/peek_backoffice_api-v1"
    assert info.value.body == "Not Found"


async def test_keeps_parsed_json_body_on_http_error():
    client = build_client(lambda _r: json_response(500, {"error": "boom"}))
    with pytest.raises(PeekHttpError) as info:
        await client.request(SALES_ENDPOINT, "{}", {})
    assert info.value.body == {"error": "boom"}


async def test_graphql_errors_take_precedence_over_http_status():
    client = build_client(lambda _r: json_response(400, {"errors": [{"message": "x"}]}))
    with pytest.raises(PeekGraphQLError):
        await client.request(SALES_ENDPOINT, "{}", {})


async def test_maps_418_and_429():
    with pytest.raises(AdminAccountRequiredError):
        await build_client(lambda _r: text_response(418, "")).request(SALES_ENDPOINT, "{}", {})
    with pytest.raises(RateLimitError):
        await build_client(lambda _r: text_response(429, ""), retry_delays_ms=[1]).request(
            SALES_ENDPOINT, "{}", {}
        )


async def test_retries_429_then_succeeds():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return text_response(429, "") if attempts == 1 else json_response(200, {"data": {"n": 1}})

    body = await build_client(handler, retry_delays_ms=[1]).request(SALES_ENDPOINT, "{}", {})
    assert body == {"data": {"n": 1}}
    assert attempts == 2


async def test_non_object_success_body_yields_an_empty_body():
    body = await build_client(lambda _r: text_response(200, "plain")).request(
        SALES_ENDPOINT, "{}", {}
    )
    assert body == {}


async def test_uses_default_sleep_when_none_supplied():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return text_response(429, "") if attempts == 1 else json_response(200, {"data": {}})

    client = build_client(handler, retry_delays_ms=[1], sleep=None)
    assert await client.request(SALES_ENDPOINT, "{}", {}) == {"data": {}}
