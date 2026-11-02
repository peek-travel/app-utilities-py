"""Pure functions mapping a raw booking-metadata node into the clean
:class:`MetaData` list, plus the integrator filter. I/O-free.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, Final, cast

from peek_app_utilities.models.peek.booking_metadata import (
    MetaData,
    MetaDataAgeValue,
    MetaDataAttachmentValue,
    MetaDataBarcodeType,
    MetaDataBarcodeValue,
    MetaDataBooleanValue,
    MetaDataCheckboxValue,
    MetaDataCurrencyValue,
    MetaDataDateValue,
    MetaDataDecimalValue,
    MetaDataDurationUnit,
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
    MetaDataValue,
    MetaDataVolumeUnit,
    MetaDataVolumeValue,
    MetaDataWeightUnit,
    MetaDataWeightValue,
    SetMetaDataResult,
)

_UPSERT_SUCCESS_TYPENAME: Final = "UpsertBookingFieldResponsesSuccess"
"""The ``__typename`` of the successful upsert result variant."""

_INTEGRATOR_SLUG_PREFIX: Final = "integrators:"
_DISPLAY_YES: Final = "Yes"
_DISPLAY_NO: Final = "No"
_DEFAULT_DECIMAL_AMOUNT: Final = "0"

RawNode = Mapping[str, Any]
ValueAndDisplay = tuple[MetaDataValue | None, str]
"""A typed value paired with its display-safe rendering."""


def from_booking_meta_data_node(node: RawNode | None) -> list[MetaData]:
    """Converts a raw booking-metadata node into a list of clean :class:`MetaData`."""
    return [_from_field_response_node(r or {}) for r in (node or {}).get("fieldResponses") or []]


def _from_field_response_node(response: RawNode) -> MetaData:
    location: RawNode = response.get("fieldLocation") or {}
    field: RawNode = location.get("field") or {}
    prompt: RawNode = location.get("prompt") or {}
    value, display_value = _from_value_node(response.get("value"))
    return MetaData(
        id=field.get("id") or "",
        name=field.get("name") or "",
        slug=field.get("slug") or "",
        type=field.get("type") or "",
        prompt=prompt.get("label"),
        prompt_hint=prompt.get("hint"),
        is_required=bool(prompt.get("isRequired")),
        refid=response.get("refid") or "",
        display_value=display_value,
        value=value,
    )


def _or(value: Any, default: Any) -> Any:
    """``??`` — the default only for an absent/``None`` value (``""``/``0``/``False`` stay)."""
    return default if value is None else value


def _yes_no(value: bool) -> str:
    return _DISPLAY_YES if value else _DISPLAY_NO


def _amount_unit(amount: int | str, unit: str | None) -> str:
    """``"<amount> <unit>"`` (unit lowercased), or just the amount when no unit."""
    return f"{amount} {unit.lower()}" if unit else str(amount)


def _escape_html(value: str) -> str:
    """Escapes the five HTML-significant characters so a string is safe to render as text."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _age(v: RawNode) -> ValueAndDisplay:
    age = _or(v.get("age"), 0)
    return MetaDataAgeValue(age=age), str(age)


def _attachment(v: RawNode) -> ValueAndDisplay:
    attachment_url = _or(v.get("attachmentUrl"), "")
    name = v.get("name")
    return (
        MetaDataAttachmentValue(
            attachment_url=attachment_url, mime=v.get("mime"), name=name, size=v.get("size")
        ),
        name or attachment_url,
    )


def _barcode(v: RawNode) -> ValueAndDisplay:
    barcode_value = _or(v.get("barcodeValue"), "")
    barcode_type = cast("MetaDataBarcodeType | None", v.get("barcodeType"))
    return MetaDataBarcodeValue(
        barcode_type=barcode_type, barcode_value=barcode_value
    ), barcode_value


