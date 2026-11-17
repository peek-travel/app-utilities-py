"""Review operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_review_service()``.
"""

from __future__ import annotations

from typing import Final

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.reviews.review_converter import (
    from_activity_review_summary_nodes,
    from_review_node,
)
from peek_app_utilities.internal.peek.reviews.review_cursor import encode_cursor
from peek_app_utilities.internal.peek.reviews.review_queries import (
    REVIEW_SUMMARIES_QUERY,
    ReviewsVariablesParams,
    build_reviews_query,
    build_reviews_variables,
)
from peek_app_utilities.models.peek.review import ProductReviewSummary, Review

DEFAULT_REVIEW_COUNT: Final = 50
"""Number of reviews returned when ``review_count`` is omitted."""
MIN_REVIEW_COUNT: Final = 1
"""Smallest allowed ``review_count``."""
MAX_REVIEW_COUNT: Final = 50
"""Largest allowed ``review_count`` (a single API page)."""

ERROR_PRODUCT_ID_REQUIRED: Final = "productId is required"
ERROR_INVALID_REVIEW_COUNT: Final = (
    f"reviewCount must be an integer between {MIN_REVIEW_COUNT} and {MAX_REVIEW_COUNT}"
)
ERROR_INVALID_REVIEW_OFFSET: Final = "reviewOffset must be a non-negative integer"


def _is_integer(value: object) -> bool:
    """``Number.isInteger`` analogue: ``True`` for an ``int`` (not a ``bool``)."""
    return isinstance(value, int) and not isinstance(value, bool)


class ReviewService:
    """Reads activity reviews, which the API returns newest-first (descending
    ``reviewedAt``). :meth:`get_reviews` fetches a single page of up to
    ``review_count`` reviews, skipping the first ``review_offset`` of them via
    the connection cursor.

    Obtain an instance via ``PeekAccessService.get_review_service()``.
    """

    def __init__(self, client: GraphQLClient, access_options: ResolvedAccessOptions) -> None:
        self._client = client
        # Whether reviewer PII (name/email) is requested.
        self._full_customer_access = access_options.full_customer_access

    async def get_reviews(
        self,
        product_id: str,
        review_count: int = DEFAULT_REVIEW_COUNT,
        review_offset: int = 0,
    ) -> list[Review]:
        """Returns up to ``review_count`` reviews for an activity in **descending
        order by review date (newest first)**, skipping the ``review_offset``
        newest reviews before collecting.

        The API cursor resumes *after* a given absolute offset, so to skip the
        first ``review_offset`` reviews the request is anchored on the review
        just before the window. A ``review_offset`` of 0 needs no cursor and is
        sent without one.

        :param product_id: The activity (product) id to fetch reviews for.
        :param review_count: How many reviews to return (1-50). Default: 50.
        :param review_offset: How many of the newest reviews to skip first
            (0-based). Default: 0 (start at the newest review).
        :raises ValueError: when ``product_id`` is empty, ``review_count`` is not
            an integer in 1-50, or ``review_offset`` is not a non-negative integer.

        Example::

            reviews = await peek.get_review_service().get_reviews(
                "87cdf37f-1872-42cb-b0bd-518312624fc1", 25, 50
            )
        """
        self._validate(product_id, review_count, review_offset)

        after = encode_cursor(review_offset - 1, review_count) if review_offset > 0 else None

        body = await self._client.request(
            SALES_ENDPOINT,
            build_reviews_query(self._full_customer_access),
            build_reviews_variables(
                ReviewsVariablesParams(activity_id=product_id, first=review_count, after=after)
            ),
        )

        reviews = (body.get("data") or {}).get("reviews") or {}
        edges = reviews.get("edges") or []
        return [from_review_node(edge["node"]) for edge in edges]

    async def get_all_review_summaries(self) -> list[ProductReviewSummary]:
        """Returns an aggregate review summary for **every** activity — its
        average rating and the count of reviews at each star level. This reads
        the same activity list as ``get_all_products``; it carries no per-review
        detail or PII, so it is unaffected by ``full_customer_access``. An
        activity with no reviews comes back with a ``None`` ``avg_rating`` and
        zero counts.

        Example::

            summaries = await peek.get_review_service().get_all_review_summaries()
            for s in summaries:
                print(s.product_name, s.avg_rating, s.count_total)
        """
        body = await self._client.request(SALES_ENDPOINT, REVIEW_SUMMARIES_QUERY, {})
        return from_activity_review_summary_nodes((body.get("data") or {}).get("activities") or [])

    @staticmethod
    def _validate(product_id: str, review_count: int, review_offset: int) -> None:
        if not product_id:
            raise ValueError(ERROR_PRODUCT_ID_REQUIRED)
        if (
            not _is_integer(review_count)
            or review_count < MIN_REVIEW_COUNT
            or review_count > MAX_REVIEW_COUNT
        ):
            raise ValueError(ERROR_INVALID_REVIEW_COUNT)
        if not _is_integer(review_offset) or review_offset < 0:
            raise ValueError(ERROR_INVALID_REVIEW_OFFSET)
