import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Any, cast

import pytest

from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.errors import PiiAccessDisabledError
from peek_app_utilities.internal.peek.bookings.booking_service import (
    AddAddonInput,
    BookingService,
    BookingServiceOptions,
    CancelBookingResult,
    parse_quantity,
)
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.internal.peek.products.product_service import ProductService
from peek_app_utilities.models.peek.booking import (
    BookingReadOptions,
    BookingTimeRangeSearch,
    CreateBookingGuest,
    CreateBookingInput,
    CreateBookingTicket,
    CreatedBooking,
    CustomQuestionAnswerInput,
)
from peek_app_utilities.models.peek.booking_addon import (
    BookingAddon,
    BookingAddonMoney,
    BookingAddonOption,
    BookingAddons,
)
from peek_app_utilities.models.peek.booking_metadata import (
    MetaDataUrlValue,
    SetMetaDataAttachmentInput,
    SetMetaDataGuestInput,
    SetMetaDataResult,
)
from peek_app_utilities.models.peek.booking_payment import (
    BookingPaymentsOnFile,
    InvoiceLinkResult,
    MakePaymentInput,
    MakePaymentResult,
    PaymentSource,
    RefundInput,
)
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption
from peek_app_utilities.models.peek.product import Product, ProductTicket
from tests.conftest import FakeGraphQLClient, RecordedCall


def collapse(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


class FakeProductService:
    """Stands in for ``ProductService``: canned products + custom questions, counting fetches."""

    def __init__(self, products: Sequence[Product] = (), questions: Sequence[CustomQuestion] = ()):
        self._products = list(products)
        self._questions = list(questions)
        self.question_fetch_count = 0

    async def get_all_products(self) -> list[Product]:
        return list(self._products)

    async def get_custom_questions(self, product_id: str) -> list[CustomQuestion]:
        self.question_fetch_count += 1
        return list(self._questions)


def make_service(
    gql: FakeGraphQLClient,
    *,
    products: Sequence[Product] = (),
    full_customer_access: bool = True,
    questions: Sequence[CustomQuestion] = (),
    integrator: str = "",
) -> tuple[BookingService, FakeProductService]:
    product_service = FakeProductService(products, questions)
    service = BookingService(
        cast("GraphQLClient", gql),
        product_service=cast("ProductService", product_service),
        options=BookingServiceOptions(
            access_options=ResolvedAccessOptions(full_customer_access=full_customer_access),
            integrator=integrator,
        ),
    )
    return service, product_service


def listing(nodes: list[dict[str, Any]], page_info: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "sales": {
            "pageInfo": page_info or {"hasNextPage": False, "endCursor": None},
            "edges": [{"node": node} for node in nodes],
        }
    }


def calls_with(gql: FakeGraphQLClient, keyword: str) -> list[RecordedCall]:
    return [c for c in gql.calls if keyword in c.query]


def call_with(gql: FakeGraphQLClient, keyword: str) -> RecordedCall:
    matches = calls_with(gql, keyword)
    assert matches, f"no call containing {keyword!r}"
    return matches[0]


NODE: dict[str, Any] = {
    "id": "b_1",
    "displayId": "B-1",
    "operatorNotes": "old",
    "reservationStatus": "CONFIRMED",
    "checkinStatus": "NONE",
    "returnStatus": "NONE",
}


class TestGetById:
    async def test_normalizes_the_id_filters_by_it_and_converts(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([NODE])))
        booking = await service.get_by_id("B-ABC123")

        assert booking is not None
        assert booking.booking_id == "b_1"
        assert gql.calls[0].variables["filter"]["bookingFilter"]["ids"] == ["b_abc123"]

    async def test_returns_none_when_not_found(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([])))
        assert await service.get_by_id("b_missing") is None

    async def test_passes_read_options_through_to_the_query(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([NODE])))
        booking = await service.get_by_id(
            "b_1", BookingReadOptions(include_guests=True, include_price_breakdown=True)
        )
        assert booking is not None
        assert booking.guests == []
        assert "bookingGuests" in gql.calls[0].query
        assert "convenienceFee" in gql.calls[0].query

    async def test_honours_a_custom_page_size(self, gql: FakeGraphQLClient):
        service = BookingService(
            cast("GraphQLClient", gql.queue(listing([]))),
            product_service=cast("ProductService", FakeProductService()),
            options=BookingServiceOptions(
                access_options=ResolvedAccessOptions(full_customer_access=False),
                integrator="",
                page_size=7,
            ),
        )
        await service.get_by_id("b_1")
        assert gql.calls[0].variables["first"] == 7


class TestBookingIdValidation:
    # A valid id reaches the client; an empty listing just yields None.
    @pytest.mark.parametrize("booking_id", ["b_abc123", "B-123ABC"])
    async def test_accepts_a_valid_booking_id(self, gql: FakeGraphQLClient, booking_id: str):
        service, _ = make_service(gql.queue(listing([])))
        assert await service.get_by_id(booking_id) is None

    # Rejected: no prefix, mismatched case/separator, an order id, or empty.
    @pytest.mark.parametrize("booking_id", ["abc123", "B_abc123", "o-Ab123", "o_abc123", ""])
    async def test_rejects_an_invalid_booking_id(self, gql: FakeGraphQLClient, booking_id: str):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="valid booking id"):
            await service.get_by_id(booking_id)
        assert gql.calls == []


class TestSearch:
    async def test_paginates_a_time_range_search_and_builds_purchase_date_filter(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(listing([NODE], {"hasNextPage": True, "endCursor": "c1"}))
        gql.queue(listing([{**NODE, "id": "b_2"}]))
        service, _ = make_service(gql)

        bookings = await service.search_by_time_range(
            BookingTimeRangeSearch(
                start="2026-01-01T00:00:00Z",
                end="2026-01-31T00:00:00Z",
                product_id="act-1",
                email="a@x.com",
            )
        )

        assert [b.booking_id for b in bookings] == ["b_1", "b_2"]
        variables_filter = gql.calls[0].variables["filter"]
        assert (
            variables_filter["purchasedAtRangeUtc"] == "[2026-01-01T00:00:00Z,2026-01-31T00:00:00Z]"
        )
        assert variables_filter["primaryGuestEmail"] == "a@x.com"
        assert variables_filter["bookingFilter"]["activityIds"] == ["act-1"]
        assert gql.calls[1].variables["after"] == "c1"

    async def test_uses_overlaps_range_for_activity_date_searches(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([])))
        await service.search_by_time_range(
            BookingTimeRangeSearch(start="2026-01-01", end="2026-01-02", search_by="activityDate")
        )
        assert (
            gql.calls[0].variables["filter"]["bookingFilter"]["overlapsRange"]
            == "[2026-01-01,2026-01-02]"
        )

    async def test_supports_a_search_string_only_filter_with_no_booking_filter(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue(listing([])))
        await service.search_by_time_range(
            BookingTimeRangeSearch(start="2026-01-01", end="2026-01-02", search_string="ada")
        )
        variables_filter = gql.calls[0].variables["filter"]
        assert variables_filter["searchString"] == "ada"
        assert "bookingFilter" not in variables_filter

    async def test_filters_by_timeslot(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([NODE])))
        bookings = await service.search_by_timeslot("act-1|ts-1")
        assert [b.booking_id for b in bookings] == ["b_1"]
        assert gql.calls[0].variables["filter"]["bookingFilter"]["timeslotRefid"] == "act-1|ts-1"

    async def test_timeslot_search_passes_read_options_and_tolerates_a_missing_page_info(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue({"sales": {"edges": [{"node": NODE}]}}))
        bookings = await service.search_by_timeslot(
            "ts", BookingReadOptions(include_guests=True, include_price_breakdown=True)
        )
        assert bookings[0].guests == []
        assert "bookingGuests" in gql.calls[0].query


class TestGetGuests:
    async def test_returns_the_merged_guests(self, gql: FakeGraphQLClient):
        gql.queue(
            {
                "sales": {
                    "edges": [
                        {
                            "node": {
                                "displayId": "B-1",
                                "id": "b_1",
                                "primaryGuest": {"id": "g1"},
                                "bookingGuests": [{"id": "g1"}, {"id": "g2"}],
                            }
                        }
                    ]
                }
            }
        )
        service, _ = make_service(gql)
        guests = await service.get_guests("b_1")
        assert [g.id for g in guests] == ["g1", "g2"]


