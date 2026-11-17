import re

import pytest

from peek_app_utilities.internal.peek.bookings.metadata_queries import (
    UPSERT_BOOKING_FIELD_RESPONSES_MUTATION,
    build_booking_meta_data_query,
)


def collapse(query: str) -> str:
    """Collapses whitespace so selection sets match regardless of layout."""
    return re.sub(r"\s+", " ", query).strip()


VARIANTS = [
    "Age", "Attachment", "Barcode", "Boolean", "Checkbox", "Currency", "Date",
    "Decimal", "Duration", "Email", "Guest", "Html", "ImageUrl", "Integer",
    "Location", "LongText", "Meta", "Percent", "Phone", "ShortText", "Time",
    "Url", "Volume", "Weight",
]  # fmt: skip


class TestBuildBookingMetaDataQuery:
    def test_selects_the_field_response_tree_inside_the_shared_sales_envelope(self):
        query = collapse(build_booking_meta_data_query(False))
        assert "sales(after: $after, first: $first, filter: $filter, orderBy: $orderBy)" in query
        assert "fieldResponses { fieldLocation { field { id name slug type }" in query
        assert "prompt { label hint isRequired }" in query
        assert "value { __typename" in query
        assert "... on WeightFieldResponseValue { weight { amount unit } }" in query

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_selects_an_inline_fragment_for_every_field_response_value_variant(self, variant: str):
        query = collapse(build_booking_meta_data_query(True))
        assert f"... on {variant}FieldResponseValue" in query

    def test_requests_guest_identity_value_fields_when_full_customer_access_is_true(self):
        query = collapse(build_booking_meta_data_query(True))
        assert (
            "... on GuestFieldResponseValue { dateOfBirth email name notes waiverSigned }" in query
        )

    def test_omits_guest_name_email_date_of_birth_when_full_customer_access_is_false(self):
        query = collapse(build_booking_meta_data_query(False))
        assert "... on GuestFieldResponseValue { notes waiverSigned }" in query
        # PII value fields are not pulled at all.
        assert "dateOfBirth" not in query
        assert "... on GuestFieldResponseValue { dateOfBirth" not in query


class TestUpsertBookingFieldResponsesMutation:
    def test_selects_the_result_union_discriminated_by_typename(self):
        mutation = collapse(UPSERT_BOOKING_FIELD_RESPONSES_MUTATION)
        assert "upsertBookingFieldResponses(input: $input)" in mutation
        assert "__typename" in mutation
        assert "... on UpsertBookingFieldResponsesSuccess { bookingId message }" in mutation
        assert "... on BookingNotFoundError { message bookingId }" in mutation
        assert "... on GenericError { message }" in mutation
