import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pytest

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.reviews.review_cursor import decode_offset
from peek_app_utilities.internal.peek.reviews.review_queries import (
    ReviewsVariablesParams,
    build_reviews_query,
    build_reviews_variables,
)
from peek_app_utilities.internal.peek.reviews.review_service import ReviewService
from peek_app_utilities.models.peek.review import ProductReviewSummary
from tests.conftest import FakeGraphQLClient

ACTIVITY = "act-1"

PII_OFF = ResolvedAccessOptions(full_customer_access=False)
PII_ON = ResolvedAccessOptions(full_customer_access=True)


@dataclass(frozen=True)
class Row:
    id: str
    date: str


def node_for(row: Row) -> dict[str, Any]:
    return {
        "activity": {"id": ACTIVITY, "name": "Downtown Bike Tour"},
        "guides": [],
        "id": row.id,
        "name": "Customer",
        "email": "c@example.com",
        "rating": 5,
        "comment": None,
        "reviewedAt": f"{row.date}T12:00:00.000000Z",
        "purchasedFor": f"{row.date}T10:00:00.000000Z",
    }


def encode_real(start: int, end: int, offset: int) -> str:
    """Encodes a real gateway cursor: base64 of ``range:start..end,offset``."""
    return base64.b64encode(f"range:{start}..{end},{offset}".encode()).decode("ascii")


@dataclass(frozen=True)
class RecordedRequest:
    """The ``after``/``first`` of a single request (``after`` decoded to its offset)."""

    after: int | None
    first: int


class FakeGateway:
    """A fake reviews API over an ordered (newest-first) row list. It mints
    offset-based cursors exactly like the real API and records the decoded
    ``after`` offset and ``first`` of every request so tests can assert what was
    sent. Stands in for ``GraphQLClient``."""

    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows
        self.requests: list[RecordedRequest] = []
        self.queries: list[str] = []

    async def request(
        self, endpoint_name: str, query: str, variables: Mapping[str, Any]
    ) -> dict[str, Any]:
        assert endpoint_name == SALES_ENDPOINT
        self.queries.append(query)
        raw_after = variables["after"]
        after = None if raw_after is None else decode_offset(raw_after)
        first = int(variables["first"])
        self.requests.append(RecordedRequest(after=after, first=first))
        start_idx = 0 if after is None else after + 1
        rows = self._rows[start_idx : start_idx + first]
        end_idx = start_idx + len(rows) - 1
        edges = [
            {"cursor": encode_real(start_idx, end_idx, start_idx + i), "node": node_for(row)}
            for i, row in enumerate(rows)
        ]
        return {"data": {"reviews": {"edges": edges}}}


def service_over(
    gateway: FakeGateway | FakeGraphQLClient, access_options: ResolvedAccessOptions = PII_OFF
) -> ReviewService:
    return ReviewService(cast(GraphQLClient, gateway), access_options)


# Newest-first (descending review date).
ROWS = [
    Row("r0", "2025-09-10"),
    Row("r1", "2025-09-08"),
    Row("r2", "2025-09-06"),
    Row("r3", "2025-09-04"),
    Row("r4", "2025-08-20"),
    Row("r5", "2025-08-18"),
]

# ─── get_reviews ─────────────────────────────────────────────────────────────


async def test_returns_up_to_the_default_50_reviews_newest_first_with_no_cursor():
    gw = FakeGateway(ROWS)
    reviews = await service_over(gw).get_reviews(ACTIVITY)

    assert [r.id for r in reviews] == ["r0", "r1", "r2", "r3", "r4", "r5"]
    assert reviews[0].product_id == ACTIVITY
    assert reviews[0].product_name == "Downtown Bike Tour"
    assert reviews[0].review_date == "2025-09-10"
    assert reviews[0].activity_date == "2025-09-10"
    assert gw.requests == [RecordedRequest(after=None, first=50)]


async def test_limits_the_page_to_review_count():
    gw = FakeGateway(ROWS)
    reviews = await service_over(gw).get_reviews(ACTIVITY, 3)

    assert [r.id for r in reviews] == ["r0", "r1", "r2"]
    assert gw.requests == [RecordedRequest(after=None, first=3)]


async def test_skips_review_offset_reviews_via_a_cursor_anchored_just_before_the_window():
    gw = FakeGateway(ROWS)
    reviews = await service_over(gw).get_reviews(ACTIVITY, 2, 4)

    assert [r.id for r in reviews] == ["r4", "r5"]
    # offset 4 ⇒ resume after absolute offset 3, asking for 2 reviews.
    assert gw.requests == [RecordedRequest(after=3, first=2)]


async def test_omits_the_cursor_when_review_offset_is_0():
    gw = FakeGateway(ROWS)
    await service_over(gw).get_reviews(ACTIVITY, 2, 0)

    assert gw.requests == [RecordedRequest(after=None, first=2)]


async def test_returns_an_empty_list_when_no_reviews_come_back():
    gw = FakeGateway([])
    assert await service_over(gw).get_reviews(ACTIVITY) == []


async def test_returns_an_empty_list_when_the_reviews_field_is_null(gql: FakeGraphQLClient):
    gql.queue({"reviews": None})
    assert await service_over(gql).get_reviews(ACTIVITY) == []


async def test_sends_the_activity_filter_variables(gql: FakeGraphQLClient):
    gql.queue({"reviews": {"edges": []}})
    await service_over(gql).get_reviews(ACTIVITY, 5)

    assert gql.last_call.endpoint_name == SALES_ENDPOINT
    assert gql.last_call.variables == {
        "first": 5,
        "filter": {"activityIds": [ACTIVITY]},
        "after": None,
    }