class TestGetPaymentsOnFile:
    async def test_aggregates_and_normalizes_the_booking_id(self, gql: FakeGraphQLClient):
        gql.queue(
            {
                "sales": {
                    "edges": [
                        {
                            "node": {
                                "order": {
                                    "id": "o_1",
                                    "paymentSources": [
                                        {"description": "Visa", "id": "ps-1", "type": "CARD"}
                                    ],
                                    "payments": [],
                                }
                            }
                        }
                    ]
                }
            }
        )
        service, _ = make_service(gql)
        result = await service.get_payments_on_file("B-ABC123")
        assert result == BookingPaymentsOnFile(
            booking_id="b_abc123",
            order_id="o_1",
            payments_on_file=[PaymentSource(description="Visa", id="ps-1", type="CARD")],
        )
        assert "paymentSources" in gql.calls[0].query


class TestAppendNote:
    async def test_appends_to_existing_notes(self, gql: FakeGraphQLClient):
        gql.queue(listing([NODE]))
        gql.queue({"updateOperatorNotesForBooking": {"booking": {"operatorNotes": "x"}}})
        service, _ = make_service(gql)

        booking = await service.append_note("b_1", "new")
        assert booking is not None
        assert booking.notes == "old\nnew"
        mutation = call_with(gql, "updateOperatorNotesForBooking")
        assert mutation.variables["input"] == {"id": "b_1", "operatorNotes": "old\nnew"}

    async def test_overwrites_notes_when_requested(self, gql: FakeGraphQLClient):
        gql.queue(listing([NODE]))
        gql.queue({"updateOperatorNotesForBooking": {"booking": {}}})
        service, _ = make_service(gql)

        booking = await service.append_note("b_1", "fresh", "overwrite")
        assert booking is not None
        assert booking.notes == "fresh"
        assert (
            call_with(gql, "updateOperatorNotesForBooking").variables["input"]["operatorNotes"]
            == "fresh"
        )

    async def test_appends_without_a_separator_when_there_are_no_existing_notes(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(listing([{**NODE, "operatorNotes": None}]))
        gql.queue({"updateOperatorNotesForBooking": {"booking": {}}})
        service, _ = make_service(gql)
        booking = await service.append_note("b_1", "first")
        assert booking is not None
        assert booking.notes == "first"

    async def test_returns_none_and_skips_the_mutation_when_the_booking_is_missing(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue(listing([])))
        assert await service.append_note("b_1", "x") is None
        assert calls_with(gql, "updateOperatorNotesForBooking") == []


class TestSetCheckinStatus:
    async def test_sends_a_timestamp_when_checking_in_and_refetches(self, gql: FakeGraphQLClient):
        gql.queue({"updateBookingCheckIn": {"booking": {"checkinStatus": "CHECKED_IN"}}})
        gql.queue(listing([NODE]))
        service, _ = make_service(gql)

        booking = await service.set_checkin_status("b_1", True)
        assert booking is not None
        assert booking.booking_id == "b_1"
        checked_in_at = call_with(gql, "updateBookingCheckIn").variables["input"]["checkedInAt"]
        assert isinstance(checked_in_at, str)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", checked_in_at)

    async def test_sends_null_when_checking_out(self, gql: FakeGraphQLClient):
        gql.queue({"updateBookingCheckIn": {"booking": {}}})
        gql.queue(listing([NODE]))
        service, _ = make_service(gql)

        await service.set_checkin_status("b_1", False)
        assert call_with(gql, "updateBookingCheckIn").variables["input"]["checkedInAt"] is None


META_NODE: dict[str, Any] = {
    "id": "b_1",
    "displayId": "B-1",
    "fieldResponses": [
        {
            "fieldLocation": {
                "field": {"id": "f1", "name": "Booking URL", "slug": "integrators:bob:booking_url", "type": "URL"},
                "prompt": {"label": "URL", "hint": None, "isRequired": False},
            },
            "refid": "r1",
            "value": {"__typename": "UrlFieldResponseValue", "url": "https://x"},
        },
        {
            "fieldLocation": {
                "field": {"id": "f2", "name": "Other", "slug": "integrators:joe:other", "type": "SHORT_TEXT"},
                "prompt": None,
            },
            "refid": "r2",
            "value": {"__typename": "ShortTextFieldResponseValue", "shortText": "nope"},
        },
    ],
}  # fmt: skip


class TestGetMetaData:
    async def test_filters_to_the_integrator_strips_the_prefix_and_returns_the_entries(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(
            gql.queue({"sales": {"edges": [{"node": META_NODE}]}}), integrator="bob"
        )

        result = await service.get_meta_data("B-ABC123")
        assert len(result) == 1
        assert result[0].slug == "booking_url"
        assert result[0].value == MetaDataUrlValue(url="https://x")
        # Filters by the exact booking id.
        assert gql.calls[0].variables["filter"]["bookingFilter"]["ids"] == ["b_abc123"]
        assert "fieldResponses" in gql.calls[0].query

    async def test_returns_an_empty_list_when_nothing_matches_the_integrator(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(
            gql.queue({"sales": {"edges": [{"node": META_NODE}]}}), integrator="nobody"
        )
        assert await service.get_meta_data("b_1") == []

    async def test_returns_an_empty_list_when_the_booking_is_not_found(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue({"sales": {"edges": []}}), integrator="bob")
        assert await service.get_meta_data("b_1") == []

    async def test_omits_guest_identity_value_fields_from_the_query_when_pii_is_off(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(
            gql.queue({"sales": {"edges": []}}), full_customer_access=False, integrator="bob"
        )
        await service.get_meta_data("b_1")
        query = collapse(gql.calls[0].query)
        assert "... on GuestFieldResponseValue { notes waiverSigned }" in query
        assert "dateOfBirth" not in query

    async def test_raises_on_an_invalid_booking_id_before_any_request(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql, integrator="bob")
        with pytest.raises(ValueError, match="valid booking id"):
            await service.get_meta_data("nope")
        assert gql.calls == []


SUCCESS = {
    "upsertBookingFieldResponses": {
        "__typename": "UpsertBookingFieldResponsesSuccess",
        "bookingId": "b_1",
        "message": "ok",
    }
}


def input_of(gql: FakeGraphQLClient) -> dict[str, Any]:
    return cast("dict[str, Any]", gql.calls[0].variables["input"])


class TestSetMetaData:
    def svc(
        self, gql: FakeGraphQLClient, response: dict[str, Any] | None = SUCCESS
    ) -> BookingService:
        if response is not None:
            gql.queue(response)
        service, _ = make_service(gql, integrator="bob")
        return service

    async def test_set_meta_data_guest_sends_the_guest_field_with_integrator_and_normalized_id(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql)
        result = await service.set_meta_data_guest(
            "B-ABC123",
            [
                SetMetaDataGuestInput(
                    name="Tyler A",
                    email="t@test.com",
                    date_of_birth="2010-06-21",
                    waiver_signed=True,
                    notes="Minor",
                )
            ],
        )
        assert result == SetMetaDataResult(success=True, booking_id="b_1", message="ok")
        payload = input_of(gql)
        assert payload["bookingId"] == "b_abc123"
        assert payload["integrator"] == "bob"
        assert payload["fieldResponses"][0] == {
            "fieldName": "guest",
            "guests": [
                {
                    "name": "Tyler A",
                    "email": "t@test.com",
                    "dateOfBirth": "2010-06-21",
                    "waiverSigned": True,
                    "notes": "Minor",
                }
            ],
        }
        assert "upsertBookingFieldResponses" in gql.calls[0].query

    async def test_set_meta_data_guest_omits_optional_guest_fields_when_not_provided(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql)
        await service.set_meta_data_guest("b_1", [SetMetaDataGuestInput(name="A", email="a@b.co")])
        assert input_of(gql)["fieldResponses"][0]["guests"] == [{"name": "A", "email": "a@b.co"}]

    async def test_set_meta_data_guest_rejects_empty_list_missing_name_or_email_before_any_request(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql, None)
        with pytest.raises(ValueError, match="at least one guest"):
            await service.set_meta_data_guest("b_1", [])
        with pytest.raises(ValueError, match="guest name"):
            await service.set_meta_data_guest(
                "b_1", [SetMetaDataGuestInput(name="", email="a@b.co")]
            )
        with pytest.raises(ValueError, match="guest email"):
            await service.set_meta_data_guest("b_1", [SetMetaDataGuestInput(name="A", email=" ")])
        assert gql.calls == []

    async def test_set_meta_data_attachment_sends_attachments_and_validates_each(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql)
        await service.set_meta_data_attachment(
            "b_1",
            [
                SetMetaDataAttachmentInput(
                    name="Signed Waiver", attachment_url="https://files.example.com/waiver.pdf"
                )
            ],
        )
        assert input_of(gql)["fieldResponses"][0] == {
            "fieldName": "attachment",
            "attachments": [
                {"name": "Signed Waiver", "attachmentUrl": "https://files.example.com/waiver.pdf"}
            ],
        }
        bad_gql = FakeGraphQLClient()
        bad = self.svc(bad_gql, None)
        with pytest.raises(ValueError, match="at least one attachment"):
            await bad.set_meta_data_attachment("b_1", [])
        with pytest.raises(ValueError, match="attachmentUrl"):
            await bad.set_meta_data_attachment(
                "b_1", [SetMetaDataAttachmentInput(name="x", attachment_url="")]
            )
        assert bad_gql.calls == []

    async def test_set_meta_data_manifest_url_sends_the_url_field_and_rejects_empty(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql)
        await service.set_meta_data_manifest_url("b_1", "https://manifests.example.com/b_1")
        assert input_of(gql)["fieldResponses"][0] == {
            "fieldName": "manifest_url",
            "url": "https://manifests.example.com/b_1",
        }
        with pytest.raises(ValueError, match="url"):
            await self.svc(FakeGraphQLClient(), None).set_meta_data_manifest_url("b_1", "")

    @pytest.mark.parametrize(
        ("method", "field_name", "value"),
        [
            ("set_meta_data_reservation_id", "reservation_id", "RES-99812"),
            ("set_meta_data_booking_status", "booking_status", "CONFIRMED"),
            ("set_meta_data_assigned_product", "assigned_product", "Zipline Tour - 2pm"),
            ("set_meta_data_assigned_employee", "assigned_employee", "Dana Guide"),
        ],
    )
    async def test_maps_the_four_short_text_setters_to_the_right_field_name_and_short_text(
        self, gql: FakeGraphQLClient, method: str, field_name: str, value: str
    ):
        service = self.svc(gql)
        await getattr(service, method)("b_1", value)
        assert input_of(gql)["fieldResponses"][0] == {"fieldName": field_name, "shortText": value}

    @pytest.mark.parametrize(
        "method",
        [
            "set_meta_data_reservation_id",
            "set_meta_data_booking_status",
            "set_meta_data_assigned_product",
            "set_meta_data_assigned_employee",
        ],
    )
    async def test_short_text_setters_reject_empty_values_before_any_request(
        self, gql: FakeGraphQLClient, method: str
    ):
        service = self.svc(gql, None)
        with pytest.raises(ValueError, match="non-empty string"):
            await getattr(service, method)("b_1", "  ")
        assert gql.calls == []

    async def test_set_meta_data_insurance_purchased_sends_a_boolean_and_rejects_non_boolean(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql)
        await service.set_meta_data_insurance_purchased("b_1", True)
        assert input_of(gql)["fieldResponses"][0] == {
            "fieldName": "insurance_purchased",
            "boolean": True,
        }
        with pytest.raises(ValueError, match="boolean"):
            await self.svc(FakeGraphQLClient(), None).set_meta_data_insurance_purchased(
                "b_1", cast("bool", "yes")
            )

    async def test_maps_booking_not_found_error_and_generic_error_results_to_success_false(
        self, gql: FakeGraphQLClient
    ):
        not_found = self.svc(
            gql,
            {
                "upsertBookingFieldResponses": {
                    "__typename": "BookingNotFoundError",
                    "bookingId": "b_1",
                    "message": "nope",
                }
            },
        )
        assert await not_found.set_meta_data_manifest_url("b_1", "https://x") == SetMetaDataResult(
            success=False, booking_id="b_1", message="nope"
        )
        generic = self.svc(
            FakeGraphQLClient(),
            {"upsertBookingFieldResponses": {"__typename": "GenericError", "message": "boom"}},
        )
        assert await generic.set_meta_data_manifest_url("b_1", "https://x") == SetMetaDataResult(
            success=False, booking_id="b_1", message="boom"
        )

    async def test_validates_the_booking_id_for_a_setter_before_any_request(
        self, gql: FakeGraphQLClient
    ):
        service = self.svc(gql, None)
        with pytest.raises(ValueError, match="valid booking id"):
            await service.set_meta_data_manifest_url("nope", "https://x")
        assert gql.calls == []

    async def test_uses_the_service_integrator_when_an_empty_one_is_set(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue(SUCCESS))
        await service.set_meta_data_manifest_url("b_1", "https://x")
        assert input_of(gql)["integrator"] == ""


class TestUpdateCustomStatus:
    async def test_sends_the_normalized_id_and_status_and_returns_true_when_confirmed(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            {"updateOperatorStatusForBooking": {"booking": {"operatorStatus": "Hello World"}}}
        )
        service, _ = make_service(gql)

        assert await service.update_custom_status("B-ABC123", "Hello World") is True
        assert gql.calls[0].variables["input"] == {
            "id": "b_abc123",
            "operatorStatus": "Hello World",
        }
        assert "updateOperatorStatusForBooking" in gql.calls[0].query

    async def test_returns_false_when_the_stored_status_differs_from_the_requested_one(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            {"updateOperatorStatusForBooking": {"booking": {"operatorStatus": "Something else"}}}
        )
        service, _ = make_service(gql)
        assert await service.update_custom_status("b_1", "Hello World") is False

    async def test_returns_false_when_the_mutation_returns_no_booking(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue({"updateOperatorStatusForBooking": None}))
        assert await service.update_custom_status("b_1", "Hello World") is False

    async def test_works_without_full_customer_access_not_a_pii_gated_operation(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            {"updateOperatorStatusForBooking": {"booking": {"operatorStatus": "Hello World"}}}
        )
        service, _ = make_service(gql, full_customer_access=False)
        assert await service.update_custom_status("b_1", "Hello World") is True

    async def test_raises_on_an_invalid_booking_id_before_any_request(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="valid booking id"):
            await service.update_custom_status("nope", "Hello World")
        assert gql.calls == []

    async def test_raises_on_an_empty_or_whitespace_only_custom_status_before_any_request(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="non-empty string"):
            await service.update_custom_status("b_1", "")
        with pytest.raises(ValueError, match="non-empty string"):
            await service.update_custom_status("b_1", "   ")
        with pytest.raises(ValueError, match="non-empty string"):
            await service.update_custom_status("b_1", cast("str", None))
        assert gql.calls == []


class TestCancel:
    async def test_cancels_with_a_default_note_and_returns_the_status(self, gql: FakeGraphQLClient):
        gql.queue(
            {
                "cancelBooking": {
                    "booking": {"id": "b_1", "displayId": "B-1", "reservationStatus": "CANCELED"}
                }
            }
        )
        service, _ = make_service(gql)

        result = await service.cancel("B-ABC123")
        assert result == CancelBookingResult(
            id="b_1", display_id="B-1", reservation_status="CANCELED"
        )
        assert gql.calls[0].variables["input"] == {"bookingId": "b_abc123", "notes": "Canceled"}

    async def test_raises_when_the_mutation_returns_no_booking(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue({"cancelBooking": None}))
        with pytest.raises(ValueError, match="No booking data"):
            await service.cancel("b_1")


PAYMENTS_RESP: dict[str, Any] = {
    "sales": {
        "edges": [
            {
                "node": {
                    "order": {
                        "id": "o_1",
                        "paymentSources": [{"description": "Visa", "id": "ps_1", "type": "CARD"}],
                        "payments": [
                            {
                                "id": "pmt_1",
                                "paymentSource": {"id": "ps_1"},
                                "appliedAt": "2026-01-02T10:00:00Z",
                                "currentAmount": {"amount": "10", "currency": "USD"},
                                "refundableAmount": {"amount": "10", "currency": "USD"},
                            }
                        ],
                    }
                }
            }
        ]
    }
}


class TestMakePayment:
    valid = MakePaymentInput(
        booking_id="b_1",
        payment_source_id="ps_1",
        amount="10",
        currency="USD",
        idempotency_key="key-1",
    )

    async def test_charges_and_returns_the_transaction_id(self, gql: FakeGraphQLClient):
        gql.queue(PAYMENTS_RESP)
        gql.queue({"applyPaymentToOrder": {"transactionId": "tx-1", "errors": None}})
        service, _ = make_service(gql)

        result = await service.make_payment(replace(self.valid, customer_message="thanks"))
        assert result == MakePaymentResult(
            transaction_id="tx-1",
            booking_id="b_1",
            order_id="o_1",
            amount="10",
            currency="USD",
            payment_source_id="ps_1",
        )
        assert call_with(gql, "applyPaymentToOrder").variables["input"] == {
            "amount": {"amount": "10", "currency": "USD"},
            "orderId": "o_1",
            "paymentSourceId": "ps_1",
            "idempotencyKey": "key-1",
            "customerMessage": "Charge initiated via API (thanks)",
            "scopedTo": ["b_1"],
        }

    async def test_uses_the_default_customer_message_and_an_empty_transaction_id_fallback(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(PAYMENTS_RESP)
        gql.queue({"applyPaymentToOrder": {"transactionId": None, "errors": []}})
        service, _ = make_service(gql)
        result = await service.make_payment(self.valid)
        assert result.transaction_id == ""
        assert (
            call_with(gql, "applyPaymentToOrder").variables["input"]["customerMessage"]
            == "Charge initiated via API"
        )

    async def test_raises_when_the_booking_is_not_found(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue({"sales": {"edges": []}}))
        with pytest.raises(ValueError, match="Booking not found"):
            await service.make_payment(self.valid)

    async def test_raises_when_the_payment_source_does_not_exist(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(PAYMENTS_RESP))
        with pytest.raises(ValueError, match="paymentSourceId not found"):
            await service.make_payment(replace(self.valid, payment_source_id="ps_other"))

    async def test_raises_when_peek_returns_payment_errors(self, gql: FakeGraphQLClient):
        gql.queue(PAYMENTS_RESP)
        gql.queue(
            {
                "applyPaymentToOrder": {
                    "transactionId": None,
                    "errors": [{"code": "X", "detail": "declined", "value": None}],
                }
            }
        )
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="Payment failed: declined"):
            await service.make_payment(self.valid)

    @pytest.mark.parametrize(
        ("overrides", "pattern"),
        [
            ({"payment_source_id": "bad"}, "paymentSourceId is required"),
            ({"payment_source_id": ""}, "paymentSourceId is required"),
            ({"amount": "abc"}, "amount is required"),
            ({"amount": ""}, "amount is required"),
            ({"currency": "usd"}, "currency is required"),
            ({"idempotency_key": ""}, "idempotencyKey is required"),
            ({"booking_id": "x-1"}, "bookingId is required"),
        ],
    )
    async def test_rejects_invalid_input(
        self, gql: FakeGraphQLClient, overrides: dict[str, Any], pattern: str
    ):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match=pattern):
            await service.make_payment(replace(self.valid, **overrides))
        assert gql.calls == []

    @pytest.mark.parametrize("source_id", ["cash/cash", "custom/other", "custom/voucher"])
    async def test_accepts_the_synthetic_payment_source_ids(
        self, gql: FakeGraphQLClient, source_id: str
    ):
        service, _ = make_service(gql.queue({"sales": {"edges": []}}))
        with pytest.raises(ValueError, match="Booking not found"):
            await service.make_payment(replace(self.valid, payment_source_id=source_id))


class TestRefund:
    valid = RefundInput(
        booking_id="b_1", payment_id="pmt_1", amount="10", currency="USD", idempotency_key="key-1"
    )

    async def test_refunds_and_returns_the_transaction_id(self, gql: FakeGraphQLClient):
        gql.queue(PAYMENTS_RESP)
        gql.queue({"applyRefundToOrder": {"transactionId": "rf-1", "errors": None}})
        service, _ = make_service(gql)

        result = await service.refund(self.valid)
        assert (result.transaction_id, result.order_id, result.payment_id) == (
            "rf-1",
            "o_1",
            "pmt_1",
        )
        assert (result.booking_id, result.amount, result.currency) == ("b_1", "10", "USD")
        payload = call_with(gql, "applyRefundToOrder").variables["input"]
        assert payload["orderId"] == "o_1"
        assert payload["paymentId"] == "pmt_1"
        assert payload["scopedTo"] == ["b_1"]
        assert payload["amount"] == {"amount": "10", "currency": "USD"}
        assert payload["idempotencyKey"] == "key-1"

    async def test_falls_back_to_an_empty_transaction_id(self, gql: FakeGraphQLClient):
        gql.queue(PAYMENTS_RESP)
        gql.queue({"applyRefundToOrder": {"transactionId": None, "errors": None}})
        service, _ = make_service(gql)
        assert (await service.refund(self.valid)).transaction_id == ""

    async def test_raises_when_the_payment_id_does_not_exist(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(PAYMENTS_RESP))
        with pytest.raises(ValueError, match="paymentId not found"):
            await service.refund(replace(self.valid, payment_id="pmt_other"))

    async def test_raises_when_the_booking_is_not_found(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue({"sales": {"edges": []}}))
        with pytest.raises(ValueError, match="Booking not found"):
            await service.refund(self.valid)

    async def test_raises_when_peek_returns_refund_errors(self, gql: FakeGraphQLClient):
        gql.queue(PAYMENTS_RESP)
        gql.queue(
            {
                "applyRefundToOrder": {
                    "transactionId": None,
                    "errors": [{"code": "X", "detail": "nope", "value": None}],
                }
            }
        )
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="Refund failed: nope"):
            await service.refund(self.valid)

    async def test_rejects_an_invalid_payment_id(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="paymentId is required"):
            await service.refund(replace(self.valid, payment_id="bad"))
        with pytest.raises(ValueError, match="paymentId is required"):
            await service.refund(replace(self.valid, payment_id=""))


class TestCreateInvoiceLink:
    booking_with_order = {**NODE, "order": {"id": "o_1"}}

    async def test_resolves_the_order_and_returns_the_invoice_url(self, gql: FakeGraphQLClient):
        gql.queue(listing([self.booking_with_order]))
        gql.queue(
            {
                "createInvoiceLink": {
                    "invoiceLink": {"status": "OK", "url": "https://inv/1"},
                    "errors": None,
                }
            }
        )
        service, _ = make_service(gql)

        result = await service.create_invoice_link("B-1")
        assert result == InvoiceLinkResult(
            booking_id="b_1", order_id="o_1", invoice_link="https://inv/1"
        )
        assert call_with(gql, "createInvoiceLink").variables["input"] == {"orderId": "o_1"}

    async def test_raises_when_the_booking_has_no_order(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(listing([])))
        with pytest.raises(ValueError, match="Booking not found"):
            await service.create_invoice_link("b_1")
        service, _ = make_service(FakeGraphQLClient().queue(listing([NODE])))
        with pytest.raises(ValueError, match="Booking not found"):
            await service.create_invoice_link("b_1")

    async def test_raises_when_no_url_is_returned(self, gql: FakeGraphQLClient):
        gql.queue(listing([self.booking_with_order]))
        gql.queue(
            {
                "createInvoiceLink": {
                    "invoiceLink": None,
                    "errors": [{"code": "X", "detail": "no", "value": None}],
                }
            }
        )
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="Failed to create invoice link"):
            await service.create_invoice_link("b_1")

    async def test_raises_when_the_booking_id_is_blank(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="bookingId is required"):
            await service.create_invoice_link("  ")


# ---- Add-on fixtures + helpers -------------------------------------------

ADDON = Product(
    product_id="item-1",
    name="Safety Gear",
    type="ADD-ON",
    color="#FFFFFF",
    currency="",
    image_url=None,
    description=None,
    meeting_location=None,
    tickets=[ProductTicket(id="opt-1", name="Helmet", min_price=None, max_price=None)],
)

ADDON_MONEY = {"amount": "10.00", "currency": "USD", "formatted": "$10.00"}
ADDON_MONEY_MODEL = BookingAddonMoney(amount="10.00", currency="USD", formatted="$10.00")


def option_node(**overrides: Any) -> dict[str, Any]:
    return {
        "refid": "or-1",
        "reservationStatus": "CONFIRMED",
        "price": ADDON_MONEY,
        "itemOptionSnapshot": {"id": "opt-1", "name": "Helmet"},
        "itemSnapshot": {"id": "item-1", "name": "Safety Gear"},
        **overrides,
    }


def item_node(options: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    return {
        "id": "it-1",
        "refid": "ir-1",
        "reservationStatus": "CONFIRMED",
        "value": {"total": ADDON_MONEY},
        "options": options,
        **overrides,
    }


def addon_booking_node(items: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    return {
        "id": "b_1",
        "displayId": "B-1",
        "refid": "bq-1",
        "reservationStatus": "CONFIRMED",
        "order": {"id": "o_1", "displayId": "O-1"},
        "items": items,
        **overrides,
    }


def sales_addons(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return listing(nodes)


CREATE_QUOTE_OK = {
    "createQuoteFromOrder": {
        "errors": None,
        "quote": {"id": "q-1", "saleQuotes": [{"refid": "sq-1", "reservationStatus": "CONFIRMED"}]},
    }
}
UPDATE_QUOTE_OK = {"updateQuoteV2": {"errors": None, "quote": {"id": "q-1"}}}
AMEND_OK = {"amendOrder": {"errors": None, "order": {"id": "o_1"}}}


def queue_addon_flow(
    gql: FakeGraphQLClient,
    list_response: dict[str, Any],
    *,
    create_quote: dict[str, Any] = CREATE_QUOTE_OK,
    update_quote: dict[str, Any] = UPDATE_QUOTE_OK,
    amend: dict[str, Any] = AMEND_OK,
) -> None:
    """Queues the add/remove add-on call chain: list → quote → update → amend → list."""
    gql.queue(list_response).queue(create_quote).queue(update_quote).queue(amend).queue(
        list_response
    )


def update_quote_booking_quotes(gql: FakeGraphQLClient) -> list[dict[str, Any]]:
    payload = call_with(gql, "updateQuoteV2").variables["input"]
    return cast("list[dict[str, Any]]", payload["quoteInput"]["bookingQuotes"])


class TestAddAddon:
    async def test_derives_the_order_id_reuses_an_existing_refid_and_returns_updated_addons(
        self, gql: FakeGraphQLClient
    ):
        # The add-on is already on the booking (item-1 / refid ir-1), so add_addon
        # reuses ir-1 instead of minting a new add-on refid.
        queue_addon_flow(gql, sales_addons([addon_booking_node([item_node([option_node()])])]))
        service, _ = make_service(gql, products=[ADDON])

        result = await service.add_addon(
            "B-1", AddAddonInput(addon_option_id="opt-1", quantity="2")
        )

        assert result.updated_booking_addons == BookingAddons(
            booking_id="b_1",
            display_id="B-1",
            order_id="o_1",
            addons=[
                BookingAddon(
                    addon_id="item-1",
                    addon_name="Safety Gear",
                    total=ADDON_MONEY_MODEL,
                    addon_options=[
                        BookingAddonOption(
                            addon_option_id="opt-1", addon_option_name="Helmet", quantity=1
                        )
                    ],
                )
            ],
        )

        assert call_with(gql, "createQuoteFromOrder").variables["input"] == {
            "orderId": "o_1",
            "quoteInput": {},
        }

        bq = update_quote_booking_quotes(gql)[0]
        assert bq["refid"] == "sq-1"
        assert bq["addons"][0]["itemId"] == "item-1"
        assert bq["addons"][0]["refid"] == "ir-1"  # reused existing item refid
        assert len(bq["addons"][0]["itemOptions"]) == 2
        assert bq["addons"][0]["itemOptions"][0]["itemOptionId"] == "opt-1"

        assert call_with(gql, "amendOrder").variables["input"] == {
            "quoteId": "q-1",
            "orderId": "o_1",
        }
        # The add-ons query is keyed by the display id as given.
        assert gql.calls[0].variables["filter"] == {"searchString": "B-1"}

    async def test_mints_a_fresh_addon_refid_when_the_item_is_not_already_on_the_booking(
        self, gql: FakeGraphQLClient
    ):
        queue_addon_flow(gql, sales_addons([addon_booking_node([])]))
        service, _ = make_service(gql, products=[ADDON])

        await service.add_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

        refid = update_quote_booking_quotes(gql)[0]["addons"][0]["refid"]
        assert refid != "ir-1"
        assert len(refid) == 36  # uuid

    async def test_does_not_reuse_the_refid_of_a_canceled_booking_quote(
        self, gql: FakeGraphQLClient
    ):
        canceled = addon_booking_node([item_node([option_node()])], reservationStatus="CANCELED")
        queue_addon_flow(gql, sales_addons([canceled]))
        service, _ = make_service(gql, products=[ADDON])
        await service.add_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))
        assert update_quote_booking_quotes(gql)[0]["addons"][0]["refid"] != "ir-1"

    async def test_raises_when_the_addon_option_id_is_missing(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="addonOptionId is required"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id=" ", quantity="1"))
        assert gql.calls == []

    @pytest.mark.parametrize("quantity", ["0", "abc", "-1"])
    async def test_rejects_invalid_quantity(self, gql: FakeGraphQLClient, quantity: str):
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="positive integer"):
            await service.add_addon(
                "b_1", AddAddonInput(addon_option_id="opt-1", quantity=quantity)
            )

    async def test_raises_when_the_addon_cannot_be_matched(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(sales_addons([addon_booking_node([])])), products=[])
        with pytest.raises(ValueError, match="Add-on not found"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-x", quantity="1"))

    async def test_raises_when_the_booking_is_not_found(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(sales_addons([])), products=[ADDON])
        with pytest.raises(ValueError, match="Booking not found"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

    async def test_raises_when_more_than_one_booking_matches(self, gql: FakeGraphQLClient):
        gql.queue(sales_addons([addon_booking_node([]), addon_booking_node([])]))
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="Expected exactly one booking"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

    @pytest.mark.parametrize(
        "create_quote",
        [
            {"createQuoteFromOrder": {"errors": None, "quote": None}},
            {"createQuoteFromOrder": {"errors": [{"code": "X", "detail": "no", "value": None}], "quote": {"id": "q-1", "saleQuotes": []}}},
            {"createQuoteFromOrder": {"errors": None, "quote": {"id": "q-1", "saleQuotes": []}}},  # no sale quote refid
        ],
    )  # fmt: skip
    async def test_raises_when_the_quote_cannot_be_created(
        self, gql: FakeGraphQLClient, create_quote: dict[str, Any]
    ):
        gql.queue(sales_addons([addon_booking_node([])])).queue(create_quote)
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="Failed to create quote from order"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

    async def test_raises_when_the_quote_update_fails(self, gql: FakeGraphQLClient):
        gql.queue(sales_addons([addon_booking_node([])])).queue(CREATE_QUOTE_OK)
        gql.queue(
            {
                "updateQuoteV2": {
                    "errors": [{"code": "X", "detail": "no", "value": None}],
                    "quote": None,
                }
            }
        )
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="Failed to update quote with add-on"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

    async def test_raises_when_the_order_amend_fails(self, gql: FakeGraphQLClient):
        gql.queue(sales_addons([addon_booking_node([])])).queue(CREATE_QUOTE_OK).queue(
            UPDATE_QUOTE_OK
        )
        gql.queue({"amendOrder": {"errors": None, "order": None}})
        service, _ = make_service(gql, products=[ADDON])
        with pytest.raises(ValueError, match="Failed to amend order with add-on"):
            await service.add_addon("b_1", AddAddonInput(addon_option_id="opt-1", quantity="1"))


class TestListAddons:
    async def test_groups_live_options_by_addon_item_with_a_quantity_count(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            sales_addons(
                [
                    addon_booking_node(
                        [item_node([option_node(refid="or-1"), option_node(refid="or-2")])]
                    )
                ]
            )
        )
        service, _ = make_service(gql)

        result = await service.list_addons("B-1")
        assert result.booking_id == "b_1"
        assert result.order_id == "o_1"
        assert result.addons == [
            BookingAddon(
                addon_id="item-1",
                addon_name="Safety Gear",
                total=ADDON_MONEY_MODEL,
                addon_options=[
                    BookingAddonOption(
                        addon_option_id="opt-1", addon_option_name="Helmet", quantity=2
                    )
                ],
            )
        ]

    async def test_drops_canceled_options_and_omits_fully_canceled_addons(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            sales_addons(
                [
                    addon_booking_node(
                        [item_node([option_node(refid="or-1", reservationStatus="CANCELED")])]
                    )
                ]
            )
        )
        service, _ = make_service(gql)
        assert (await service.list_addons("B-1")).addons == []

    async def test_uses_the_booking_level_fallback_when_there_are_no_items(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue(sales_addons([addon_booking_node([])])))
        assert await service.list_addons("B-1") == BookingAddons(
            booking_id="b_1", display_id="B-1", order_id="o_1", addons=[]
        )

    async def test_falls_back_to_empty_ids_for_a_bare_node(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql.queue(sales_addons([{}])))
        assert await service.list_addons("B-1") == BookingAddons(
            booking_id="", display_id="", order_id="", addons=[]
        )

    async def test_requires_a_booking_id(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="bookingId is required"):
            await service.list_addons("  ")


REMOVE_CREATE_QUOTE = {
    "createQuoteFromOrder": {"errors": None, "quote": {"id": "q-1", "saleQuotes": []}}
}


class TestRemoveAddon:
    def queue_remove(self, gql: FakeGraphQLClient, nodes: list[dict[str, Any]]) -> BookingService:
        queue_addon_flow(gql, sales_addons(nodes), create_quote=REMOVE_CREATE_QUOTE)
        service, _ = make_service(gql)
        return service

    async def test_cancels_one_confirmed_option_leaving_the_addon_confirmed(
        self, gql: FakeGraphQLClient
    ):
        service = self.queue_remove(
            gql,
            [
                addon_booking_node(
                    [item_node([option_node(refid="or-1"), option_node(refid="or-2")])]
                )
            ],
        )

        await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

        bq = update_quote_booking_quotes(gql)[0]
        assert bq["refid"] == "bq-1"
        assert bq["addons"][0]["refid"] == "ir-1"
        assert "reservationStatus" not in bq["addons"][0]  # or-2 still live
        assert bq["addons"][0]["itemOptions"] == [
            {"reservationStatus": "CANCELED", "refid": "or-1"}
        ]

    async def test_cancels_the_whole_addon_when_every_option_is_removed(
        self, gql: FakeGraphQLClient
    ):
        service = self.queue_remove(
            gql,
            [
                addon_booking_node(
                    [item_node([option_node(refid="or-1"), option_node(refid="or-2")])]
                )
            ],
        )
        await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="2"))
        assert update_quote_booking_quotes(gql)[0]["addons"][0]["reservationStatus"] == "CANCELED"

    async def test_cancels_across_multiple_booking_items(self, gql: FakeGraphQLClient):
        service = self.queue_remove(
            gql,
            [
                addon_booking_node(
                    [
                        item_node([option_node(refid="or-1")], id="it-1", refid="ir-1"),
                        item_node([option_node(refid="or-2")], id="it-2", refid="ir-2"),
                    ]
                )
            ],
        )
        await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="2"))
        refids = sorted(a["refid"] for a in update_quote_booking_quotes(gql)[0]["addons"])
        assert refids == ["ir-1", "ir-2"]

    async def test_stops_selecting_once_the_quantity_budget_is_spent(self, gql: FakeGraphQLClient):
        service = self.queue_remove(
            gql,
            [
                addon_booking_node(
                    [
                        item_node([option_node(refid="or-1")], id="it-1", refid="ir-1"),
                        item_node([option_node(refid="or-2")], id="it-2", refid="ir-2"),
                    ]
                )
            ],
        )
        await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))
        assert [a["refid"] for a in update_quote_booking_quotes(gql)[0]["addons"]] == ["ir-1"]

    async def test_skips_already_canceled_options_when_selecting_what_to_cancel(
        self, gql: FakeGraphQLClient
    ):
        service = self.queue_remove(
            gql,
            [
                addon_booking_node(
                    [
                        item_node(
                            [
                                option_node(refid="or-1", reservationStatus="CANCELED"),
                                option_node(refid="or-2"),
                            ]
                        )
                    ]
                )
            ],
        )
        await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))
        assert update_quote_booking_quotes(gql)[0]["addons"][0]["itemOptions"] == [
            {"reservationStatus": "CANCELED", "refid": "or-2"}
        ]

    async def test_raises_when_no_matching_confirmed_option_is_found(self, gql: FakeGraphQLClient):
        gql.queue(
            sales_addons(
                [addon_booking_node([item_node([option_node(reservationStatus="CANCELED")])])]
            )
        )
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="No confirmed add-on option"):
            await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="1"))

    async def test_validates_the_addon_option_id_and_quantity(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="addonOptionId is required"):
            await service.remove_addon("B-1", AddAddonInput(quantity="1"))
        with pytest.raises(ValueError, match="positive integer"):
            await service.remove_addon("B-1", AddAddonInput(addon_option_id="opt-1", quantity="x"))
        assert gql.calls == []


