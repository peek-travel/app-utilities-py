"""Endpoint routing for the CNG backoffice REST API. Shared across the CNG
resources so each value lives in exactly one place, with :data:`CNG_API_ENDPOINTS`
as the simple lookup a new CNG API extends.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.internal.api_endpoints import ApiEndpoints

CNG_EXTENDABLE_SLUG: Final = "cng_backoffice_api-v1"
"""Routing slug inserted between the base API URL and the REST path."""

CNG_PRODUCTS_ENDPOINT: Final = "products"
"""Endpoint key for the app-registry products list."""

PRODUCTS_PATH: Final = "api/v2/app-registry/products?active=1"
"""REST path (relative to the slug) for the app-registry products list.
``active=1`` keeps the gateway from returning inactive/archived products."""

CNG_API_ENDPOINTS: Final = ApiEndpoints({CNG_PRODUCTS_ENDPOINT: CNG_EXTENDABLE_SLUG})
"""The CNG endpoint lookup — add a new CNG API by adding one entry."""
