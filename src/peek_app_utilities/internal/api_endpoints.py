"""A platform's tiny map of **API endpoint key → relative path** (the "slug"
inserted between the install's base API URL and the endpoint's own path).

The base API URL is the install's app endpoint with no routing segment — the
install webhook's ``api_url`` (with any slug stripped back off), or
``base_url/app_id`` when built from the deprecated defaults. Each service class
resolves *its own* slug through this lookup, so two services on the same
platform can route through different slugs. Adding a new API — even one on a
different slug than its siblings — is a single entry here.

An empty-string path means the endpoint sits directly on the base with no slug
(e.g. the legacy Peek v1 GraphQL gateway, which has no extendable slug).
"""

from __future__ import annotations

from collections.abc import Mapping


class ApiEndpoints:
    """Maps endpoint keys to the relative slug appended to the base API URL."""

    def __init__(self, paths: Mapping[str, str]) -> None:
        self._paths: dict[str, str] = dict(paths)

    def path_for(self, endpoint: str) -> str:
        """The relative path (slug) for ``endpoint``, appended to the base API URL."""
        return self._paths[endpoint]


def join_url(*parts: str) -> str:
    """Joins URL path parts with single slashes, dropping empty parts so an absent
    slug never produces a ``//``. The base keeps its scheme's ``//`` intact
    because it is passed as one already-joined part."""
    return "/".join(part for part in parts if part)