class TestParseQuantity:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("2", 2), (" 3 ", 3), (4, 4), ("0", None), ("-1", None), ("abc", None), (True, None), (None, None), (2.5, None)],
    )  # fmt: skip
    def test_parses_positive_integer_strings_and_ints_only(self, value: Any, expected: int | None):
        assert parse_quantity(value) == expected


# ---- Create fixtures ------------------------------------------------------

VALID_CREATE = CreateBookingInput(
    activity_id="act-1",
    availability_time_id="avail-1",
    tickets=[CreateBookingTicket(resource_option_id="r1", quantity=2)],
    guest=CreateBookingGuest(name="Ada", email="ada@example.com"),
)

ORDER_SALE = {
    "id": "b_1",
    "displayId": "B-1",
    "balance": {"total": {"amount": "100.00", "currency": "USD", "formatted": "$100.00"}},
}
QUOTE_OK = {"createQuoteV2": {"errors": None, "quote": {"id": "q-1"}}}
ORDER_OK = {"createOrderFromQuote": {"errors": None, "order": {"id": "o_1", "sales": [ORDER_SALE]}}}
PAYMENT_OK = {"applyPaymentToOrder": {"transactionId": "tx-1", "errors": None}}


def queue_create(
    gql: FakeGraphQLClient,
    *,
    quote: dict[str, Any] = QUOTE_OK,
    order: dict[str, Any] | None = ORDER_OK,
    payment: dict[str, Any] | None = None,
) -> FakeGraphQLClient:
    gql.queue(quote)
    if order is not None:
        gql.queue(order)
    if payment is not None:
        gql.queue(payment)
    return gql


