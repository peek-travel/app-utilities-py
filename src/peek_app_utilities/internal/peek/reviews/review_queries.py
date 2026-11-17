"""Raw Peek GraphQL query and response shapes for activity reviews. Internal —
never re-exported from the public barrel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, TypedDict

_REVIEWER_PII_SELECTION: Final = "name\n          email"
"""The reviewer ``name``/``email`` fields, selected only with full customer access."""


def build_reviews_query(full_customer_access: bool) -> str:
    """Builds the reviews query.

    Fetches a page of reviews, newest-first, optionally filtered by activity and
    resumed from a cursor. The API returns up to ``first`` reviews per page in
    descending ``reviewedAt`` order; pagination walks backwards in time via the
    last edge's ``cursor`` as the next ``after``.

    Without ``full_customer_access``, the reviewer's ``name`` and ``email`` are
    not requested (they come back absent → ``None`` in the converter); the review
    ``comment``, rating, dates, and credited guides are always selected.
    """
    pii = _REVIEWER_PII_SELECTION if full_customer_access else ""
    return f"""
  query Reviews($first: Int, $filter: ReviewFilter, $after: String) {{
    reviews(first: $first, filter: $filter, after: $after) {{
      edges {{
        node {{
          activity {{
            id
            name
          }}
          guides {{
            id
            name
          }}
          id
          {pii}
          rating
          comment
          reviewedAt
          purchasedFor
        }}
        cursor
      }}
    }}
  }}
"""


class ReviewGuideNode(TypedDict, total=False):
    """A guide node as returned by the API."""

    id: str
    name: str


class ReviewActivityNode(TypedDict, total=False):
    id: str
    name: str


class ReviewNode(TypedDict, total=False):
    """A single review node as returned by the API."""

    activity: ReviewActivityNode | None
    guides: list[ReviewGuideNode] | None
    id: str
    name: str | None
    email: str | None
    rating: float
    comment: str | None
    reviewedAt: str
    purchasedFor: str


class ReviewEdge(TypedDict, total=False):
    """A single edge in the reviews connection."""

    node: ReviewNode
    cursor: str


class ReviewsConnection(TypedDict, total=False):
    edges: list[ReviewEdge] | None


class ReviewsResponse(TypedDict, total=False):
    """``data`` payload of :func:`build_reviews_query`."""

    reviews: ReviewsConnection | None


REVIEW_SUMMARIES_QUERY: Final = """
  query ReviewSummaries {
    activities {
      id
      name
      reviewMeta {
        avgRating
        count
        fiveStar
        fourStar
        threeStar
        twoStar
        oneStar
      }
    }
  }
"""
"""Fetches every activity with its aggregate review statistics. The
``activities`` connection is the same list ``get_all_products`` reads; here only
the id, name, and ``reviewMeta`` rating distribution are selected. Carries no
PII, so it is unaffected by ``full_customer_access``."""


class ReviewMetaNode(TypedDict, total=False):
    """An activity's aggregate review statistics as returned by the API."""

    avgRating: float | None
    count: int
    fiveStar: int
    fourStar: int
    threeStar: int
    twoStar: int
    oneStar: int


class ActivityReviewSummaryNode(TypedDict, total=False):
    """A single activity node as returned by :data:`REVIEW_SUMMARIES_QUERY`."""

    id: str
    name: str
    reviewMeta: ReviewMetaNode | None


class ReviewSummariesResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`REVIEW_SUMMARIES_QUERY`."""

    activities: list[ActivityReviewSummaryNode] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewsVariablesParams:
    """Inputs to :func:`build_reviews_variables`."""

    activity_id: str
    first: int
    after: str | None


def build_reviews_variables(params: ReviewsVariablesParams) -> dict[str, Any]:
    """Builds the variables for :func:`build_reviews_query`."""
    return {
        "first": params.first,
        "filter": {"activityIds": [params.activity_id]},
        "after": params.after,
    }
