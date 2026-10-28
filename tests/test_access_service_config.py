import pytest

from peek_app_utilities.access_service_config import (
    DEFAULT_RETRY_DELAYS_MS,
    DEFAULT_TOKEN_REFRESH_LEEWAY_SECONDS,
    DEFAULT_TOKEN_TTL_SECONDS,
    BaseAccessServiceConfig,
    create_http_client,
    create_token_manager,
    require_non_empty,
    resolve_base_api_url,
    resolve_retry_delays,
)

PEEK_SLUG = "peek_backoffice_api-v1"
SERVICE = "PeekAccessService"


def test_returns_the_url_unchanged_when_it_carries_no_slug():
    url = "https://apps.peek.com/installations-api/google-things-to-do-integration"
    assert resolve_base_api_url(url, PEEK_SLUG, SERVICE) == url


def test_trims_a_trailing_slash():
    assert resolve_base_api_url("https://x.test/demo-app/", PEEK_SLUG, SERVICE) == (
        "https://x.test/demo-app"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://x.test/demo-app/peek_backoffice_api-v1",
        "https://x.test/demo-app/peek-backoffice-api-v1",
        "https://x.test/demo-app/peek_backoffice_api-v1/",
    ],
)
def test_strips_this_platforms_slug_back_to_the_base(url: str):
    assert resolve_base_api_url(url, PEEK_SLUG, SERVICE) == "https://x.test/demo-app"


def test_raises_when_the_url_carries_a_different_platforms_slug():
    with pytest.raises(ValueError, match=r'"cng".*"peek"'):
        resolve_base_api_url("https://x.test/demo-app/cng_backoffice_api-v1", PEEK_SLUG, SERVICE)


def test_require_non_empty_names_the_field_and_service():
    with pytest.raises(ValueError, match=r'PeekAccessService: "install_id" is required'):
        require_non_empty("", "install_id", SERVICE)
    with pytest.raises(ValueError):
        require_non_empty(None, "install_id", SERVICE)
    require_non_empty("ok", "install_id", SERVICE)


def _config(**overrides: object) -> BaseAccessServiceConfig:
    base: dict[str, object] = {"install_id": "i", "jwt_secret": "s", "issuer": "app"}
    base.update(overrides)
    return BaseAccessServiceConfig(**base)  # type: ignore[arg-type]


def test_create_token_manager_applies_the_shared_defaults():
    manager = create_token_manager(_config())
    opts = manager._options
    assert opts.ttl_seconds == DEFAULT_TOKEN_TTL_SECONDS
    assert opts.leeway_seconds == DEFAULT_TOKEN_REFRESH_LEEWAY_SECONDS
    assert opts.issuer == "app"
    assert opts.install_id == "i"


def test_create_token_manager_honours_overrides():
    manager = create_token_manager(_config(token_ttl_seconds=10, token_refresh_leeway_seconds=2))
    assert manager._options.ttl_seconds == 10
    assert manager._options.leeway_seconds == 2


def test_resolve_retry_delays_defaults_and_overrides():
    assert resolve_retry_delays(_config()) == DEFAULT_RETRY_DELAYS_MS
    assert resolve_retry_delays(_config(retry_delays_ms=[5, 6])) == (5, 6)


async def test_create_http_client_returns_a_closable_async_client():
    client = create_http_client()
    await client.aclose()
