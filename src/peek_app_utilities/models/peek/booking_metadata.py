"""The clean, transport-agnostic data model for a booking's custom-field
metadata (the booking's ``fieldResponses``).

Each :class:`MetaData` entry flattens the field definition (id/name/slug/type),
its prompt (label/hint/required), and the response ``refid``, and carries a
single typed :data:`MetaDataValue` — a discriminated union (keyed by ``kind``)
mirroring the API's ``FieldResponseValue`` variants, so exactly one shape is
present per entry and consumers narrow on ``kind``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union

MetaDataBarcodeType = Literal[
    "BARCODE_CODE128",
    "BARCODE_CODE39",
    "DATA_MATRIX",
    "EAN_13",
    "ITF",
    "QR_CODE",
    "TEXT",
    "UPC",
]
"""Barcode symbology reported on a ``kind: "barcode"`` metadata value."""

MetaDataDurationUnit = Literal["SECONDS", "MINUTES", "HOURS", "DAYS", "WEEKS", "MONTHS", "YEARS"]
"""Time unit reported on a ``kind: "duration"`` metadata value."""

MetaDataWeightUnit = Literal["KILOGRAM", "POUND", "STONE"]
"""Mass unit reported on a ``kind: "weight"`` metadata value."""

MetaDataVolumeUnit = Literal["GALLON"]
"""Volume unit reported on a ``kind: "volume"`` metadata value."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataAgeValue:
    kind: Literal["age"] = "age"
    age: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataAttachmentValue:
    kind: Literal["attachment"] = "attachment"
    attachment_url: str
    mime: str | None
    name: str | None
    size: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataBarcodeValue:
    kind: Literal["barcode"] = "barcode"
    barcode_type: MetaDataBarcodeType | None
    barcode_value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataBooleanValue:
    kind: Literal["boolean"] = "boolean"
    boolean: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataCheckboxValue:
    kind: Literal["checkbox"] = "checkbox"
    is_checked: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataCurrencyValue:
    kind: Literal["currency"] = "currency"
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataDateValue:
    kind: Literal["date"] = "date"
    date: str
    """ISO date string."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataDecimalValue:
    kind: Literal["decimal"] = "decimal"
    decimal: str | None
    """Kept as a string to avoid float-precision loss."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataDurationValue:
    kind: Literal["duration"] = "duration"
    amount: int
    unit: MetaDataDurationUnit | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataEmailValue:
    kind: Literal["email"] = "email"
    email: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataGuestValue:
    """The identity fields (``name``/``email``/``date_of_birth``) are PII and come
    back ``None`` unless the access service has ``full_customer_access``."""

    kind: Literal["guest"] = "guest"
    name: str | None
    email: str | None
    date_of_birth: str | None
    notes: str | None
    waiver_signed: bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataHtmlValue:
    kind: Literal["html"] = "html"
    html: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataImageUrlValue:
    kind: Literal["imageUrl"] = "imageUrl"
    image_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataIntegerValue:
    kind: Literal["integer"] = "integer"
    integer: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataLocationValue:
    kind: Literal["location"] = "location"
    country: str | None
    county: str | None
    locality: str | None
    postal_code: str | None
    region: str | None
    street_address: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataLongTextValue:
    kind: Literal["longText"] = "longText"
    long_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataMetaValue:
    kind: Literal["meta"] = "meta"
    meta: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataPercentValue:
    kind: Literal["percent"] = "percent"
    percent: str | None
    """Kept as a string to avoid float-precision loss."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataPhoneValue:
    kind: Literal["phone"] = "phone"
    phone: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataShortTextValue:
    kind: Literal["shortText"] = "shortText"
    short_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataTimeValue:
    kind: Literal["time"] = "time"
    time: str
    """ISO time string."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataUrlValue:
    kind: Literal["url"] = "url"
    url: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataVolumeValue:
    kind: Literal["volume"] = "volume"
    amount: str
    unit: MetaDataVolumeUnit | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaDataWeightValue:
    kind: Literal["weight"] = "weight"
    amount: str
    unit: MetaDataWeightUnit | None


MetaDataValue = Union[  # noqa: UP007 — an explicit alias reads better than a 24-arm `|` chain
    MetaDataAgeValue,
    MetaDataAttachmentValue,
    MetaDataBarcodeValue,
    MetaDataBooleanValue,
    MetaDataCheckboxValue,
    MetaDataCurrencyValue,
    MetaDataDateValue,
    MetaDataDecimalValue,
    MetaDataDurationValue,
    MetaDataEmailValue,
    MetaDataGuestValue,
    MetaDataHtmlValue,
    MetaDataImageUrlValue,
    MetaDataIntegerValue,
    MetaDataLocationValue,
    MetaDataLongTextValue,
    MetaDataMetaValue,
    MetaDataPercentValue,
    MetaDataPhoneValue,
    MetaDataShortTextValue,
    MetaDataTimeValue,
    MetaDataUrlValue,
    MetaDataVolumeValue,
    MetaDataWeightValue,
]
"""A booking custom-field response value — a discriminated union keyed by
``kind``, one variant per API ``…FieldResponseValue`` type. Numeric ``Int``
values are ``int``; ``Decimal`` values are kept as strings to avoid
float-precision loss; ``Date``/``Time`` values are ISO strings.

A human-readable, display-safe rendering of the value lives on the parent
:attr:`MetaData.display_value`, not here.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetaData:
    """A single booking custom-field response (one ``fieldResponse``)."""

    id: str
    """Field definition id."""
    name: str
    """Field name (human label)."""
    slug: str
    """Field slug. When an ``integrator`` filter is applied, the matched
    ``integrators:<integrator>:`` prefix is stripped off (e.g.
    ``integrators:bob:booking_url`` → ``booking_url``)."""
    type: str
    """Raw field type reported by the API (kept as a string)."""
    prompt: str | None
    """Prompt label shown for the field, or ``None`` when the field has no prompt."""
    prompt_hint: str | None
    """Prompt hint text, or ``None``."""
    is_required: bool
    """Whether the field is required (``False`` when the field has no prompt)."""
    refid: str
    """The response's reference id."""
    display_value: str
    """A human-readable, display-safe string rendering of the value. Always
    present — ``""`` when the value is absent or of an unrecognized variant. The
    ``html`` value's rendering is HTML-escaped so it is safe to render as text."""
    value: MetaDataValue | None
    """The typed response value, or ``None`` when absent or of an unrecognized
    (future) variant."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SetMetaDataGuestInput:
    """A guest entry for ``BookingService.set_meta_data_guest``."""

    name: str
    """Guest name (required)."""
    email: str
    """Guest email (required)."""
    date_of_birth: str | None = None
    """Date of birth as an ISO date (e.g. ``"2010-06-21"``)."""
    waiver_signed: bool | None = None
    """Whether the guest signed the waiver."""
    notes: str | None = None
    """Free-text notes."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SetMetaDataAttachmentInput:
    """An attachment entry for ``BookingService.set_meta_data_attachment``."""

    name: str
    """Display name for the attachment (required)."""
    attachment_url: str
    """URL of the attachment (required)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SetMetaDataResult:
    """The result of a ``set_meta_data_…`` write."""

    success: bool
    """Whether the API reported the upsert succeeded."""
    booking_id: str
    """The booking id echoed back (falls back to the requested id)."""
    message: str
    """The API's success or error message (``""`` when none)."""
