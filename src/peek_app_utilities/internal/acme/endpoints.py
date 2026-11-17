"""Endpoint routing for the ACME backoffice REST API. Shared across the ACME
resources so each value lives in exactly one place, with
:data:`ACME_API_ENDPOINTS` as the simple lookup a new ACME API extends.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.internal.api_endpoints import ApiEndpoints

ACME_EXTENDABLE_SLUG: Final = "acme_backoffice_api-v1"
"""Routing slug inserted between the base API URL and the REST path."""

ACME_TEMPLATES_ENDPOINT: Final = "templates"
"""Endpoint key for the event-template names list."""

TEMPLATES_PATH: Final = "v2/b2b/event/templates/names?pageSize=-1&page=1"
"""REST path (relative to the slug) for the event-template names list."""

ACME_API_ENDPOINTS: Final = ApiEndpoints({ACME_TEMPLATES_ENDPOINT: ACME_EXTENDABLE_SLUG})
"""The ACME endpoint lookup — add a new ACME API by adding one entry."""
