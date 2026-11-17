from typing import Any, cast

from peek_app_utilities.internal.peek.reviews.review_converter import (
    from_activity_review_summary_node,
    from_activity_review_summary_nodes,
    from_review_node,
    to_date_only,
)
from peek_app_utilities.internal.peek.reviews.review_queries import (
    ActivityReviewSummaryNode,
    ReviewNode,
)
from peek_app_utilities.models.peek.review import Guide, ProductReviewSummary, Review


def node(**overrides: Any) -> ReviewNode:
    base: dict[str, Any] = {
        "activity": {"id": "act-1", "name": "Downtown Bike Tour"},
        "guides": [{"id": "u_y6e4r", "name": "Oskar Bruening"}],
        "id": "rvw_1",
        "name": "Oskar Test",
        "email": "oskar@peek.com",
        "rating": 5,
        "comment": "Great",
        "reviewedAt": "2025-08-06T16:40:49.000000Z",
        "purchasedFor": "2025-08-04T16:30:00.000000Z",
    }
    base.update(overrides)
    return cast(ReviewNode, base)


# ─── to_date_only ────────────────────────────────────────────────────────────


def test_extracts_the_yyyy_mm_dd_prefix():
    assert to_date_only("2025-08-06T16:40:49.000000Z") == "2025-08-06"


# ─── from_review_node ────────────────────────────────────────────────────────


def test_maps_a_fully_populated_node_to_the_clean_model():
    assert from_review_node(node()) == Review(
        id="rvw_1",
        product_id="act-1",
        product_name="Downtown Bike Tour",
        guides=[Guide(id="u_y6e4r", name="Oskar Bruening")],
        customer_name="Oskar Test",
        customer_email="oskar@peek.com",
        activity_date="2025-08-04",
        review_date="2025-08-06",
        rating=5,
        comment="Great",
    )


def test_coerces_null_guides_name_email_comment_to_safe_defaults():
    review = from_review_node(node(guides=None, name=None, email=None, comment=None))
    assert review.guides == []
    assert review.customer_name is None
    assert review.customer_email is None
    assert review.comment is None


def test_falls_back_to_empty_strings_when_activity_is_missing():
    review = from_review_node(node(activity=None))
    assert review.product_id == ""
    assert review.product_name == ""


def test_treats_absent_pii_fields_as_none():
    # Without full customer access the reviewer name/email are never selected,
    # so the node simply lacks the keys.
    raw = node()
    del raw["name"]
    del raw["email"]
    review = from_review_node(raw)
    assert review.customer_name is None
    assert review.customer_email is None


# ─── from_activity_review_summary_node ───────────────────────────────────────


def summary_node(**overrides: Any) -> ActivityReviewSummaryNode:
    base: dict[str, Any] = {
        "id": "act-1",
        "name": "Downtown Bike Tour",
        "reviewMeta": {
            "avgRating": 4.5,
            "count": 10,
            "fiveStar": 6,
            "fourStar": 2,
            "threeStar": 1,
            "twoStar": 1,
            "oneStar": 0,
        },
    }
    base.update(overrides)
    return cast(ActivityReviewSummaryNode, base)


def test_maps_a_fully_populated_summary_node_to_the_clean_summary():
    assert from_activity_review_summary_node(summary_node()) == ProductReviewSummary(
        product_id="act-1",
        product_name="Downtown Bike Tour",
        avg_rating=4.5,
        count_total=10,
        count_one_star=0,
        count_two_star=1,
        count_three_star=1,
        count_four_star=2,
        count_five_star=6,
    )


def test_collapses_a_null_review_meta_to_null_average_and_zero_counts():
    assert from_activity_review_summary_node(summary_node(reviewMeta=None)) == ProductReviewSummary(
        product_id="act-1",
        product_name="Downtown Bike Tour",
        avg_rating=None,
        count_total=0,
        count_one_star=0,
        count_two_star=0,
        count_three_star=0,
        count_four_star=0,
        count_five_star=0,
    )


def test_keeps_a_null_avg_rating_when_there_are_no_ratings():
    summary = from_activity_review_summary_node(
        summary_node(
            reviewMeta={
                "avgRating": None,
                "count": 0,
                "fiveStar": 0,
                "fourStar": 0,
                "threeStar": 0,
                "twoStar": 0,
                "oneStar": 0,
            }
        )
    )
    assert summary.avg_rating is None
    assert summary.count_total == 0


# ─── from_activity_review_summary_nodes ──────────────────────────────────────


def test_maps_every_node_in_order():
    summaries = from_activity_review_summary_nodes(
        [
            summary_node(id="act-1", name="One"),
            summary_node(id="act-2", name="Two", reviewMeta=None),
        ]
    )
    assert [s.product_id for s in summaries] == ["act-1", "act-2"]
    assert summaries[1].avg_rating is None


def test_returns_empty_list_for_no_activities():
    assert from_activity_review_summary_nodes([]) == []
