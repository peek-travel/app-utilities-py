"""Pure function flattening raw membership nodes into the clean
:class:`Membership` model — one record per variant.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from peek_app_utilities.internal.peek.memberships.membership_queries import (
    MembershipNode,
    MembershipVariantNode,
)
from peek_app_utilities.models.peek.membership import Membership


def from_memberships_response(response: Mapping[str, Any] | None) -> list[Membership]:
    """Flattens a memberships response into one :class:`Membership` per variant."""
    memberships: list[MembershipNode] = (response or {}).get("memberships") or []
    return [
        _from_variant(membership, variant)
        for membership in memberships
        for variant in membership.get("membershipVariants") or []
    ]


def _from_variant(membership: MembershipNode, variant: MembershipVariantNode) -> Membership:
    return Membership(
        id=membership.get("id") or "",
        membership_variant_id=variant.get("id") or "",
        description=variant.get("description"),
        external_name=variant.get("externalName") or "",
        image_url=variant.get("imageUrl"),
        internal_name=variant.get("internalName") or "",
        display_name=membership.get("name") or "",
    )
