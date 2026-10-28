from typing import Any, cast

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
from peek_app_utilities.internal.peek.products.product_service import (
    ProductService,
    ProductServiceOptions,
)
from peek_app_utilities.internal.sdk_headers import SDK_HEADER_VALUE
from peek_app_utilities.logger import noop_logger
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption
from peek_app_utilities.models.peek.pricing import PricingMoney
from peek_app_utilities.models.peek.product import Product, ProductTicket
from tests.conftest import (
    FakeGraphQLClient,
    RecordingLogger,
    json_response,
    mock_http_client,
    no_sleep,
    request_json,
    text_response,
)

BASE = "https://gw.test/gql/app-1"


def build_client(handler, **overrides) -> GraphQLClient:
    """A real ``GraphQLClient`` over a mock HTTP transport (the TS tests inject a
    fake ``fetch``), for the cases that exercise the transport end to end."""
    options: dict[str, Any] = {
        "base_api_url": BASE,
        "endpoints": peek_api_endpoints(False),
        "gateway_key": "gw-key",
        "get_token": lambda: "tok-123",
        "retry_delays_ms": [],
        "logger": noop_logger,
        "http_client": mock_http_client(handler),
        "sleep": no_sleep,
    }
    options.update(overrides)
    return GraphQLClient(GraphQLClientOptions(**options))


def service_over(
    gql: FakeGraphQLClient, options: ProductServiceOptions | None = None
) -> ProductService:
    return ProductService(cast(GraphQLClient, gql), options)


def query_of(request: httpx.Request) -> str:
    return cast(str, request_json(request)["query"])


def variables_of(request: httpx.Request) -> dict[str, Any]:
    return cast(dict[str, Any], request_json(request)["variables"])


ACTIVITY = {
    "name": "Kayak Tour",
    "id": "act-1",
    "type": "ACTIVITY",
    "colorHex": "#1A2B3C",
    "currency": "USD",
    "resourceOptions": [
        {
            "id": "r1",
            "name": "Single",
            "priceRange": {
                "min": {"currency": "USD", "amount": "50.00", "formatted": "$50.00"},
                "max": {"currency": "USD", "amount": "80.00", "formatted": "$80.00"},
            },
        }
    ],
}

ACTIVITY_TICKET = ProductTicket(
    id="r1",
    name="Single",
    min_price=PricingMoney(amount="50.00", currency="USD", display_price="$50.00"),
    max_price=PricingMoney(amount="80.00", currency="USD", display_price="$80.00"),
)

ACTIVITY_PRODUCT = Product(
    product_id="act-1",
    name="Kayak Tour",
    type="ACTIVITY",
    color="#1A2B3C",
    currency="USD",
    image_url=None,
    description=None,
    meeting_location=None,
    tickets=[ACTIVITY_TICKET],
)

RENTAL = {
    "name": "Test Rental",
    "id": "rental-1",
    "type": "RENTAL",
    "colorHex": "#1EC6CE",
    "currency": "USD",
    "resourceOptions": [{"id": "r2", "name": "Bikes"}],
}


def add_on_node(option_id: str, option_name: str) -> dict[str, Any]:
    return {
        "id": option_id,
        "name": option_name,
        "description": None,
        "item": {"id": "item-1", "name": "Safety Gear"},
    }


def add_on_product(*tickets: ProductTicket) -> Product:
    return Product(
        product_id="item-1",
        name="Safety Gear",
        type="ADD-ON",
        color="#FFFFFF",
        currency="",
        image_url=None,
        description=None,
        meeting_location=None,
        tickets=list(tickets),
    )


def add_on_ticket(option_id: str, option_name: str) -> ProductTicket:
    return ProductTicket(id=option_id, name=option_name, min_price=None, max_price=None)


def item_options_page(edges: list[dict[str, Any]], end_cursor: str | None) -> dict[str, Any]:
    return {
        "itemOptions": {
            "edges": edges,
            "pageInfo": {"hasNextPage": end_cursor is not None, "endCursor": end_cursor},
        }
    }


EMPTY_ITEM_OPTIONS = item_options_page([], None)

