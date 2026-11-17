"""Pure, I/O-free mapping from raw review nodes to the clean :class:`Review`
model. No network, no logging, no clock access.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from peek_app_utilities.internal.peek.reviews.review_queries import (
    ActivityReviewSummaryNode,
    ReviewNode,
)
from peek_app_utilities.models.peek.review import Guide, ProductReviewSummary, Review

ISO_DATE_LENGTH: Final = 10
"""Length of an ISO ``YYYY-MM-DD`` date prefix."""


def to_date_only(iso_date_time: str) -> str:
    """Extracts the ``YYYY-MM-DD`` date prefix from an ISO date-time string."""
    return iso_date_time[:ISO_DATE_LENGTH]


def from_review_node(node: ReviewNode) -> Review:
    """Maps a raw review node to the clean :class:`Review` model."""
    activity = node.get("activity") or {}
    guides = [
        Guide(id=guide.get("id") or "", name=guide.get("name") or "")
        for guide in node.get("guides") or []
    ]
    return Review(
        id=node.get("id") or "",
        product_id=activity.get("id") or "",
        product_name=activity.get("name") or "",
        guides=guides,
        customer_name=node.get("name"),
        customer_email=node.get("email"),
        activity_date=to_date_only(node.get("purchasedFor") or ""),
        review_date=to_date_only(node.get("reviewedAt") or ""),
        rating=node.get("rating") or 0,
        comment=node.get("comment"),
    )


def from_activity_review_summary_node(node: ActivityReviewSummaryNode) -> ProductReviewSummary:
    """Maps a raw activity node to a clean :class:`ProductReviewSummary`. A
    missing ``reviewMeta`` (an activity with no reviews) collapses to a ``None``
    average and zero counts."""
    meta = node.get("reviewMeta") or {}
    return ProductReviewSummary(
        product_id=node.get("id") or "",
        product_name=node.get("name") or "",
        avg_rating=meta.get("avgRating"),
        count_total=meta.get("count") or 0,
        count_one_star=meta.get("oneStar") or 0,
        count_two_star=meta.get("twoStar") or 0,
        count_three_star=meta.get("threeStar") or 0,
        count_four_star=meta.get("fourStar") or 0,
        count_five_star=meta.get("fiveStar") or 0,
    )


def from_activity_review_summary_nodes(
    nodes: Iterable[ActivityReviewSummaryNode],
) -> list[ProductReviewSummary]:
    """Maps every activity node to a :class:`ProductReviewSummary`."""
    return [from_activity_review_summary_node(node) for node in nodes]
