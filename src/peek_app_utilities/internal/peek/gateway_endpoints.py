"""Endpoint routing for the Peek backoffice GraphQL API. Every current operation
routes through the ``sales`` endpoint; the endpoint key and slugs live here so
they sit in exactly one place, and :func:`peek_api_endpoints` is the simple
lookup a new Peek API extends.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.internal.api_endpoints import ApiEndpoints

SALES_ENDPOINT: Final = "sales"
"""The GraphQL endpoint key every current Peek operation routes through."""

V2_EXTENDABLE_SLUG: Final = "peek_backoffice_api-v1"
"""Registry routing slug for the ``sales`` endpoint (v2 / app-endpoint mode)."""


def peek_api_endpoints(use_registry_slug: bool) -> ApiEndpoints:
    """Builds the Peek endpoint lookup for a transport generation.

    - **Registry mode** (``use_registry_slug`` — v2 or an app-endpoint
      ``api_url``): the ``sales`` endpoint routes through the
      ``peek_backoffice_api-v1`` slug appended to the base API URL.
    - **Legacy v1 mode**: the backoffice-GraphQL gateway has no extendable slug,
      so ``sales`` sits directly under the base (``base/sales``).
    """
    return ApiEndpoints(
        {SALES_ENDPOINT: V2_EXTENDABLE_SLUG if use_registry_slug else SALES_ENDPOINT}
    )
