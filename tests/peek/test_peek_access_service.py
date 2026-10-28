import json
import time
from typing import Any

import httpx
import jwt
import pytest

from peek_app_utilities.access_options import AccessOptions
from peek_app_utilities.errors import PiiAccessDisabledError
from peek_app_utilities.internal.peek.account_users.account_user_service import (
    AccountUserService,
)
from peek_app_utilities.internal.peek.availability.availability_service import (
    AvailabilityService,
)
from peek_app_utilities.internal.peek.bookings.booking_service import BookingService
from peek_app_utilities.internal.peek.daily_notes.daily_note_service import DailyNoteService
from peek_app_utilities.internal.peek.memberships.membership_service import MembershipService
from peek_app_utilities.internal.peek.pricing.pricing_service import PricingService
from peek_app_utilities.internal.peek.products.product_service import ProductService
from peek_app_utilities.internal.peek.promo_codes.promo_code_service import PromoCodeService
from peek_app_utilities.internal.peek.resellers.reseller_service import ResellerService
from peek_app_utilities.internal.peek.resource_pools.resource_pool_service import (
    ResourcePoolService,
)
from peek_app_utilities.internal.peek.reviews.review_service import ReviewService
from peek_app_utilities.internal.peek.timeslots.timeslot_service import TimeslotService
from peek_app_utilities.peek_access_service import PeekAccessService, PeekAccessServiceConfig
from tests.conftest import RecordingLogger, json_response, mock_http_client

REQUIRED = {
    "install_id": "install-1",
    "jwt_secret": "secret",
    "issuer": "Peek Test",
    "app_id": "app-1",
    "gateway_key": "gw-key",
}
INSTALL_ID = "8c1f32b4-ab3c-4e20-82b7-844ea9e03bc9"
REGISTRY_ISSUER = "app_registry_v2"
REGISTRY_AUDIENCE = "Joken"
SAMPLE_USER = {
    "email": "admin@peek.com",
    "id": "usr_9f21",
    "is_admin": False,
    "locale": "en",
    "name": "Admin User",
    "platform": "peek",
}
API_URL = "https://app-registry.sandbox.peeklabs.com/installations-api/demo-app"
RESOLVED_URL = f"{API_URL}/peek_backoffice_api-v1"


def config(**overrides: Any) -> PeekAccessServiceConfig:
    return PeekAccessServiceConfig(**{**REQUIRED, **overrides})