def quote_input_of(gql: FakeGraphQLClient) -> dict[str, Any]:
    return cast("dict[str, Any]", call_with(gql, "createQuoteV2").variables["input"]["quoteInput"])


def booking_quote_of(gql: FakeGraphQLClient) -> dict[str, Any]:
    return cast("dict[str, Any]", quote_input_of(gql)["bookingQuotes"][0])


def quote_tickets(gql: FakeGraphQLClient) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", booking_quote_of(gql)["tickets"])


def eur_product(product_id: str = "act-1") -> Product:
    return replace(ADDON, product_id=product_id, type="ACTIVITY", currency="EUR", tickets=[])


def q(**over: Any) -> CustomQuestion:
    base: dict[str, Any] = {
        "id": "cq_x",
        "order": 1,
        "is_required": False,
        "question_text": "Question",
        "hint_text": None,
        "question_type": "TEXT",
        "internal_label": None,
        "per_guest": False,
        "default_value": None,
        "options": [],
    }
    return CustomQuestion(**{**base, **over})


QUESTIONS = [
    q(id="cq_check", question_text="Adult Only?", question_type="CHECK_BOX"),
    q(id="cq_text", question_text="Dietary Notes", question_type="TEXT"),
    q(
        id="cq_pick",
        question_text="Pickup Spot",
        question_type="SELECT_ONE",
        options=[
            CustomQuestionOption(id="cqao_a", order=1, value="Option A"),
            CustomQuestionOption(id="cqao_b", order=2, value="Option B"),
        ],
    ),
]