def _boolean(v: RawNode) -> ValueAndDisplay:
    flag = bool(v.get("boolean"))
    return MetaDataBooleanValue(boolean=flag), _yes_no(flag)


def _checkbox(v: RawNode) -> ValueAndDisplay:
    is_checked = bool(v.get("isChecked"))
    return MetaDataCheckboxValue(is_checked=is_checked), _yes_no(is_checked)


def _currency(v: RawNode) -> ValueAndDisplay:
    currency = _or(v.get("currency"), "")
    return MetaDataCurrencyValue(currency=currency), currency


def _date(v: RawNode) -> ValueAndDisplay:
    date = _or(v.get("date"), "")
    return MetaDataDateValue(date=date), date


def _decimal(v: RawNode) -> ValueAndDisplay:
    decimal = v.get("decimal")
    return MetaDataDecimalValue(decimal=decimal), _or(decimal, "")


def _duration(v: RawNode) -> ValueAndDisplay:
    duration: RawNode = v.get("duration") or {}
    amount = _or(duration.get("amount"), 0)
    unit = cast("MetaDataDurationUnit | None", duration.get("unit"))
    return MetaDataDurationValue(amount=amount, unit=unit), _amount_unit(amount, unit)


def _email(v: RawNode) -> ValueAndDisplay:
    email = v.get("email")
    return MetaDataEmailValue(email=email), _or(email, "")


def _guest(v: RawNode) -> ValueAndDisplay:
    name = v.get("name")
    return (
        MetaDataGuestValue(
            name=name,
            email=v.get("email"),
            date_of_birth=v.get("dateOfBirth"),
            notes=v.get("notes"),
            waiver_signed=v.get("waiverSigned"),
        ),
        _or(name, ""),
    )


def _html(v: RawNode) -> ValueAndDisplay:
    html = _or(v.get("html"), "")
    return MetaDataHtmlValue(html=html), _escape_html(html)


def _image_url(v: RawNode) -> ValueAndDisplay:
    image_url = _or(v.get("imageUrl"), "")
    return MetaDataImageUrlValue(image_url=image_url), image_url


def _integer(v: RawNode) -> ValueAndDisplay:
    integer = _or(v.get("integer"), 0)
    return MetaDataIntegerValue(integer=integer), str(integer)


def _location(v: RawNode) -> ValueAndDisplay:
    street_address = v.get("streetAddress")
    locality = v.get("locality")
    region = v.get("region")
    postal_code = v.get("postalCode")
    country = v.get("country")
    return (
        MetaDataLocationValue(
            country=country,
            county=v.get("county"),
            locality=locality,
            postal_code=postal_code,
            region=region,
            street_address=street_address,
        ),
        ", ".join(
            part for part in (street_address, locality, region, postal_code, country) if part
        ),
    )


def _long_text(v: RawNode) -> ValueAndDisplay:
    long_text = _or(v.get("longText"), "")
    return MetaDataLongTextValue(long_text=long_text), long_text


def _meta(v: RawNode) -> ValueAndDisplay:
    meta = v.get("meta")
    display = "" if meta is None else json.dumps(meta, separators=(",", ":"), ensure_ascii=False)
    return MetaDataMetaValue(meta=meta), display


def _percent(v: RawNode) -> ValueAndDisplay:
    percent = v.get("percent")
    return MetaDataPercentValue(percent=percent), "" if percent is None else f"{percent}%"


def _phone(v: RawNode) -> ValueAndDisplay:
    phone = _or(v.get("phone"), "")
    return MetaDataPhoneValue(phone=phone), phone


def _short_text(v: RawNode) -> ValueAndDisplay:
    short_text = _or(v.get("shortText"), "")
    return MetaDataShortTextValue(short_text=short_text), short_text


def _time(v: RawNode) -> ValueAndDisplay:
    time = _or(v.get("time"), "")
    return MetaDataTimeValue(time=time), time


def _url(v: RawNode) -> ValueAndDisplay:
    url = v.get("url")
    return MetaDataUrlValue(url=url), _or(url, "")