def empty_products_client() -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """An HTTP client answering the product queries with empty pages, recording calls."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        query = json.loads(request.content)["query"]
        if "activities" in query:
            return json_response(200, {"data": {"activities": []}})
        return json_response(
            200,
            {"data": {"itemOptions": {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}},
        )

    return mock_http_client(handler), calls


def mint(secret: str, overrides: dict[str, Any] | None = None, **claims: Any) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "display_version": "0.0.11",
        "user": SAMPLE_USER,
        "sub": INSTALL_ID,
        "iss": REGISTRY_ISSUER,
        "aud": REGISTRY_AUDIENCE,
        "jti": "7d3d42c5-5724-489e-8380-a33abfc14936",
        "exp": now + 60,
        "nbf": now,
    }
    payload.update(overrides or {})
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


# ─── constructor validation ──────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["install_id", "jwt_secret", "issuer", "app_id", "gateway_key"])
def test_raises_when_a_required_v1_field_is_missing(field: str):
    with pytest.raises(ValueError, match=field):
        PeekAccessService(config(**{field: ""}))


def test_does_not_require_gateway_key_in_v2_mode():
    PeekAccessService(
        PeekAccessServiceConfig(
            install_id="install-1", jwt_secret="secret", issuer="Peek Test", app_id="app-1", mode="v2"
        )
    )


# ─── accessors ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("accessor", "cls"),
    [
        ("get_product_service", ProductService),
        ("get_account_user_service", AccountUserService),
        ("get_resource_pool_service", ResourcePoolService),
        ("get_timeslot_service", TimeslotService),
        ("get_reseller_service", ResellerService),
        ("get_promo_code_service", PromoCodeService),
        ("get_pricing_service", PricingService),
        ("get_daily_note_service", DailyNoteService),
        ("get_availability_service", AvailabilityService),
        ("get_membership_service", MembershipService),
        ("get_booking_service", BookingService),
        ("get_review_service", ReviewService),
    ],
)
def test_accessors_return_the_service_and_memoize_the_instance(accessor: str, cls: type):
    peek = PeekAccessService(config())
    service = getattr(peek, accessor)()
    assert isinstance(service, cls)
    assert getattr(peek, accessor)() is service


def test_memoizes_booking_service_per_integrator_and_defaults_to_the_issuer():
    peek = PeekAccessService(config())
    default = peek.get_booking_service()
    assert peek.get_booking_service("Peek Test") is default
    custom = peek.get_booking_service("custom-integrator")
    assert custom is not default
    assert peek.get_booking_service("custom-integrator") is custom


# ─── transport wiring ────────────────────────────────────────────────────────


async def test_wires_the_default_endpoint_and_a_minted_bearer_token():
    client, calls = empty_products_client()
    async with PeekAccessService(config(http_client=client)) as peek:
        await peek.get_product_service().get_all_products()

    assert str(calls[0].url) == "https://apps.peekapis.com/backoffice-gql/app-1/sales"
    assert calls[0].headers["X-Peek-Auth"].startswith("Bearer ")
    assert calls[0].headers["pk-api-key"] == "gw-key"


async def test_forwards_configuration_overrides_to_the_transport_and_product_service():
    logger = RecordingLogger()
    client, calls = empty_products_client()
    peek = PeekAccessService(
        config(
            http_client=client,
            base_url="https://custom.test/gql",
            retry_delays_ms=[1],
            logger=logger,
            item_options_page_size=7,
            token_ttl_seconds=120,
            token_refresh_leeway_seconds=10,
        )
    )
    await peek.get_product_service().get_all_products()

    assert str(calls[0].url) == "https://custom.test/gql/app-1/sales"
    assert logger.messages("info")
    item_call = next(c for c in calls if "itemOptions" in json.loads(c.content)["query"])
    assert json.loads(item_call.content)["variables"]["first"] == 7


async def test_owns_and_closes_its_http_client_only_when_it_created_it():
    provided = mock_http_client(lambda _r: json_response(200, {}))
    peek = PeekAccessService(config(http_client=provided))
    await peek.aclose()
    assert not provided.is_closed

    owned = PeekAccessService(config())
    inner = owned._http.client
    await owned.aclose()
    assert inner.is_closed


# ─── verify_peek_auth_token ──────────────────────────────────────────────────


def test_returns_fully_typed_claims_from_a_valid_registry_token():
    claims = PeekAccessService(config()).verify_peek_auth_token(mint("secret"))
    assert claims.install_id == INSTALL_ID
    assert claims.display_version == "0.0.11"


def test_accepts_the_raw_header_value_with_a_bearer_prefix():
    peek = PeekAccessService(config())
    token = mint("secret")
    assert peek.verify_peek_auth_token(f"Bearer {token}").install_id == INSTALL_ID
    assert peek.verify_peek_auth_token(f"bearer {token}").install_id == INSTALL_ID


def test_maps_the_nested_user_object_to_typed_fields():
    user = PeekAccessService(config()).verify_peek_auth_token(mint("secret")).user
    assert user is not None
    assert user.email == "admin@peek.com"
    assert user.id == "usr_9f21"
    assert user.is_admin is False
    assert user.locale == "en"
    assert user.name == "Admin User"
    assert user.platform == "peek"


@pytest.mark.parametrize(("platform", "expected"), [("cng", "cng"), ("shopify", None)])
def test_propagates_or_normalizes_the_platform_claim(platform: str, expected: str | None):
    token = mint("secret", {"user": {**SAMPLE_USER, "platform": platform}})
    assert PeekAccessService(config()).verify_peek_auth_token(token).user.platform == expected


def test_maps_is_admin_true_correctly():
    token = mint("secret", {"user": {**SAMPLE_USER, "is_admin": True}})
    assert PeekAccessService(config()).verify_peek_auth_token(token).user.is_admin is True


def test_rejects_a_token_signed_with_a_different_secret():
    with pytest.raises(jwt.InvalidSignatureError):
        PeekAccessService(config()).verify_peek_auth_token(mint("wrong-secret"))


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"iss": "wrong-issuer"}, jwt.InvalidIssuerError),
        ({"aud": "wrong-audience"}, jwt.InvalidAudienceError),
        ({"exp": int(time.time()) - 1}, jwt.ExpiredSignatureError),
    ],
)
def test_rejects_wrong_issuer_audience_or_expired(claims: dict[str, Any], error: type[Exception]):
    with pytest.raises(error):
        PeekAccessService(config()).verify_peek_auth_token(mint("secret", **claims))


def test_rejects_a_malformed_token_string():
    with pytest.raises(jwt.InvalidTokenError):
        PeekAccessService(config()).verify_peek_auth_token("not.a.jwt")


@pytest.mark.parametrize("sentinel", ["", "null", "NULL", "  "])
def test_normalizes_a_sentinel_id_to_none_without_raising(sentinel: str):
    token = mint("secret", {"user": {**SAMPLE_USER, "id": sentinel}})
    assert PeekAccessService(config()).verify_peek_auth_token(token).user.id is None


def test_maps_a_user_block_that_omits_id_keeping_the_other_fields():
    user_without_id = {k: v for k, v in SAMPLE_USER.items() if k != "id"}
    user = PeekAccessService(config()).verify_peek_auth_token(
        mint("secret", {"user": user_without_id})
    ).user
    assert user.id is None
    assert user.email == "admin@peek.com"
    assert user.is_admin is False


def test_returns_none_user_when_the_token_carries_no_user_block():
    token = mint("secret", {"user": None})
    assert PeekAccessService(config()).verify_peek_auth_token(token).user is None


def test_defaults_missing_sub_and_display_version_to_empty_strings():
    token = jwt.encode(
        {"iss": REGISTRY_ISSUER, "aud": REGISTRY_AUDIENCE, "exp": int(time.time()) + 60},
        "secret",
        algorithm="HS256",
    )
    claims = PeekAccessService(config()).verify_peek_auth_token(token)
    assert claims.install_id == ""
    assert claims.display_version == ""


# ─── v2 mode ─────────────────────────────────────────────────────────────────


async def test_v2_uses_the_app_registry_base_url_by_default():
    client, calls = empty_products_client()
    peek = PeekAccessService(config(mode="v2", http_client=client))
    await peek.get_product_service().get_all_products()
    assert str(calls[0].url) == (
        "https://app-registry.peeklabs.com/installations-api/app-1/peek_backoffice_api-v1"
    )


async def test_v2_inserts_the_slug_with_a_custom_base_url():
    client, calls = empty_products_client()
    peek = PeekAccessService(
        config(mode="v2", http_client=client, base_url="https://app-registry.prod.peeklabs.com/installations-api")
    )
    await peek.get_product_service().get_all_products()
    assert str(calls[0].url) == (
        "https://app-registry.prod.peeklabs.com/installations-api/app-1/peek_backoffice_api-v1"
    )


async def test_v2_still_mints_and_sends_a_bearer_token():
    client, calls = empty_products_client()
    peek = PeekAccessService(config(mode="v2", http_client=client))
    await peek.get_product_service().get_all_products()
    assert calls[0].headers["X-Peek-Auth"].startswith("Bearer ")


# ─── api_url mode ────────────────────────────────────────────────────────────


def api_url_config(api_url: str, **overrides: Any) -> PeekAccessServiceConfig:
    return PeekAccessServiceConfig(
        install_id="install-1", jwt_secret="secret", issuer="Peek Test", api_url=api_url, **overrides
    )


@pytest.mark.parametrize("api_url", [API_URL, f"{API_URL}/peek-backoffice-api-v1"])
async def test_api_url_posts_to_the_base_with_the_peek_slug_appended(api_url: str):
    client, calls = empty_products_client()
    peek = PeekAccessService(api_url_config(api_url, http_client=client))
    await peek.get_product_service().get_all_products()
    assert str(calls[0].url) == RESOLVED_URL
    assert calls[0].headers["X-Peek-Auth"].startswith("Bearer ")
    assert "pk-api-key" not in calls[0].headers


def test_api_url_raises_when_it_carries_a_different_platforms_slug():
    with pytest.raises(ValueError, match="backoffice"):
        PeekAccessService(api_url_config(f"{API_URL}/cng_backoffice_api-v1"))


def test_api_url_needs_neither_app_id_nor_gateway_key():
    PeekAccessService(api_url_config(API_URL))


async def test_api_url_takes_precedence_over_base_url_and_mode():
    client, calls = empty_products_client()
    peek = PeekAccessService(
        config(mode="v2", base_url="https://ignored.example/gql", api_url=API_URL, http_client=client)
    )
    await peek.get_product_service().get_all_products()
    assert str(calls[0].url) == RESOLVED_URL


# ─── PII ─────────────────────────────────────────────────────────────────────


async def test_defaults_to_pii_off_so_payment_operations_are_disabled():
    peek = PeekAccessService(config())
    with pytest.raises(PiiAccessDisabledError):
        await peek.get_booking_service().get_payments_on_file("b_abc")


async def test_enables_payment_operations_when_full_customer_access_is_set():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return json_response(200, {"data": {"sales": {"edges": []}}})

    peek = PeekAccessService(
        config(
            http_client=mock_http_client(handler),
            access_options=AccessOptions(full_customer_access=True),
        )
    )
    await peek.get_booking_service().get_payments_on_file("b_abc")
    assert calls, "the gated read reached the transport"