def answers(*pairs: tuple[str, str]) -> list[CustomQuestionAnswerInput]:
    return [CustomQuestionAnswerInput(question_id_or_text=k, value=v) for k, v in pairs]


class TestCreate:
    async def test_creates_a_booking_via_quote_then_order(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql))

        result = await service.create(replace(VALID_CREATE, operator_notes="VIP"))
        assert result == CreatedBooking(
            order_id="o_1",
            booking_id="b_1",
            display_id="B-1",
            balance_amount="100.00",
            balance_currency="USD",
            balance_formatted="$100.00",
        )

        quote_input = quote_input_of(gql)
        bq = quote_input["bookingQuotes"][0]
        assert bq["activityId"] == "act-1"
        assert bq["availabilityTimeId"] == "avail-1"
        assert len(bq["tickets"]) == 2
        assert bq["tickets"][0]["resourceOptionId"] == "r1"
        assert bq["skipCustomerEmail"] is False
        assert bq["operatorNotes"] == "VIP"
        assert bq["guest"] == {
            "name": "Ada",
            "email": "ada@example.com",
            "phone": None,
            "optinMarketing": False,
            "optinSms": False,
            "postalCode": None,
            "country": None,
        }
        assert "source" not in quote_input
        assert call_with(gql, "createOrderFromQuote").variables["input"] == {"quoteId": "q-1"}
        assert calls_with(gql, "applyPaymentToOrder") == []

    async def test_defaults_the_balance_when_the_sale_carries_none(self, gql: FakeGraphQLClient):
        order = {
            "createOrderFromQuote": {
                "errors": None,
                "order": {"id": "o_1", "sales": [{"id": "b_1", "displayId": "B-1"}]},
            }
        }
        service, _ = make_service(queue_create(gql, order=order))
        result = await service.create(VALID_CREATE)
        assert (result.balance_amount, result.balance_currency, result.balance_formatted) == (
            "0.00",
            "USD",
            "$0.00",
        )

    async def test_splits_list_price_across_tickets_in_the_activity_currency(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql), products=[eur_product()])

        await service.create(
            replace(
                VALID_CREATE,
                tickets=[CreateBookingTicket(resource_option_id="r1", quantity=3)],
                list_price="10.00",
            )
        )

        assert [t["price"] for t in quote_tickets(gql)] == [
            {"amount": "3.33", "currency": "EUR"},
            {"amount": "3.33", "currency": "EUR"},
            {"amount": "3.34", "currency": "EUR"},
        ]

    async def test_distributes_the_list_price_across_multiple_ticket_lines_in_order(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql), products=[eur_product()])

        await service.create(
            replace(
                VALID_CREATE,
                tickets=[
                    CreateBookingTicket(resource_option_id="r1", quantity=2),
                    CreateBookingTicket(resource_option_id="r2", quantity=1),
                ],
                list_price="10.00",
            )
        )

        assert [(t["resourceOptionId"], t["price"]) for t in quote_tickets(gql)] == [
            ("r1", {"amount": "3.33", "currency": "EUR"}),
            ("r1", {"amount": "3.33", "currency": "EUR"}),
            ("r2", {"amount": "3.34", "currency": "EUR"}),
        ]

    async def test_falls_back_to_usd_when_the_activity_currency_cannot_be_resolved(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql), products=[])  # no products
        await service.create(replace(VALID_CREATE, list_price="10"))  # quantity 2
        assert [t["price"] for t in quote_tickets(gql)] == [
            {"amount": "5.00", "currency": "USD"},
            {"amount": "5.00", "currency": "USD"},
        ]
        # A matching activity with an empty currency falls back too.
        gql2 = queue_create(FakeGraphQLClient())
        service, _ = make_service(gql2, products=[replace(eur_product(), currency="")])
        await service.create(replace(VALID_CREATE, list_price="10"))
        assert quote_tickets(gql2)[0]["price"]["currency"] == "USD"

    async def test_omits_the_ticket_price_when_no_list_price_is_given(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql))
        await service.create(VALID_CREATE)
        assert all("price" not in t for t in quote_tickets(gql))

    async def test_raises_on_an_invalid_list_price_before_any_network_call(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="positive number"):
            await service.create(replace(VALID_CREATE, list_price="abc"))
        assert gql.calls == []

    async def test_clones_from_a_parent_order_when_provided(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql))
        await service.create(replace(VALID_CREATE, parent_order_id="o_parent"))
        assert quote_input_of(gql)["source"] == {"clonedFromId": "o_parent"}

    async def test_resolves_custom_question_answers_by_id_and_text_onto_the_quote(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql), questions=QUESTIONS)

        await service.create(
            replace(
                VALID_CREATE,
                custom_question_answers=answers(
                    ("cq_text", "No nuts"),
                    ("Adult Only?", "yes"),  # text match → checkbox
                    ("cq_pick", "option b"),  # fuzzy option label
                ),
            )
        )

        resolved = booking_quote_of(gql)["questionAnswers"]
        assert len(resolved) == 3
        assert resolved[0]["questionId"] == "cq_text"
        assert resolved[0]["questionAnswerText"] == "No nuts"
        assert (
            resolved[1]["questionId"],
            resolved[1]["isChecked"],
            resolved[1]["questionAnswerText"],
        ) == (
            "cq_check",
            True,
            "Yes",
        )
        assert (
            resolved[2]["questionId"],
            resolved[2]["questionAnswerOptionId"],
            resolved[2]["questionAnswerText"],
        ) == (
            "cq_pick",
            "cqao_b",
            "Option B",
        )
        # Each answer carries a fresh, unique refid.
        refids = [a["refid"] for a in resolved]
        assert all(isinstance(r, str) and r for r in refids)
        assert len(set(refids)) == 3

    async def test_omits_question_answers_when_none_are_supplied(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql), questions=QUESTIONS)
        await service.create(VALID_CREATE)
        assert "questionAnswers" not in booking_quote_of(gql)

    async def test_fails_an_unmatched_question_before_making_a_quote(self, gql: FakeGraphQLClient):
        service, _ = make_service(gql, questions=QUESTIONS)
        with pytest.raises(ValueError, match="No custom question matches id"):
            await service.create(
                replace(VALID_CREATE, custom_question_answers=answers(("cq_missing", "x")))
            )
        assert calls_with(gql, "createQuoteV2") == []

    async def test_fails_an_invalid_checkbox_value_before_making_a_quote(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql, questions=QUESTIONS)
        with pytest.raises(ValueError, match="must be yes/no/true/false"):
            await service.create(
                replace(VALID_CREATE, custom_question_answers=answers(("cq_check", "maybe")))
            )
        assert calls_with(gql, "createQuoteV2") == []

    async def test_rejects_a_per_guest_question_before_making_a_quote(self, gql: FakeGraphQLClient):
        per_guest = [q(id="cq_pg", question_text="Waiver", question_type="TEXT", per_guest=True)]
        service, _ = make_service(gql, questions=per_guest)
        with pytest.raises(ValueError, match="not yet supported"):
            await service.create(
                replace(VALID_CREATE, custom_question_answers=answers(("cq_pg", "x")))
            )
        assert calls_with(gql, "createQuoteV2") == []

    async def test_require_required_questions_fails_when_a_required_question_is_unanswered(
        self, gql: FakeGraphQLClient
    ):
        required = [
            q(id="cq_req", question_text="Dietary Notes", question_type="TEXT", is_required=True)
        ]
        service, _ = make_service(gql, questions=required)
        with pytest.raises(ValueError, match=r"\(cq_req\) is required but was not answered"):
            await service.create(replace(VALID_CREATE, require_required_questions=True))
        assert calls_with(gql, "createQuoteV2") == []

    async def test_require_required_questions_passes_when_the_required_question_is_answered(
        self, gql: FakeGraphQLClient
    ):
        required = [
            q(id="cq_req", question_text="Dietary Notes", question_type="TEXT", is_required=True)
        ]
        service, _ = make_service(queue_create(gql), questions=required)
        await service.create(
            replace(
                VALID_CREATE,
                require_required_questions=True,
                custom_question_answers=answers(("cq_req", "vegan")),
            )
        )
        resolved = booking_quote_of(gql)["questionAnswers"]
        assert len(resolved) == 1
        assert (resolved[0]["questionId"], resolved[0]["questionAnswerText"]) == ("cq_req", "vegan")

    async def test_require_required_questions_omits_question_answers_when_nothing_is_required_or_answered(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql), questions=QUESTIONS)
        await service.create(replace(VALID_CREATE, require_required_questions=True))
        assert "questionAnswers" not in booking_quote_of(gql)

    async def test_accept_all_custom_question_ids_accepts_an_unknown_id_and_skips_the_questions_fetch(
        self, gql: FakeGraphQLClient
    ):
        service, product_service = make_service(queue_create(gql), questions=QUESTIONS)
        await service.create(
            replace(
                VALID_CREATE,
                accept_all_custom_question_ids=True,
                custom_question_answers=answers(("cq_notinlist", "free text")),
            )
        )
        # Every answer was by id, so the activity's questions were never fetched.
        assert product_service.question_fetch_count == 0
        resolved = booking_quote_of(gql)["questionAnswers"]
        assert len(resolved) == 1
        assert (resolved[0]["questionId"], resolved[0]["questionAnswerText"]) == (
            "cq_notinlist",
            "free text",
        )

    async def test_accept_all_custom_question_ids_still_fetches_questions_to_resolve_a_by_name_answer(
        self, gql: FakeGraphQLClient
    ):
        service, product_service = make_service(queue_create(gql), questions=QUESTIONS)
        await service.create(
            replace(
                VALID_CREATE,
                accept_all_custom_question_ids=True,
                custom_question_answers=answers(
                    ("cq_unknown", "blind"),  # accepted as text
                    ("Dietary Notes", "vegan"),  # needs the list
                ),
            )
        )
        assert product_service.question_fetch_count == 1
        resolved = booking_quote_of(gql)["questionAnswers"]
        assert len(resolved) == 2
        assert (resolved[0]["questionId"], resolved[0]["questionAnswerText"]) == (
            "cq_unknown",
            "blind",
        )
        assert (resolved[1]["questionId"], resolved[1]["questionAnswerText"]) == (
            "cq_text",
            "vegan",
        )

    @pytest.mark.parametrize("parent_order_id", ["o_abc123", "O-123ABC"])
    async def test_accepts_a_valid_parent_order_id(
        self, gql: FakeGraphQLClient, parent_order_id: str
    ):
        service, _ = make_service(queue_create(gql))
        assert (
            await service.create(replace(VALID_CREATE, parent_order_id=parent_order_id)) is not None
        )

    # Rejected: no prefix, mismatched case/separator, or a booking id.
    @pytest.mark.parametrize("parent_order_id", ["ord-parent", "o-Ab123", "b_abc123"])
    async def test_rejects_an_invalid_parent_order_id(
        self, gql: FakeGraphQLClient, parent_order_id: str
    ):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match="valid order id"):
            await service.create(replace(VALID_CREATE, parent_order_id=parent_order_id))

    async def test_marks_the_booking_paid_with_the_full_balance(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql, payment=PAYMENT_OK))
        result = await service.create(
            replace(VALID_CREATE, mark_as_paid=True, idempotency_key="k1")
        )
        assert result.transaction_id == "tx-1"
        assert call_with(gql, "applyPaymentToOrder").variables["input"] == {
            "amount": {"amount": "100.00", "currency": "USD"},
            "orderId": "o_1",
            "paymentSourceId": "custom/other",
            "idempotencyKey": "k1",
            "customerMessage": "Marked as paid",
            "scopedTo": ["b_1"],
        }

    async def test_marks_the_booking_paid_with_a_partial_amount(self, gql: FakeGraphQLClient):
        service, _ = make_service(queue_create(gql, payment=PAYMENT_OK))
        await service.create(
            replace(VALID_CREATE, mark_as_paid=True, mark_as_paid_amount="50", idempotency_key="k1")
        )
        assert (
            call_with(gql, "applyPaymentToOrder").variables["input"]["amount"]["amount"] == "50.00"
        )

    @pytest.mark.parametrize("partial", ["abc", "-5", "0"])
    async def test_falls_back_to_the_full_balance_for_a_non_positive_partial_amount(
        self, gql: FakeGraphQLClient, partial: str
    ):
        service, _ = make_service(queue_create(gql, payment=PAYMENT_OK))
        await service.create(
            replace(
                VALID_CREATE, mark_as_paid=True, mark_as_paid_amount=partial, idempotency_key="k1"
            )
        )
        assert (
            call_with(gql, "applyPaymentToOrder").variables["input"]["amount"]["amount"] == "100.00"
        )

    async def test_raises_when_the_quote_fails(self, gql: FakeGraphQLClient):
        service, _ = make_service(
            queue_create(gql, quote={"createQuoteV2": {"errors": None, "quote": None}}, order=None)
        )
        with pytest.raises(ValueError, match="Failed to create quote"):
            await service.create(VALID_CREATE)

    async def test_raises_when_the_order_has_errors(self, gql: FakeGraphQLClient):
        order = {
            "createOrderFromQuote": {
                "errors": [{"code": "X", "detail": "no", "value": None}],
                "order": None,
            }
        }
        service, _ = make_service(queue_create(gql, order=order))
        with pytest.raises(ValueError, match="Failed to create order from quote"):
            await service.create(VALID_CREATE)

    async def test_raises_when_the_order_has_no_sales(self, gql: FakeGraphQLClient):
        order = {"createOrderFromQuote": {"errors": None, "order": {"id": "o_1", "sales": []}}}
        service, _ = make_service(queue_create(gql, order=order))
        with pytest.raises(ValueError, match="no sales found"):
            await service.create(VALID_CREATE)

    async def test_raises_when_marking_paid_fails(self, gql: FakeGraphQLClient):
        payment = {
            "applyPaymentToOrder": {
                "transactionId": None,
                "errors": [{"code": "X", "detail": "no", "value": None}],
            }
        }
        service, _ = make_service(queue_create(gql, payment=payment))
        with pytest.raises(ValueError, match="Failed to mark booking as paid"):
            await service.create(replace(VALID_CREATE, mark_as_paid=True, idempotency_key="k1"))

    @pytest.mark.parametrize(
        ("overrides", "pattern"),
        [
            ({"activity_id": ""}, "activityId is required"),
            ({"availability_time_id": ""}, "availabilityTimeId is required"),
            ({"tickets": []}, "at least one ticket"),
            (
                {"tickets": [CreateBookingTicket(resource_option_id="r1", quantity=0)]},
                "positive quantity",
            ),
            (
                {"tickets": [CreateBookingTicket(resource_option_id="", quantity=1)]},
                "positive quantity",
            ),
            ({"guest": CreateBookingGuest(name="")}, "guest name is required"),
            ({"mark_as_paid": True}, "idempotencyKey is required when markAsPaid"),
        ],
    )
    async def test_rejects_invalid_input(
        self, gql: FakeGraphQLClient, overrides: dict[str, Any], pattern: str
    ):
        service, _ = make_service(gql)
        with pytest.raises(ValueError, match=pattern):
            await service.create(replace(VALID_CREATE, **overrides))
        assert gql.calls == []