def _volume(v: RawNode) -> ValueAndDisplay:
    volume: RawNode = v.get("volume") or {}
    amount = _or(volume.get("amount"), _DEFAULT_DECIMAL_AMOUNT)
    unit = cast("MetaDataVolumeUnit | None", volume.get("unit"))
    return MetaDataVolumeValue(amount=amount, unit=unit), _amount_unit(amount, unit)


def _weight(v: RawNode) -> ValueAndDisplay:
    weight: RawNode = v.get("weight") or {}
    amount = _or(weight.get("amount"), _DEFAULT_DECIMAL_AMOUNT)
    unit = cast("MetaDataWeightUnit | None", weight.get("unit"))
    return MetaDataWeightValue(amount=amount, unit=unit), _amount_unit(amount, unit)


_VALUE_MAPPERS: Final[Mapping[str, Callable[[RawNode], ValueAndDisplay]]] = {
    "AgeFieldResponseValue": _age,
    "AttachmentFieldResponseValue": _attachment,
    "BarcodeFieldResponseValue": _barcode,
    "BooleanFieldResponseValue": _boolean,
    "CheckboxFieldResponseValue": _checkbox,
    "CurrencyFieldResponseValue": _currency,
    "DateFieldResponseValue": _date,
    "DecimalFieldResponseValue": _decimal,
    "DurationFieldResponseValue": _duration,
    "EmailFieldResponseValue": _email,
    "GuestFieldResponseValue": _guest,
    "HtmlFieldResponseValue": _html,
    "ImageUrlFieldResponseValue": _image_url,
    "IntegerFieldResponseValue": _integer,
    "LocationFieldResponseValue": _location,
    "LongTextFieldResponseValue": _long_text,
    "MetaFieldResponseValue": _meta,
    "PercentFieldResponseValue": _percent,
    "PhoneFieldResponseValue": _phone,
    "ShortTextFieldResponseValue": _short_text,
    "TimeFieldResponseValue": _time,
    "UrlFieldResponseValue": _url,
    "VolumeFieldResponseValue": _volume,
    "WeightFieldResponseValue": _weight,
}


def _from_value_node(value: RawNode | None) -> ValueAndDisplay:
    """Maps the raw union value node to a typed :data:`MetaDataValue` and its
    display-safe rendering, discriminating on ``__typename``. Returns
    ``(None, "")`` when absent or of an unrecognized (future) variant — unknown
    types are never coerced."""
    if not value:
        return None, ""
    mapper = _VALUE_MAPPERS.get(value.get("__typename") or "")
    if mapper is None:
        return None, ""
    return mapper(value)


def to_set_meta_data_result(node: RawNode | None, booking_id: str) -> SetMetaDataResult:
    """Maps the ``upsertBookingFieldResponses`` result union into a clean
    :class:`SetMetaDataResult`. ``success`` is ``True`` only for the success
    variant; the message and (when present) echoed booking id are carried across,
    falling back to the requested ``booking_id``."""
    result: RawNode = node or {}
    return SetMetaDataResult(
        success=result.get("__typename") == _UPSERT_SUCCESS_TYPENAME,
        booking_id=result.get("bookingId") or booking_id,
        message=result.get("message") or "",
    )


def filter_meta_data_by_integrator(meta_data: list[MetaData], integrator: str) -> list[MetaData]:
    """Keeps only the metadata whose ``slug`` starts with ``integrators:<integrator>:``
    (case-sensitive exact prefix), stripping that prefix off the returned ``slug``
    (e.g. with ``integrator = "bob"``, ``integrators:bob:booking_url`` → ``booking_url``)."""
    prefix = f"{_INTEGRATOR_SLUG_PREFIX}{integrator}:"
    return [
        replace(entry, slug=entry.slug[len(prefix) :])
        for entry in meta_data
        if entry.slug.startswith(prefix)
    ]
