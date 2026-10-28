"""Clean data models for Peek activity reviews."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Guide:
    """A guide credited on a review."""

    id: str
    """Guide id (e.g. ``u_y6e4r``)."""
    name: str
    """Guide display name."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Review:
    """A single customer review for an activity (product)."""

    id: str
    """Review id (e.g. ``rvw_359erv``)."""
    product_id: str
    """Activity (product) id the review is for."""
    product_name: str
    """Activity (product) name."""
    guides: list[Guide]
    """Guides credited on the review. May be empty."""
    customer_name: str | None
    """Customer name. ``None`` when absent or when ``full_customer_access`` is off."""
    customer_email: str | None
    """Customer email. ``None`` when absent or when ``full_customer_access`` is off."""
    activity_date: str
    """Activity date (``YYYY-MM-DD``), derived from ``purchasedFor``."""
    review_date: str
    """Review date (``YYYY-MM-DD``), derived from ``reviewedAt``."""
    rating: float
    """Star rating, 1-5."""
    comment: str | None
    """Free-text review. May be ``None``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductReviewSummary:
    """Aggregate review statistics for a single activity (product), as returned
    by ``ReviewService.get_all_review_summaries``. Carries no per-review detail
    or PII — just the rating distribution and average."""

    product_id: str
    """Activity (product) id the summary is for."""
    product_name: str
    """Activity (product) name."""
    avg_rating: float | None
    """Average star rating as a decimal, or ``None`` when there are no ratings."""
    count_total: int
    """Total number of reviews."""
    count_one_star: int
    """Number of 1-star reviews."""
    count_two_star: int
    """Number of 2-star reviews."""
    count_three_star: int
    """Number of 3-star reviews."""
    count_four_star: int
    """Number of 4-star reviews."""
    count_five_star: int
    """Number of 5-star reviews."""
