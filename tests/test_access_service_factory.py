from dataclasses import dataclass

import httpx
import pytest

from peek_app_utilities.access_service_factory import (
    InstallAccessConfig,
    create_access_service_for_install,
)
from peek_app_utilities.acme_access_service import AcmeAccessService
from peek_app_utilities.cng_access_service import CngAccessService
from peek_app_utilities.peek_access_service import PeekAccessService
from tests.conftest import json_response, mock_http_client

CREDS = InstallAccessConfig(jwt_secret="secret", issuer="app-name")
API_URL = "https://app-registry.sandbox.peeklabs.com/installations-api/demo-app"


@dataclass(frozen=True)
class Target:
    platform: str | None
    api_url: str
    install_id: str


@pytest.mark.parametrize(
    ("platform", "cls"),
    [("peek", PeekAccessService), ("cng", CngAccessService), ("acme", AcmeAccessService)],
)
def test_routes_each_platform_to_its_access_service(platform: str, cls: type):
    service = create_access_service_for_install(Target(platform, API_URL, "install-1"), CREDS)  # type: ignore[arg-type]
    assert isinstance(service, cls)


async def test_wires_the_installs_api_url_as_the_service_endpoint():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return json_response(200, {"data": {"activities": []}})

    config = InstallAccessConfig(
        jwt_secret="secret", issuer="app-name", http_client=mock_http_client(handler)
    )
    service = create_access_service_for_install(Target("peek", API_URL, "install-1"), config)  # type: ignore[arg-type]
    assert isinstance(service, PeekAccessService)
    await service.get_product_service().get_all_activities()

    # Peek POSTs to the api_url with the platform extendable slug appended.
    assert calls[0] == f"{API_URL}/peek_backoffice_api-v1"


@pytest.mark.parametrize("platform", [None, "newbrand"])
def test_raises_on_an_unknown_or_missing_platform(platform: str | None):
    with pytest.raises(ValueError, match="unknown or missing platform"):
        create_access_service_for_install(Target(platform, API_URL, "install-9"), CREDS)  # type: ignore[arg-type]


def test_peek_only_fields_are_dropped_for_rest_platforms():
    config = InstallAccessConfig(
        jwt_secret="secret", issuer="app-name", gateway_key="gk", item_options_page_size=10
    )
    service = create_access_service_for_install(Target("cng", API_URL, "install-1"), config)  # type: ignore[arg-type]
    assert isinstance(service, CngAccessService)
