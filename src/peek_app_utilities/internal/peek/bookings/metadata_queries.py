"""Raw Peek GraphQL selection, query builder, and response shapes for a booking's
custom-field metadata (``fieldResponses``). Internal.

The query is a variant of the single-booking read: it reuses the shared
``sales(...)`` envelope (:func:`build_sales_query`) and the shared variable
builder (``build_bookings_variables``), selecting only the field-response tree.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

from peek_app_utilities.internal.peek.bookings.booking_queries import build_sales_query

# The `GuestFieldResponseValue` selection. The customer-identity fields
# (`name`/`email`/`dateOfBirth`) are PII — selected only when
# `full_customer_access` is set, so without it the API never returns them
# (→ `None` in the converter). `notes`/`waiverSigned` always stay.
_GUEST_VALUE_PII_FIELDS: Final = "dateOfBirth\n      email\n      name\n      "


def _build_guest_value_fields(full_customer_access: bool) -> str:
    return f"""... on GuestFieldResponseValue {{
      {_GUEST_VALUE_PII_FIELDS if full_customer_access else ""}notes
      waiverSigned
    }}"""


def _build_meta_data_value_selection(full_customer_access: bool) -> str:
    """Builds the ``value { __typename … }`` union selection. ``__typename`` is
    selected so the converter can discriminate the variant cleanly. The only part
    that varies is the PII-gated guest fragment."""
    return f"""value {{
    __typename
    ... on AgeFieldResponseValue {{ age }}
    ... on AttachmentFieldResponseValue {{ attachmentUrl mime name size }}
    ... on BarcodeFieldResponseValue {{ barcodeType barcodeValue }}
    ... on BooleanFieldResponseValue {{ boolean }}
    ... on CheckboxFieldResponseValue {{ isChecked }}
    ... on CurrencyFieldResponseValue {{ currency }}
    ... on DateFieldResponseValue {{ date }}
    ... on DecimalFieldResponseValue {{ decimal }}
    ... on DurationFieldResponseValue {{ duration {{ amount unit }} }}
    ... on EmailFieldResponseValue {{ email }}
    {_build_guest_value_fields(full_customer_access)}
    ... on HtmlFieldResponseValue {{ html }}
    ... on ImageUrlFieldResponseValue {{ imageUrl }}
    ... on IntegerFieldResponseValue {{ integer }}
    ... on LocationFieldResponseValue {{ country county locality postalCode region streetAddress }}
    ... on LongTextFieldResponseValue {{ longText }}
    ... on MetaFieldResponseValue {{ meta }}
    ... on PercentFieldResponseValue {{ percent }}
    ... on PhoneFieldResponseValue {{ phone }}
    ... on ShortTextFieldResponseValue {{ shortText }}
    ... on TimeFieldResponseValue {{ time }}
    ... on UrlFieldResponseValue {{ url }}
    ... on VolumeFieldResponseValue {{ volume {{ amount unit }} }}
    ... on WeightFieldResponseValue {{ weight {{ amount unit }} }}
  }}"""


def build_booking_meta_data_query(full_customer_access: bool) -> str:
    """Builds the booking-metadata query. Without ``full_customer_access`` the
    guest value's identity fields (name/email/DOB) are not requested at all."""
    return build_sales_query(f"""
    ... on Booking {{
      displayId
      id
      fieldResponses {{
        fieldLocation {{
          field {{ id name slug type }}
          prompt {{ label hint isRequired }}
        }}
        refid
        {_build_meta_data_value_selection(full_customer_access)}
      }}
    }}
  """)


UPSERT_BOOKING_FIELD_RESPONSES_MUTATION: Final = """
  mutation UpsertBookingFieldResponses($input: UpsertBookingFieldResponsesInput!) {
    upsertBookingFieldResponses(input: $input) {
      __typename
      ... on UpsertBookingFieldResponsesSuccess { bookingId message }
      ... on BookingNotFoundError { message bookingId }
      ... on GenericError { message }
    }
  }
"""
"""Upserts a booking's custom-field responses, scoped to an integrator. The
result is a union — success or one of two typed errors — discriminated by
``__typename``."""


class UpsertBookingFieldResponsesNode(TypedDict, total=False):
    __typename: str
    bookingId: str | None
    message: str | None


# ---- Raw response shapes -------------------------------------------------


class MetaDataValueNode(TypedDict, total=False):
    """The raw union value node — one branch populated per ``__typename``."""

    __typename: str
    age: int | None
    attachmentUrl: str | None
    mime: str | None
    name: str | None
    size: int | None
    barcodeType: str | None
    barcodeValue: str | None
    boolean: bool | None
    isChecked: bool | None
    currency: str | None
    date: str | None
    decimal: str | None
    duration: dict[str, Any] | None
    email: str | None
    dateOfBirth: str | None
    notes: str | None
    waiverSigned: bool | None
    html: str | None
    imageUrl: str | None
    integer: int | None
    country: str | None
    county: str | None
    locality: str | None
    postalCode: str | None
    region: str | None
    streetAddress: str | None
    longText: str | None
    meta: Any
    percent: str | None
    phone: str | None
    shortText: str | None
    time: str | None
    url: str | None
    volume: dict[str, Any] | None
    weight: dict[str, Any] | None


class MetaDataFieldResponseNode(TypedDict, total=False):
    fieldLocation: dict[str, Any] | None
    refid: str
    value: MetaDataValueNode | None


class BookingMetaDataNode(TypedDict, total=False):
    displayId: str
    id: str
    fieldResponses: list[MetaDataFieldResponseNode] | None