# ─── get_all_products ────────────────────────────────────────────────────────


async def test_combines_activities_and_add_ons_paginating_item_options_across_pages():
    seen: list[httpx.Request] = []
    item_options_pages = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal item_options_pages
        seen.append(request)
        query = query_of(request)
        if "activities" in query:
            # Query should be whitespace-collapsed (single line, no double spaces).
            assert "\n" not in query
            assert "  " not in query
            # Catalog fields must be requested on the wire.
            for field in (
                "imageUrl",
                "description",
                "meetingLocationFormattedAddress",
                "meetingLocationUrl",
                "infoMeetingLocation",
            ):
                assert field in query
            return json_response(200, {"data": {"activities": [ACTIVITY]}})

        item_options_pages += 1
        if item_options_pages == 1:
            assert variables_of(request)["after"] is None
            return json_response(
                200,
                {
                    "data": item_options_page(
                        [{"cursor": "c1", "node": add_on_node("opt-1", "Helmet")}], "c1"
                    )
                },
            )
        assert variables_of(request)["after"] == "c1"
        return json_response(
            200,
            {
                "data": item_options_page(
                    [{"cursor": "c2", "node": add_on_node("opt-2", "Life Vest")}], None
                )
            },
        )

    service = ProductService(build_client(handler))
    products = await service.get_all_products()

    assert products == [
        ACTIVITY_PRODUCT,
        add_on_product(add_on_ticket("opt-1", "Helmet"), add_on_ticket("opt-2", "Life Vest")),
    ]

    # 1 activities call + 2 item-option pages.
    assert len(seen) == 3
    assert str(seen[0].url) == f"{BASE}/sales"
    headers = seen[0].headers
    assert headers["X-Peek-Auth"] == "Bearer tok-123"
    assert headers["pk-api-key"] == "gw-key"
    assert headers["Content-Type"] == "application/json"
    assert headers["x-peek-sdk"] == SDK_HEADER_VALUE


async def test_uses_the_configured_item_options_page_size(gql: FakeGraphQLClient):
    gql.queue({"activities": []}).queue(EMPTY_ITEM_OPTIONS)

    await service_over(gql, ProductServiceOptions(item_options_page_size=7)).get_all_products()

    item_call = next(c for c in gql.calls if "itemOptions" in c.query)
    assert item_call.variables["first"] == 7
    assert item_call.endpoint_name == SALES_ENDPOINT


async def test_defaults_the_item_options_page_size_to_50(gql: FakeGraphQLClient):
    gql.queue(EMPTY_ITEM_OPTIONS)

    await service_over(gql).get_all_addons()

    assert gql.last_call.variables == {"first": 50, "after": None}


async def test_returns_an_empty_list_when_a_200_response_carries_no_data():
    service = ProductService(build_client(lambda _r: json_response(200, {})))

    assert await service.get_all_products() == []


async def test_retries_on_http_429_then_succeeds():
    activities_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal activities_calls
        if "activities" in query_of(request):
            activities_calls += 1
            if activities_calls == 1:
                return json_response(429, {})
            return json_response(200, {"data": {"activities": []}})
        return json_response(200, {"data": EMPTY_ITEM_OPTIONS})

    service = ProductService(build_client(handler, retry_delays_ms=[5]))

    assert await service.get_all_products() == []
    assert activities_calls == 2


async def test_raises_rate_limit_error_when_retries_are_exhausted():
    service = ProductService(build_client(lambda _r: json_response(429, {}), retry_delays_ms=[1]))

    with pytest.raises(RateLimitError):
        await service.get_all_products()


async def test_maps_http_418_to_admin_account_required_error_and_logs():
    logger = RecordingLogger()

    def handler(request: httpx.Request) -> httpx.Response:
        if "activities" in query_of(request):
            return json_response(418, {})
        return json_response(200, {"data": EMPTY_ITEM_OPTIONS})

    service = ProductService(build_client(handler, logger=logger))

    with pytest.raises(AdminAccountRequiredError):
        await service.get_all_products()
    assert any(
        message == "Making GraphQL request" and context.get("endpointName") == "sales"
        for level, message, context in logger.entries
        if level == "info"
    )
    assert logger.messages("warn")