def test_build_reviews_variables_shapes_the_filter_and_cursor():
    variables = build_reviews_variables(
        ReviewsVariablesParams(activity_id="act-9", first=10, after="abc")
    )
    assert variables == {"first": 10, "filter": {"activityIds": ["act-9"]}, "after": "abc"}


# ─── get_reviews — validation ────────────────────────────────────────────────


def validating_service() -> ReviewService:
    return service_over(FakeGateway(ROWS))


async def test_rejects_an_empty_product_id():
    with pytest.raises(ValueError, match="productId is required"):
        await validating_service().get_reviews("")


async def test_rejects_a_review_count_below_1():
    with pytest.raises(ValueError, match="reviewCount must be an integer between 1 and 50"):
        await validating_service().get_reviews(ACTIVITY, 0)


async def test_rejects_a_review_count_above_50():
    with pytest.raises(ValueError, match="reviewCount must be an integer between 1 and 50"):
        await validating_service().get_reviews(ACTIVITY, 51)


async def test_rejects_a_non_integer_review_count():
    with pytest.raises(ValueError, match="reviewCount must be an integer between 1 and 50"):
        await validating_service().get_reviews(ACTIVITY, 2.5)


async def test_rejects_a_negative_review_offset():
    with pytest.raises(ValueError, match="reviewOffset must be a non-negative integer"):
        await validating_service().get_reviews(ACTIVITY, 10, -1)


async def test_rejects_a_non_integer_review_offset():
    with pytest.raises(ValueError, match="reviewOffset must be a non-negative integer"):
        await validating_service().get_reviews(ACTIVITY, 10, 1.5)


async def test_rejects_a_boolean_review_count():
    # ``True`` is an ``int`` in Python, but not an integer count.
    with pytest.raises(ValueError, match="reviewCount must be an integer between 1 and 50"):
        await validating_service().get_reviews(ACTIVITY, True)


# ─── get_reviews — access options (full_customer_access) ─────────────────────


def capturing_client(node: dict[str, Any]) -> FakeGraphQLClient:
    """Queues a single-edge reviews page with/without reviewer PII."""
    base: dict[str, Any] = {
        "activity": {"id": ACTIVITY, "name": "Tour"},
        "guides": [],
        "id": "r0",
        "name": None,
        "email": None,
        "rating": 5,
        "comment": "Great",
        "reviewedAt": "2025-09-10T12:00:00.000000Z",
        "purchasedFor": "2025-09-10T10:00:00.000000Z",
    }
    base.update(node)
    return FakeGraphQLClient().queue({"reviews": {"edges": [{"cursor": "c", "node": base}]}})


def collapse(query: str) -> str:
    return re.sub(r"\s+", " ", query)


async def test_requests_reviewer_name_email_when_full_customer_access_is_true():
    gql = capturing_client({"name": "Ada", "email": "ada@example.com"})
    (review,) = await service_over(gql, PII_ON).get_reviews(ACTIVITY)

    query = collapse(gql.last_call.query)
    # The reviewer's own id/name/email/rating selection (distinct from the
    # activity/guides `name` fields).
    assert "id name email rating" in query
    assert review.customer_name == "Ada"
    assert review.customer_email == "ada@example.com"


async def test_omits_reviewer_name_email_and_nulls_them_when_full_customer_access_is_false():
    gql = capturing_client({})
    (review,) = await service_over(gql, PII_OFF).get_reviews(ACTIVITY)

    query = collapse(gql.last_call.query)
    assert "id rating comment" in query
    # `email` appears only as the reviewer field, so its absence is unambiguous.
    assert "email" not in query
    # The review content still comes through.
    assert review.comment == "Great"
    assert review.customer_name is None
    assert review.customer_email is None


def test_build_reviews_query_selects_reviewer_pii_only_with_full_customer_access():
    with_pii = collapse(build_reviews_query(True))
    without_pii = collapse(build_reviews_query(False))

    assert "id name email rating comment reviewedAt purchasedFor" in with_pii
    assert "id rating comment reviewedAt purchasedFor" in without_pii
    assert "email" not in without_pii
    # Everything else is identical: activity, guides, cursor.
    for always in ("activity { id name }", "guides { id name }", "cursor"):
        assert always in with_pii
        assert always in without_pii


# ─── get_all_review_summaries ────────────────────────────────────────────────


async def test_maps_every_activitys_review_meta_to_a_clean_summary(gql: FakeGraphQLClient):
    gql.queue(
        {
            "activities": [
                {
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
                },
                {"id": "act-2", "name": "No Reviews Yet", "reviewMeta": None},
            ]
        }
    )

    summaries = await service_over(gql).get_all_review_summaries()

    assert summaries == [
        ProductReviewSummary(
            product_id="act-1",
            product_name="Downtown Bike Tour",
            avg_rating=4.5,
            count_total=10,
            count_one_star=0,
            count_two_star=1,
            count_three_star=1,
            count_four_star=2,
            count_five_star=6,
        ),
        ProductReviewSummary(
            product_id="act-2",
            product_name="No Reviews Yet",
            avg_rating=None,
            count_total=0,
            count_one_star=0,
            count_two_star=0,
            count_three_star=0,
            count_four_star=0,
            count_five_star=0,
        ),
    ]
    call = gql.last_call
    assert call.endpoint_name == SALES_ENDPOINT
    assert call.variables == {}
    query = collapse(call.query)
    assert "activities" in query
    assert "reviewMeta" in query


async def test_returns_empty_list_when_no_activities_come_back(gql: FakeGraphQLClient):
    gql.queue({"activities": []})
    assert await service_over(gql).get_all_review_summaries() == []


async def test_returns_empty_list_when_the_activities_field_is_absent(gql: FakeGraphQLClient):
    gql.queue({})
    assert await service_over(gql).get_all_review_summaries() == []
