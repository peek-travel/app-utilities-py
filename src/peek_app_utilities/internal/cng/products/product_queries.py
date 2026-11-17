"""Raw CNG REST response shapes for products. Internal implementation detail of
the package — never re-exported from the public entry point.

Confirmed against a live ``api/v2/app-registry/products`` sample. The payload is
a Laravel-style resource collection (``{"data": [...]}``) of snake_case product
rows. Only the fields the converter reads are typed here; the converter is
written defensively so missing/null fields degrade rather than raise.
"""

from __future__ import annotations

from typing import TypedDict


class ProductNode(TypedDict, total=False):
    """A single product row as returned by the app-registry products endpoint."""

    id: int | str | None
    """Stable product id. Numeric in the REST payload; stringified by the converter."""
    name: str | None
    slug: str | None
    status: str | None
    access_control_color_hex: str | None
    custom_access_control_color: bool | None


class ProductsResponse(TypedDict, total=False):
    """The products list payload — a ``{"data": [...]}`` resource collection."""

    data: list[ProductNode] | None
