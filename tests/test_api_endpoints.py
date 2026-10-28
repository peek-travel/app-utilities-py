from peek_app_utilities.internal.api_endpoints import ApiEndpoints, join_url


def test_returns_the_relative_path_for_a_known_endpoint_key():
    endpoints = ApiEndpoints({"sales": "peek_backoffice_api-v1"})
    assert endpoints.path_for("sales") == "peek_backoffice_api-v1"


def test_supports_an_empty_slug():
    endpoints = ApiEndpoints({"sales": ""})
    assert endpoints.path_for("sales") == ""


def test_join_url_joins_parts_with_single_slashes():
    assert join_url("https://x.test/base", "slug", "a/b?c=1") == "https://x.test/base/slug/a/b?c=1"


def test_join_url_drops_empty_parts():
    assert join_url("https://x.test/base", "", "path") == "https://x.test/base/path"
