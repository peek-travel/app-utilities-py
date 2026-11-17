"""Raw ACME REST response shapes for event templates. Internal implementation
detail of the package — never re-exported from the public entry point.

The ``v2/b2b/event/templates/names`` endpoint returns a ``{"list": [...]}``
envelope. Each node carries a ``reviewState``; only ``"published"`` templates
are surfaced as activities (see the converter).
"""

from __future__ import annotations

from typing import Final, TypedDict

PUBLISHED_REVIEW_STATE: Final = "published"
"""The published review state — the only templates surfaced as activities."""


class ColorCategory(TypedDict, total=False):
    backgroundColor: str | None
    textColor: str | None


class TemplateNode(TypedDict, total=False):
    """A single template node as returned by the templates/names endpoint."""

    id: str | None
    name: str | None
    type: str | None
    admissionType: str | None
    reviewState: str | None
    colorCategory: ColorCategory | None


class TemplatesResponse(TypedDict, total=False):
    """The templates list payload (``{"list": [...]}``); a bare array is tolerated too."""

    list: list[TemplateNode] | None
