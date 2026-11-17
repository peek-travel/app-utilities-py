import httpx
import pytest

from peek_app_utilities.cng_access_service import CngAccessService, CngAccessServiceConfig
from peek_app_utilities.models.cng.product import Activity
from tests.conftest import json_response, mock_http_client

BASE = {
    "install_id": "install-123",
    "jwt_secret": "secret",
    "issuer": "app-name",
    "app_id": "app-1",
}


def config(**overrides: object) -> CngAccessServiceConfig:
    return CngAccessServiceConfig(**{**BASE, **overrides})  # type: ignore[arg-type]


def recording_client(body: object) -> tuple[httpx.AsyncClient, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return json_response(200, body)

    return mock_http_client(handler), calls


@pytest.mark.parametrize("field", ["install_id", "jwt_secret", "issuer", "app_id"])
def test_raises_when_a_required_field_is_empty(field: str):
    with pytest.raises(ValueError, match=f'"{field}" is required'):
        CngAccessService(config(**{field: ""}))


def test_memoizes_the_product_service():
    cng = CngAccessService(config())
    assert cng.get_product_service() is cng.get_product_service()


async def test_hits_the_default_app_registry_base_url():
    client, calls = recording_client({"data": [{"id": 1000171, "name": "Tour"}]})
    async with CngAccessService(config(http_client=client)) as cng:
        activities = await cng.get_product_service().get_all_activities()

    assert activities == [
        Activity(product_id="1000171", name="Tour", type="ACTIVITY", color="", tickets=[])
    ]
    assert calls[0] == (
        "https://app-registry.peeklabs.com/installations-api/app-1/cng_backoffice_api-v1/"
        "api/v2/app-registry/products?active=1"
    )


async def test_honors_a_custom_base_url():
    client, calls = recording_client({"data": []})
    cng = CngAccessService(config(base_url="https://custom.test/base", http_client=client))
    await cng.get_product_service().get_all_activities()
    assert calls[0] == (
        "https://custom.test/base/app-1/cng_backoffice_api-v1/api/v2/app-registry/products?active=1"
    )


async def test_treats_api_url_as_the_base_and_inserts_the_cng_slug():
    client, calls = recording_client({"data": []})
    cng = CngAccessService(
        CngAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://app-registry.sandbox.peeklabs.com/installations-api/demo-app",
            http_client=client,
        )
    )
    await cng.get_product_service().get_all_activities()
    assert calls[0] == (
        "https://app-registry.sandbox.peeklabs.com/installations-api/demo-app/"
        "cng_backoffice_api-v1/api/v2/app-registry/products?active=1"
    )


async def test_strips_an_already_present_cng_slug_back_to_the_base():
    client, calls = recording_client({"data": []})
    cng = CngAccessService(
        CngAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://x.test/demo-app/cng-backoffice-api-v1",
            http_client=client,
        )
    )
    await cng.get_product_service().get_all_activities()
    assert calls[0] == (
        "https://x.test/demo-app/cng_backoffice_api-v1/api/v2/app-registry/products?active=1"
    )


def test_raises_when_api_url_carries_a_different_platforms_slug():
    with pytest.raises(ValueError, match=r'"peek".*"cng"'):
        CngAccessService(
            CngAccessServiceConfig(
                install_id="install-123",
                jwt_secret="secret",
                issuer="app-name",
                api_url="https://x.test/demo-app/peek_backoffice_api-v1",
            )
        )


def test_needs_no_app_id_when_api_url_is_set():
    CngAccessService(
        CngAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://x.test/base",
        )
    )


async def test_aclose_closes_only_a_package_owned_client():
    provided = mock_http_client(lambda _r: json_response(200, {}))
    cng = CngAccessService(config(http_client=provided))
    await cng.aclose()
    assert not provided.is_closed

    owned = CngAccessService(config())
    inner = owned._http.client
    await owned.aclose()
    assert inner.is_closed
