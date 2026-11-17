"""Account-user operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_account_user_service()`` rather
than constructing it directly — the access service wires in the authenticated,
shared transport. Only active users are returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from peek_app_utilities.internal.peek.account_users.account_user_converter import (
    from_account_user_node,
    from_account_user_nodes,
)
from peek_app_utilities.internal.peek.account_users.account_user_queries import (
    USER_BY_FILTER_QUERY,
    USER_QUERY,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.models.peek.account_user import AccountUser

DEFAULT_PAGE_SIZE: Final = 50
"""Default page size for cursor-paginated account users."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountUserServiceOptions:
    """Tuning options for an :class:`AccountUserService`."""

    page_size: int | None = None
    """Page size for cursor pagination. Default: 50."""


class AccountUserService:
    def __init__(
        self, client: GraphQLClient, options: AccountUserServiceOptions | None = None
    ) -> None:
        self._client = client
        page_size = options.page_size if options is not None else None
        self._page_size = page_size if page_size is not None else DEFAULT_PAGE_SIZE

    async def get_all(self) -> list[AccountUser]:
        """Returns all active account users, walking the cursor pagination to the
        end. Inactive users are omitted."""
        users: list[AccountUser] = []
        after: str | None = None

        # Cursor pagination is inherently sequential: each page yields the next cursor.
        while True:
            body = await self._client.request(
                SALES_ENDPOINT, USER_QUERY, {"first": self._page_size, "after": after}
            )
            connection = _connection(body)
            edges = connection.get("edges") or []
            if not edges:
                break

            users.extend(from_account_user_nodes([edge.get("node") for edge in edges]))

            page_info = connection.get("pageInfo") or {}
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                after = page_info["endCursor"]
            else:
                break

        return users

    async def get_by_id(self, user_id: str) -> AccountUser | None:
        """Returns a single active account user by id, or ``None`` when no active
        user matches."""
        body = await self._client.request(
            SALES_ENDPOINT,
            USER_BY_FILTER_QUERY,
            {"first": self._page_size, "filter": {"ids": [user_id]}},
        )
        edges = _connection(body).get("edges") or []
        if not edges:
            return None
        return from_account_user_node(edges[0].get("node"))


def _connection(body: dict[str, Any]) -> dict[str, Any]:
    """The ``accountUsers`` connection of a response body, or ``{}``."""
    data = body.get("data") or {}
    connection: dict[str, Any] = data.get("accountUsers") or {}
    return connection