async def test_raises_peek_graphql_error_carrying_the_raw_errors():
    graphql_errors = [{"message": "boom"}]

    def handler(request: httpx.Request) -> httpx.Response:
        if "activities" in query_of(request):
            return json_response(200, {"errors": graphql_errors})
        return json_response(200, {"data": EMPTY_ITEM_OPTIONS})

    service = ProductService(build_client(handler))

    with pytest.raises(PeekGraphQLError) as excinfo:
        await service.get_all_products()
    assert excinfo.value.graphql_errors == graphql_errors


async def test_raises_a_typed_peek_http_error_for_other_non_2xx_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        if "activities" in query_of(request):
            return json_response(500, {"oops": True})
        return json_response(200, {"data": EMPTY_ITEM_OPTIONS})

    service = ProductService(build_client(handler))

    with pytest.raises(PeekHttpError) as excinfo:
        await service.get_all_products()
    assert excinfo.value.status_code == 500
    assert excinfo.value.body == {"oops": True}
    assert excinfo.value.url == f"{BASE}/sales"


async def test_surfaces_the_http_status_for_a_non_json_error_page_instead_of_a_parse_error():
    # Regression: a 404 with a plain-text body must not blow up while parsing
    # the body before the status is read.
    def handler(request: httpx.Request) -> httpx.Response:
        if "activities" in query_of(request):
            return text_response(404, "Not Found")
        return json_response(200, {"data": EMPTY_ITEM_OPTIONS})

    service = ProductService(build_client(handler))

    with pytest.raises(PeekHttpError) as excinfo:
        await service.get_all_products()
    assert excinfo.value.status_code == 404
    assert excinfo.value.body == "Not Found"


# ─── get_all_activities ──────────────────────────────────────────────────────


async def test_get_all_activities_returns_only_activity_typed_products_making_one_request(
    gql: FakeGraphQLClient,
):
    gql.queue({"activities": [ACTIVITY, RENTAL]})

    products = await service_over(gql).get_all_activities()

    assert products == [ACTIVITY_PRODUCT]
    assert len(gql.calls) == 1
    assert "itemOptions" not in gql.last_call.query


async def test_get_all_activities_returns_empty_list_when_no_activity_typed_products_exist(
    gql: FakeGraphQLClient,
):
    gql.queue({"activities": [RENTAL]})
    assert await service_over(gql).get_all_activities() == []


# ─── get_all_rentals ─────────────────────────────────────────────────────────


async def test_get_all_rentals_returns_only_rental_typed_products_making_one_request(
    gql: FakeGraphQLClient,
):
    gql.queue({"activities": [ACTIVITY, RENTAL]})

    products = await service_over(gql).get_all_rentals()

    assert products == [
        Product(
            product_id="rental-1",
            name="Test Rental",
            type="RENTAL",
            color="#1EC6CE",
            currency="USD",
            image_url=None,
            description=None,
            meeting_location=None,
            tickets=[ProductTicket(id="r2", name="Bikes", min_price=None, max_price=None)],
        )
    ]
    assert len(gql.calls) == 1
    assert "itemOptions" not in gql.last_call.query


async def test_get_all_rentals_returns_empty_list_when_no_rental_typed_products_exist(
    gql: FakeGraphQLClient,
):
    gql.queue({"activities": [ACTIVITY]})
    assert await service_over(gql).get_all_rentals() == []


# ─── get_all_addons ──────────────────────────────────────────────────────────


async def test_get_all_addons_returns_only_add_on_products_paginating_across_pages(
    gql: FakeGraphQLClient,
):
    gql.queue(item_options_page([{"cursor": "c1", "node": add_on_node("opt-1", "Helmet")}], "c1"))
    gql.queue(EMPTY_ITEM_OPTIONS)

    products = await service_over(gql).get_all_addons()

    assert products == [add_on_product(add_on_ticket("opt-1", "Helmet"))]
    assert len(gql.calls) == 2
    assert all("activities" not in c.query for c in gql.calls)
    assert [c.variables["after"] for c in gql.calls] == [None, "c1"]