class TestAccessOptions:
    async def test_requests_no_pii_fields_and_nulls_pii_on_the_result_for_get_by_id(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(gql.queue(listing([NODE])), full_customer_access=False)
        booking = await service.get_by_id("b_1")
        query = collapse(gql.calls[0].query)
        assert "bookingPortalUrl" not in query
        assert "primaryGuest { name" not in query
        assert "questionAnswers" not in query
        assert booking is not None
        assert booking.customer_name == ""
        assert booking.customer_email is None
        assert booking.portal_url is None

    async def test_returns_guests_without_identity_fields_for_get_guests(
        self, gql: FakeGraphQLClient
    ):
        gql.queue(
            {
                "sales": {
                    "edges": [
                        {
                            "node": {
                                "displayId": "B-1",
                                "id": "b_1",
                                "primaryGuest": {"id": "g1"},
                                "bookingGuests": [{"id": "g1", "isParticipant": True}],
                            }
                        }
                    ]
                }
            }
        )
        service, _ = make_service(gql, full_customer_access=False)
        guests = await service.get_guests("b_1")
        assert guests[0].id == "g1"
        assert guests[0].name is None
        assert guests[0].email is None
        assert "dateOfBirth" not in gql.calls[0].query
        assert "fieldResponses" not in gql.calls[0].query

    @pytest.mark.parametrize(
        ("operation", "call"),
        [
            ("get_payments_on_file", lambda s: s.get_payments_on_file("b_1")),
            (
                "make_payment",
                lambda s: s.make_payment(
                    MakePaymentInput(
                        booking_id="b_1",
                        payment_source_id="ps_1",
                        amount="1.00",
                        currency="USD",
                        idempotency_key="k",
                    )
                ),
            ),
            (
                "refund",
                lambda s: s.refund(
                    RefundInput(
                        booking_id="b_1",
                        payment_id="pmt_1",
                        amount="1.00",
                        currency="USD",
                        idempotency_key="k",
                    )
                ),
            ),
            ("create_invoice_link", lambda s: s.create_invoice_link("b_1")),
            (
                "add_addon",
                lambda s: s.add_addon("b_1", AddAddonInput(addon_option_id="io_1", quantity="1")),
            ),
            (
                "remove_addon",
                lambda s: s.remove_addon(
                    "b_1", AddAddonInput(addon_option_id="io_1", quantity="1")
                ),
            ),
        ],
    )
    async def test_disables_the_operation_and_makes_no_network_call_when_full_customer_access_is_false(
        self,
        gql: FakeGraphQLClient,
        operation: str,
        call: Callable[[BookingService], Awaitable[object]],
    ):
        service, _ = make_service(gql, full_customer_access=False)
        with pytest.raises(PiiAccessDisabledError) as exc_info:
            await call(service)
        assert exc_info.value.operation == operation
        assert gql.calls == []

    async def test_still_allows_create_with_mark_as_paid_when_full_customer_access_is_false(
        self, gql: FakeGraphQLClient
    ):
        service, _ = make_service(queue_create(gql, payment=PAYMENT_OK), full_customer_access=False)
        result = await service.create(
            CreateBookingInput(
                activity_id="act-1",
                availability_time_id="avail-1",
                tickets=[CreateBookingTicket(resource_option_id="r1", quantity=1)],
                guest=CreateBookingGuest(name="Ada"),
                mark_as_paid=True,
                idempotency_key="k1",
            )
        )
        assert result.transaction_id == "tx-1"
