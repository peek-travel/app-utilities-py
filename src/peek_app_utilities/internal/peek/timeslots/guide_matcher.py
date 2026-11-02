"""Pure guide-matching logic: resolves a caller-supplied guide identifier to a
resource-pool id. A guide may be referenced by resource-pool id, by backing
account-user id, or by name (directly or via an account user).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from peek_app_utilities.models.peek.resource_pool import ResourcePool


class NamedUser(Protocol):
    """Anything with an ``id`` and a ``name`` (e.g. an ``AccountUser``)."""

    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...


def match_guide_to_resource_pool(
    guide_id: str,
    guide_resource_pools: Sequence[ResourcePool],
    account_users: Sequence[NamedUser],
) -> str | None:
    """Resolves ``guide_id`` to a resource-pool id using ``guide_resource_pools``
    (resource pools already filtered to the guide category) and
    ``account_users``. Returns the matched pool id, or ``None`` when nothing
    matches."""
    # Direct resource-pool id match.
    direct_id_match = _find_pool(guide_resource_pools, lambda pool: pool.id == guide_id)
    if direct_id_match is not None:
        return direct_id_match.id

    # Match by backing account-user id.
    account_user_match = _find_pool(
        guide_resource_pools,
        lambda pool: pool.account_user is not None and pool.account_user.id == guide_id,
    )
    if account_user_match is not None:
        return account_user_match.id

    # Match by pool name.
    name_match = _find_pool(guide_resource_pools, lambda pool: pool.name == guide_id)
    if name_match is not None:
        return name_match.id

    # Resolve via an account user, then match its pool by id or name.
    matched_user = next((user for user in account_users if user.id == guide_id), None)
    if matched_user is not None:
        user_id_match = _find_pool(
            guide_resource_pools,
            lambda pool: pool.account_user is not None and pool.account_user.id == matched_user.id,
        )
        # Unreachable in practice: the earlier account-user id match already
        # returns when a pool's account_user.id equals the guide id; kept for
        # source parity with the TypeScript matcher.
        if user_id_match is not None:  # pragma: no cover
            return user_id_match.id

        user_name_match = _find_pool(
            guide_resource_pools, lambda pool: pool.name == matched_user.name
        )
        if user_name_match is not None:
            return user_name_match.id

    return None


def _find_pool(
    pools: Sequence[ResourcePool], predicate: Callable[[ResourcePool], bool]
) -> ResourcePool | None:
    return next((pool for pool in pools if predicate(pool)), None)
