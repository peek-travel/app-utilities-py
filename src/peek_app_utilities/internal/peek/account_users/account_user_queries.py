"""Raw Peek GraphQL queries and response shapes for account users. Internal —
not re-exported from the public entry point.
"""

from __future__ import annotations

from typing import Final, TypedDict

USER_QUERY: Final = """
  query Sales($first: Int, $after: String) {
    accountUsers(first: $first, after: $after) {
      pageInfo {
        endCursor
        hasNextPage
      }
      edges {
        cursor
        node {
          id
          name
          email
          phone
          status
          assignedActivities {
            id
            name
          }
        }
      }
    }
  }
"""
"""Fetches a cursor-paginated page of account users."""

USER_BY_FILTER_QUERY: Final = """
  query Sales($first: Int, $filter: AccountUsersFilter) {
    accountUsers(first: $first, filter: $filter) {
      edges {
        cursor
        node {
          id
          name
          email
          phone
          status
          assignedActivities {
            id
            name
          }
        }
      }
    }
  }
"""
"""Fetches account users matching a filter (e.g. by id)."""


class AssignedActivityNode(TypedDict, total=False):
    """An ``assignedActivities`` entry of an :class:`AccountUserNode`."""

    id: str | None
    name: str | None


class AccountUserNode(TypedDict, total=False):
    """A single account-user node as returned by the account-user queries."""

    id: str | None
    name: str | None
    email: str | None
    phone: str | None
    status: str | None
    assignedActivities: list[AssignedActivityNode] | None


class AccountUserPageInfo(TypedDict, total=False):
    """Cursor-pagination info of an :class:`AccountUsersConnection`."""

    endCursor: str | None
    hasNextPage: bool | None


class AccountUserEdge(TypedDict, total=False):
    """A single edge of an :class:`AccountUsersConnection`."""

    cursor: str | None
    node: AccountUserNode | None


class AccountUsersConnection(TypedDict, total=False):
    """The ``accountUsers`` connection; ``pageInfo`` is only selected by
    :data:`USER_QUERY`."""

    pageInfo: AccountUserPageInfo | None
    edges: list[AccountUserEdge] | None


class AccountUsersResponse(TypedDict, total=False):
    """The ``data`` payload of the account-user queries."""

    accountUsers: AccountUsersConnection | None
