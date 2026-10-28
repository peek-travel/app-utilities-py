import httpx
import pytest

from peek_app_utilities.acme_access_service import AcmeAccessService, AcmeAccessServiceConfig
from peek_app_utilities.models.acme.product import AcmeActivity
from tests.conftest import json_response, mock_http_client

BASE = {
    "install_id": "install-123",
    "jwt_secret": "secret",
    "issuer": "app-name",
    "app_id": "app-1",
}
TEMPLATES_PATH = "v2/b2b/event/templates/names?pageSize=-1&page=1"
PUBLISHED = {
    "id": "61f99bfe62bd1f467c39771f",
    "name": "General Admission",
    "type": "standard",
    "admissionType": "standard",
    "reviewState": "published",
    "colorCategory": {"backgroundColor": "#00695c", "textColor": "#ffffff"},
}


def config(**overrides: object) -> AcmeAccessServiceConfig:
    return AcmeAccessServiceConfig(**{**BASE, **overrides})  # type: ignore[arg-type]


def recording_client(body: object) -> tuple[httpx.AsyncClient, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return json_response(200, body)

    return mock_http_client(handler), calls


@pytest.mark.parametrize("field", ["install_id", "jwt_secret", "issuer", "app_id"])
def test_raises_when_a_required_field_is_empty(field: str):
    with pytest.raises(ValueError, match=f'"{field}" is required'):
        AcmeAccessService(config(**{field: ""}))


def test_memoizes_the_product_service():
    acme = AcmeAccessService(config())
    assert acme.get_product_service() is acme.get_product_service()


async def test_hits_the_default_app_registry_base_url():
    client, calls = recording_client({"list": [PUBLISHED]})
    async with AcmeAccessService(config(http_client=client)) as acme:
        activities = await acme.get_product_service().get_all_activities()

    assert activities == [
        AcmeActivity(
            product_id="61f99bfe62bd1f467c39771f",
            name="General Admission",
            type="standard",
            color="#00695c",
            tickets=[],
        )
    ]
    assert calls[0] == (
        "https://app-registry.peeklabs.com/installations-api/app-1/acme_backoffice_api-v1/"
        + TEMPLATES_PATH
    )


async def test_honors_a_custom_base_url():
    client, calls = recording_client({"list": []})
    acme = AcmeAccessService(config(base_url="https://custom.test/base", http_client=client))
    await acme.get_product_service().get_all_activities()
    assert calls[0] == f"https://custom.test/base/app-1/acme_backoffice_api-v1/{TEMPLATES_PATH}"


async def test_treats_api_url_as_the_base_and_inserts_the_acme_slug():
    client, calls = recording_client({"list": []})
    acme = AcmeAccessService(
        AcmeAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://app-registry.sandbox.peeklabs.com/installations-api/demo-app",
            http_client=client,
        )
    )
    await acme.get_product_service().get_all_activities()
    assert calls[0] == (
        "https://app-registry.sandbox.peeklabs.com/installations-api/demo-app/"
        f"acme_backoffice_api-v1/{TEMPLATES_PATH}"
    )


async def test_strips_an_already_present_acme_slug_back_to_the_base():
    client, calls = recording_client({"list": []})
    acme = AcmeAccessService(
        AcmeAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://x.test/demo-app/acme-backoffice-api-v1",
            http_client=client,
        )
    )
    await acme.get_product_service().get_all_activities()
    assert calls[0] == f"https://x.test/demo-app/acme_backoffice_api-v1/{TEMPLATES_PATH}"


def test_raises_when_api_url_carries_a_different_platforms_slug():
    with pytest.raises(ValueError, match="backoffice"):
        AcmeAccessService(
            AcmeAccessServiceConfig(
                install_id="install-123",
                jwt_secret="secret",
                issuer="app-name",
                api_url="https://x.test/demo-app/cng_backoffice_api-v1",
            )
        )


def test_needs_no_app_id_when_api_url_is_set():
    AcmeAccessService(
        AcmeAccessServiceConfig(
            install_id="install-123",
            jwt_secret="secret",
            issuer="app-name",
            api_url="https://x.test/base",
        )
    )


async def test_aclose_closes_only_a_package_owned_client():
    provided = mock_http_client(lambda _r: json_response(200, {}))
    acme = AcmeAccessService(config(http_client=provided))
    await acme.aclose()
    assert not provided.is_closed

    owned = AcmeAccessService(config())
    inner = owned._http.client
    await owned.aclose()
    assert inner.is_closed