async def test_get_all_addons_returns_empty_list_when_no_add_ons_exist(gql: FakeGraphQLClient):
    gql.queue(EMPTY_ITEM_OPTIONS)
    assert await service_over(gql).get_all_addons() == []


async def test_get_all_addons_stops_when_has_next_page_is_set_without_an_end_cursor(
    gql: FakeGraphQLClient,
):
    gql.queue(
        {
            "itemOptions": {
                "edges": [{"cursor": "c1", "node": add_on_node("opt-1", "Helmet")}],
                "pageInfo": {"hasNextPage": True, "endCursor": None},
            }
        }
    )

    products = await service_over(gql).get_all_addons()

    assert products == [add_on_product(add_on_ticket("opt-1", "Helmet"))]
    assert len(gql.calls) == 1


# ─── get_custom_questions ────────────────────────────────────────────────────

CUSTOM_QUESTIONS_ACTIVITY = {
    "id": "act-1",
    "name": "Downtown Bike Tour",
    "questionActivityConfigurations": [
        {
            "isRequired": False,
            "order": 1,
            "question": {
                "id": "cq_anq67",
                "questionType": "CHECK_BOX",
                "text": "Check box - Per Guest - Adult Only",
                "answerDefaultValue": None,
                "hint": None,
                "internalLabel": None,
                "perGuest": True,
            },
        },
        {
            "isRequired": False,
            "order": 3,
            "question": {
                "id": "cq_bq48e",
                "questionType": "SELECT_ONE",
                "text": "Multiple Choice",
                "answerDefaultValue": None,
                "hint": None,
                "internalLabel": None,
                "perGuest": False,
                "options": [
                    {"id": "cqao_mwdgvw", "text": "Option A", "order": 1},
                    {"id": "cqao_va78v7", "text": "Option B", "order": 2},
                ],
            },
        },
    ],
}


async def test_passes_the_product_id_and_maps_configurations_into_custom_questions(
    gql: FakeGraphQLClient,
):
    gql.queue({"activity": CUSTOM_QUESTIONS_ACTIVITY})

    questions = await service_over(gql).get_custom_questions("act-1")

    assert questions == [
        CustomQuestion(
            id="cq_anq67",
            order=1,
            is_required=False,
            question_text="Check box - Per Guest - Adult Only",
            hint_text=None,
            question_type="CHECK_BOX",
            internal_label=None,
            per_guest=True,
            default_value=None,
            options=[],
        ),
        CustomQuestion(
            id="cq_bq48e",
            order=3,
            is_required=False,
            question_text="Multiple Choice",
            hint_text=None,
            question_type="SELECT_ONE",
            internal_label=None,
            per_guest=False,
            default_value=None,
            options=[
                CustomQuestionOption(id="cqao_mwdgvw", order=1, value="Option A"),
                CustomQuestionOption(id="cqao_va78v7", order=2, value="Option B"),
            ],
        ),
    ]
    assert len(gql.calls) == 1
    call = gql.last_call
    assert call.endpoint_name == SALES_ENDPOINT
    assert "questionActivityConfigurations" in call.query
    assert "ChoiceQuestion" in call.query
    assert call.variables == {"id": "act-1"}


async def test_returns_an_empty_list_when_the_activity_is_not_found(gql: FakeGraphQLClient):
    gql.queue({"activity": None})
    assert await service_over(gql).get_custom_questions("missing") == []


async def test_custom_questions_returns_an_empty_list_when_a_200_response_carries_no_data(
    gql: FakeGraphQLClient,
):
    gql.queue_body({})
    assert await service_over(gql).get_custom_questions("act-1") == []


async def test_raises_without_hitting_the_network_when_the_id_is_blank(gql: FakeGraphQLClient):
    with pytest.raises(ValueError, match="A non-empty product id is required"):
        await service_over(gql).get_custom_questions("  ")
    with pytest.raises(ValueError, match="A non-empty product id is required"):
        await service_over(gql).get_custom_questions("")
    assert gql.calls == []
