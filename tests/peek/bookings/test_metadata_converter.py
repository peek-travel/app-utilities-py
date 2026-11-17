from dataclasses import asdict, replace
from typing import Any

from peek_app_utilities.internal.peek.bookings.metadata_converter import (
    filter_meta_data_by_integrator,
    from_booking_meta_data_node,
    to_set_meta_data_result,
)
from peek_app_utilities.models.peek.booking_metadata import (
    MetaData,
    MetaDataAgeValue,
    MetaDataGuestValue,
    MetaDataHtmlValue,
    MetaDataMetaValue,
    MetaDataShortTextValue,
    MetaDataUrlValue,
    SetMetaDataResult,
)


def response(slug: str, value: dict[str, Any] | None) -> dict[str, Any]:
    """Wraps a raw value node in a field-response node with a slug."""
    return {
        "fieldLocation": {
            "field": {"id": f"f_{slug}", "name": slug, "slug": slug, "type": "TYPE"},
            "prompt": {"label": "Prompt", "hint": "Hint", "isRequired": True},
        },
        "refid": f"r_{slug}",
        "value": value,
    }


def value_dicts(responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converted values as plain dicts with the parent's display_value flattened in."""
    out: list[dict[str, Any]] = []
    for m in from_booking_meta_data_node(
        {"id": "b", "displayId": "B", "fieldResponses": responses}
    ):
        d = asdict(m.value) if m.value is not None else {}
        d["display_value"] = m.display_value
        out.append(d)
    return out


def value(node: dict[str, Any]) -> dict[str, Any]:
    return value_dicts([response("s", node)])[0]


class TestFromBookingMetaDataNode:
    def test_flattens_field_prompt_refid_into_a_meta_data_list(self):
        node = {
            "id": "b_1",
            "displayId": "B-1",
            "fieldResponses": [
                response(
                    "shortText", {"__typename": "ShortTextFieldResponseValue", "shortText": "hi"}
                )
            ],
        }
        result = from_booking_meta_data_node(node)
        assert result == [
            MetaData(
                id="f_shortText",
                name="shortText",
                slug="shortText",
                type="TYPE",
                prompt="Prompt",
                prompt_hint="Hint",
                is_required=True,
                refid="r_shortText",
                display_value="hi",
                value=MetaDataShortTextValue(short_text="hi"),
            )
        ]

    def test_defaults_prompt_fields_to_none_false_when_the_prompt_is_absent(self):
        node = {
            "id": "b_1",
            "displayId": "B-1",
            "fieldResponses": [
                {
                    "fieldLocation": {
                        "field": {"id": "f", "name": "n", "slug": "s", "type": "t"},
                        "prompt": None,
                    },
                    "refid": "r",
                    "value": None,
                }
            ],
        }
        [entry] = from_booking_meta_data_node(node)
        assert (entry.prompt, entry.prompt_hint, entry.is_required, entry.value) == (
            None,
            None,
            False,
            None,
        )

    def test_maps_every_value_variant_by_typename(self):
        responses = [
            response("age", {"__typename": "AgeFieldResponseValue", "age": 40}),
            response("attachment", {"__typename": "AttachmentFieldResponseValue", "attachmentUrl": "u", "mime": "image/png", "name": "f.png", "size": 12}),
            response("barcode", {"__typename": "BarcodeFieldResponseValue", "barcodeType": "QR_CODE", "barcodeValue": "abc"}),
            response("boolean", {"__typename": "BooleanFieldResponseValue", "boolean": True}),
            response("checkbox", {"__typename": "CheckboxFieldResponseValue", "isChecked": True}),
            response("currency", {"__typename": "CurrencyFieldResponseValue", "currency": "USD"}),
            response("date", {"__typename": "DateFieldResponseValue", "date": "2026-01-01"}),
            response("decimal", {"__typename": "DecimalFieldResponseValue", "decimal": "1.5"}),
            response("duration", {"__typename": "DurationFieldResponseValue", "duration": {"amount": 3, "unit": "HOURS"}}),
            response("email", {"__typename": "EmailFieldResponseValue", "email": "a@b.co"}),
            response("guest", {"__typename": "GuestFieldResponseValue", "name": "Ada", "email": "a@b.co", "dateOfBirth": "1990-01-01", "notes": "n", "waiverSigned": True}),
            response("html", {"__typename": "HtmlFieldResponseValue", "html": "<b>x</b>"}),
            response("imageUrl", {"__typename": "ImageUrlFieldResponseValue", "imageUrl": "img"}),
            response("integer", {"__typename": "IntegerFieldResponseValue", "integer": 7}),
            response("location", {"__typename": "LocationFieldResponseValue", "country": "US", "county": "C", "locality": "L", "postalCode": "P", "region": "R", "streetAddress": "S"}),
            response("longText", {"__typename": "LongTextFieldResponseValue", "longText": "long"}),
            response("meta", {"__typename": "MetaFieldResponseValue", "meta": {"a": 1}}),
            response("percent", {"__typename": "PercentFieldResponseValue", "percent": "12.5"}),
            response("phone", {"__typename": "PhoneFieldResponseValue", "phone": "+1"}),
            response("time", {"__typename": "TimeFieldResponseValue", "time": "10:00"}),
            response("url", {"__typename": "UrlFieldResponseValue", "url": "https://x"}),
            response("volume", {"__typename": "VolumeFieldResponseValue", "volume": {"amount": "2.0", "unit": "GALLON"}}),
            response("weight", {"__typename": "WeightFieldResponseValue", "weight": {"amount": "3.0", "unit": "KILOGRAM"}}),
        ]  # fmt: skip
        assert value_dicts(responses) == [
            {"kind": "age", "age": 40, "display_value": "40"},
            {"kind": "attachment", "attachment_url": "u", "mime": "image/png", "name": "f.png", "size": 12, "display_value": "f.png"},
            {"kind": "barcode", "barcode_type": "QR_CODE", "barcode_value": "abc", "display_value": "abc"},
            {"kind": "boolean", "boolean": True, "display_value": "Yes"},
            {"kind": "checkbox", "is_checked": True, "display_value": "Yes"},
            {"kind": "currency", "currency": "USD", "display_value": "USD"},
            {"kind": "date", "date": "2026-01-01", "display_value": "2026-01-01"},
            {"kind": "decimal", "decimal": "1.5", "display_value": "1.5"},
            {"kind": "duration", "amount": 3, "unit": "HOURS", "display_value": "3 hours"},
            {"kind": "email", "email": "a@b.co", "display_value": "a@b.co"},
            {"kind": "guest", "name": "Ada", "email": "a@b.co", "date_of_birth": "1990-01-01", "notes": "n", "waiver_signed": True, "display_value": "Ada"},
            {"kind": "html", "html": "<b>x</b>", "display_value": "&lt;b&gt;x&lt;/b&gt;"},
            {"kind": "imageUrl", "image_url": "img", "display_value": "img"},
            {"kind": "integer", "integer": 7, "display_value": "7"},
            {"kind": "location", "country": "US", "county": "C", "locality": "L", "postal_code": "P", "region": "R", "street_address": "S", "display_value": "S, L, R, P, US"},
            {"kind": "longText", "long_text": "long", "display_value": "long"},
            {"kind": "meta", "meta": {"a": 1}, "display_value": '{"a":1}'},
            {"kind": "percent", "percent": "12.5", "display_value": "12.5%"},
            {"kind": "phone", "phone": "+1", "display_value": "+1"},
            {"kind": "time", "time": "10:00", "display_value": "10:00"},
            {"kind": "url", "url": "https://x", "display_value": "https://x"},
            {"kind": "volume", "amount": "2.0", "unit": "GALLON", "display_value": "2.0 gallon"},
            {"kind": "weight", "amount": "3.0", "unit": "KILOGRAM", "display_value": "3.0 kilogram"},
        ]  # fmt: skip

    def test_maps_absent_unknown_value_variants_and_missing_scalars_to_defaults(self):
        responses = [
            response("unknown", {"__typename": "SomethingNewFieldResponseValue"}),
            response("nullValue", None),
            response("noTypename", {"age": 5}),
            response("ageDefault", {"__typename": "AgeFieldResponseValue"}),
            response("guestPiiOff", {"__typename": "GuestFieldResponseValue", "notes": "n", "waiverSigned": False}),
        ]  # fmt: skip
        entries = from_booking_meta_data_node(
            {"id": "b", "displayId": "B", "fieldResponses": responses}
        )
        assert entries[0].value is None
        assert entries[0].display_value == ""
        assert entries[1].value is None
        assert entries[2].value is None
        assert entries[3].value == MetaDataAgeValue(age=0)
        assert entries[3].display_value == "0"
        assert entries[4].value == MetaDataGuestValue(
            name=None, email=None, date_of_birth=None, notes="n", waiver_signed=False
        )
        assert entries[4].display_value == ""

    def test_defaults_every_variants_absent_fields_covers_the_fallback_branches(self):
        typenames = [
            "Attachment", "Barcode", "Boolean", "Checkbox", "Currency", "Date", "Decimal",
            "Duration", "Email", "Html", "ImageUrl", "Integer", "Location", "LongText", "Meta",
            "Percent", "Phone", "ShortText", "Time", "Url", "Volume", "Weight",
        ]  # fmt: skip
        responses = [response(t, {"__typename": f"{t}FieldResponseValue"}) for t in typenames]
        assert value_dicts(responses) == [
            {"kind": "attachment", "attachment_url": "", "mime": None, "name": None, "size": None, "display_value": ""},
            {"kind": "barcode", "barcode_type": None, "barcode_value": "", "display_value": ""},
            {"kind": "boolean", "boolean": False, "display_value": "No"},
            {"kind": "checkbox", "is_checked": False, "display_value": "No"},
            {"kind": "currency", "currency": "", "display_value": ""},
            {"kind": "date", "date": "", "display_value": ""},
            {"kind": "decimal", "decimal": None, "display_value": ""},
            {"kind": "duration", "amount": 0, "unit": None, "display_value": "0"},
            {"kind": "email", "email": None, "display_value": ""},
            {"kind": "html", "html": "", "display_value": ""},
            {"kind": "imageUrl", "image_url": "", "display_value": ""},
            {"kind": "integer", "integer": 0, "display_value": "0"},
            {"kind": "location", "country": None, "county": None, "locality": None, "postal_code": None, "region": None, "street_address": None, "display_value": ""},
            {"kind": "longText", "long_text": "", "display_value": ""},
            {"kind": "meta", "meta": None, "display_value": ""},
            {"kind": "percent", "percent": None, "display_value": ""},
            {"kind": "phone", "phone": "", "display_value": ""},
            {"kind": "shortText", "short_text": "", "display_value": ""},
            {"kind": "time", "time": "", "display_value": ""},
            {"kind": "url", "url": None, "display_value": ""},
            {"kind": "volume", "amount": "0", "unit": None, "display_value": "0"},
            {"kind": "weight", "amount": "0", "unit": None, "display_value": "0"},
        ]  # fmt: skip

    def test_html_display_value_escapes_all_five_html_significant_characters(self):
        [entry] = from_booking_meta_data_node(
            {
                "id": "b",
                "displayId": "B",
                "fieldResponses": [
                    response(
                        "html",
                        {
                            "__typename": "HtmlFieldResponseValue",
                            "html": "<a href=\"x\">A & 'B'</a>",
                        },
                    )
                ],
            }
        )
        assert entry.value == MetaDataHtmlValue(html="<a href=\"x\">A & 'B'</a>")
        assert entry.display_value == "&lt;a href=&quot;x&quot;&gt;A &amp; &#39;B&#39;&lt;/a&gt;"

    def test_returns_an_empty_list_for_a_missing_node(self):
        assert from_booking_meta_data_node(None) == []

    def test_returns_an_empty_list_when_the_node_has_no_responses(self):
        assert from_booking_meta_data_node({}) == []
        assert (
            from_booking_meta_data_node({"id": "b_2", "displayId": "B-2", "fieldResponses": None})
            == []
        )

    def test_defaults_the_whole_field_when_field_location_is_absent(self):
        [entry] = from_booking_meta_data_node(
            {"id": "b", "displayId": "B", "fieldResponses": [{"refid": "r", "value": None}]}
        )
        assert entry == MetaData(
            id="",
            name="",
            slug="",
            type="",
            prompt=None,
            prompt_hint=None,
            is_required=False,
            refid="r",
            display_value="",
            value=None,
        )


class TestValueEdgeCases:
    def test_attachment_display_value_prefers_name_falling_back_to_url_when_name_is_empty_or_null(
        self,
    ):
        assert (
            value(
                {
                    "__typename": "AttachmentFieldResponseValue",
                    "attachmentUrl": "https://f",
                    "name": "r.pdf",
                    "size": 1,
                }
            )["display_value"]
            == "r.pdf"
        )
        v = value(
            {"__typename": "AttachmentFieldResponseValue", "attachmentUrl": "https://f", "name": ""}
        )
        assert (v["name"], v["display_value"]) == ("", "https://f")
        v = value(
            {
                "__typename": "AttachmentFieldResponseValue",
                "attachmentUrl": "https://f",
                "name": None,
                "size": 0,
            }
        )
        assert (v["name"], v["size"], v["display_value"]) == (None, 0, "https://f")  # fmt: skip

    def test_location_joins_only_the_present_parts_in_address_order_dropping_empties(self):
        assert (
            value(
                {
                    "__typename": "LocationFieldResponseValue",
                    "locality": "Springfield",
                    "country": "US",
                }
            )["display_value"]
            == "Springfield, US"
        )
        assert value({"__typename": "LocationFieldResponseValue", "streetAddress": "1 Main", "locality": "", "region": "IL", "postalCode": None, "country": "US"})["display_value"] == "1 Main, IL, US"  # fmt: skip

    def test_duration_volume_weight_drop_the_unit_from_display_value_when_it_is_null(self):
        v = value(
            {"__typename": "DurationFieldResponseValue", "duration": {"amount": 5, "unit": None}}
        )
        assert (v["amount"], v["unit"], v["display_value"]) == (5, None, "5")
        assert (
            value(
                {
                    "__typename": "VolumeFieldResponseValue",
                    "volume": {"amount": "2.5", "unit": None},
                }
            )["display_value"]
            == "2.5"
        )
        assert value({"__typename": "WeightFieldResponseValue", "weight": {"amount": "3.0", "unit": None}})["display_value"] == "3.0"  # fmt: skip

    def test_preserves_unknown_enum_values_and_lowercases_them_in_display_value_non_coercion(self):
        assert value(
            {
                "__typename": "BarcodeFieldResponseValue",
                "barcodeType": "FUTURE_CODE",
                "barcodeValue": "z9",
            }
        ) == {
            "kind": "barcode",
            "barcode_type": "FUTURE_CODE",
            "barcode_value": "z9",
            "display_value": "z9",
        }
        v = value(
            {
                "__typename": "DurationFieldResponseValue",
                "duration": {"amount": 2, "unit": "FORTNIGHTS"},
            }
        )
        assert (v["unit"], v["display_value"]) == ("FORTNIGHTS", "2 fortnights")
        v = value(
            {"__typename": "WeightFieldResponseValue", "weight": {"amount": "1", "unit": "GRAM"}}
        )
        assert (v["unit"], v["display_value"]) == ("GRAM", "1 gram")  # fmt: skip

    def test_renders_meta_of_any_json_shape_and_empty_string_for_explicit_null(self):
        assert value({"__typename": "MetaFieldResponseValue", "meta": {"a": 1, "b": [2, 3]}}) == {
            "kind": "meta",
            "meta": {"a": 1, "b": [2, 3]},
            "display_value": '{"a":1,"b":[2,3]}',
        }
        assert (
            value({"__typename": "MetaFieldResponseValue", "meta": [1, 2]})["display_value"]
            == "[1,2]"
        )
        assert (
            value({"__typename": "MetaFieldResponseValue", "meta": "hello"})["display_value"]
            == '"hello"'
        )
        v = value({"__typename": "MetaFieldResponseValue", "meta": 0})
        assert (v["meta"], v["display_value"]) == (0, "0")
        v = value({"__typename": "MetaFieldResponseValue", "meta": False})
        assert (v["meta"], v["display_value"]) == (False, "false")
        assert value({"__typename": "MetaFieldResponseValue", "meta": None}) == {"kind": "meta", "meta": None, "display_value": ""}  # fmt: skip

    def test_renders_zero_ish_decimal_percent_integer_age_values_rather_than_treating_them_as_absent(
        self,
    ):
        v = value({"__typename": "DecimalFieldResponseValue", "decimal": "0"})
        assert (v["decimal"], v["display_value"]) == ("0", "0")
        v = value({"__typename": "PercentFieldResponseValue", "percent": "0"})
        assert (v["percent"], v["display_value"]) == ("0", "0%")
        assert (
            value({"__typename": "IntegerFieldResponseValue", "integer": 0})["display_value"] == "0"
        )
        assert value({"__typename": "AgeFieldResponseValue", "age": 0})["display_value"] == "0"

    def test_keeps_the_waiver_signed_false_null_distinction_on_the_guest_variant(self):
        v = value({"__typename": "GuestFieldResponseValue", "name": "Ada", "waiverSigned": False})
        assert (v["waiver_signed"], v["display_value"]) == (False, "Ada")
        assert (
            value({"__typename": "GuestFieldResponseValue", "name": "Ada"})["waiver_signed"] is None
        )

    def test_does_not_double_escape_ampersands_already_part_of_an_escape_sequence(self):
        assert (
            value({"__typename": "HtmlFieldResponseValue", "html": "a & <b> &amp; c"})[
                "display_value"
            ]
            == "a &amp; &lt;b&gt; &amp;amp; c"
        )


def meta(id: str, name: str, slug: str) -> MetaData:
    return MetaData(
        id=id,
        name=name,
        slug=slug,
        type="t",
        prompt=None,
        prompt_hint=None,
        is_required=False,
        refid=f"r{id}",
        display_value="",
        value=None,
    )


class TestFilterMetaDataByIntegrator:
    entries = [
        meta("1", "a", "integrators:bob:booking_url"),
        meta("2", "b", "integrators:BOB:booking_url"),
        meta("3", "c", "integrators:joe:other"),
        meta("4", "d", "plain_field"),
    ]

    def test_keeps_only_exact_prefix_matches_case_sensitive_and_strips_the_prefix(self):
        result = filter_meta_data_by_integrator(self.entries, "bob")
        assert len(result) == 1
        assert result[0].id == "1"
        assert result[0].slug == "booking_url"

    def test_returns_nothing_when_no_slug_matches_the_integrator(self):
        assert filter_meta_data_by_integrator(self.entries, "nope") == []

    def test_returns_an_empty_list_for_empty_input(self):
        assert filter_meta_data_by_integrator([], "bob") == []

    def test_preserves_every_non_slug_field_and_the_value_on_matched_entries(self):
        entry = MetaData(
            id="x",
            name="Booking URL",
            slug="integrators:bob:booking_url",
            type="URL",
            prompt="P",
            prompt_hint="H",
            is_required=True,
            refid="r",
            display_value="https://x",
            value=MetaDataUrlValue(url="https://x"),
        )
        assert filter_meta_data_by_integrator([entry], "bob") == [
            replace(entry, slug="booking_url")
        ]

    def test_keeps_all_of_multiple_matches_for_the_same_integrator(self):
        many = [
            replace(self.entries[0], id="a", slug="integrators:bob:one"),
            replace(self.entries[0], id="b", slug="integrators:bob:two"),
        ]
        assert [e.slug for e in filter_meta_data_by_integrator(many, "bob")] == ["one", "two"]

    def test_matches_only_a_leading_prefix_not_one_appearing_mid_slug(self):
        mid = [replace(self.entries[0], slug="x:integrators:bob:y")]
        assert filter_meta_data_by_integrator(mid, "bob") == []

    def test_strips_to_an_empty_slug_when_the_slug_is_exactly_the_prefix(self):
        exact = [replace(self.entries[0], slug="integrators:bob:")]
        assert filter_meta_data_by_integrator(exact, "bob")[0].slug == ""

    def test_does_not_match_when_the_integrator_is_a_prefix_of_another_integrators_name(self):
        bobby = [replace(self.entries[0], slug="integrators:bobby:url")]
        assert filter_meta_data_by_integrator(bobby, "bob") == []

    def test_meta_value_round_trips_as_a_meta_dataclass(self):
        assert MetaDataMetaValue(meta={"a": 1}).kind == "meta"


class TestToSetMetaDataResult:
    def test_maps_the_success_variant_to_success_true_with_the_echoed_id_and_message(self):
        assert to_set_meta_data_result(
            {
                "__typename": "UpsertBookingFieldResponsesSuccess",
                "bookingId": "b_1",
                "message": "ok",
            },
            "b_fallback",
        ) == SetMetaDataResult(success=True, booking_id="b_1", message="ok")

    def test_maps_booking_not_found_error_to_success_false_keeping_the_id_and_message(self):
        assert to_set_meta_data_result(
            {"__typename": "BookingNotFoundError", "bookingId": "b_x", "message": "not found"},
            "b_fallback",
        ) == SetMetaDataResult(success=False, booking_id="b_x", message="not found")

    def test_maps_generic_error_to_success_false_falling_back_to_the_requested_id(self):
        assert to_set_meta_data_result(
            {"__typename": "GenericError", "message": "boom"}, "b_fallback"
        ) == SetMetaDataResult(success=False, booking_id="b_fallback", message="boom")

    def test_defaults_success_false_message_empty_for_an_absent_or_unknown_result(self):
        assert to_set_meta_data_result(None, "b_fallback") == SetMetaDataResult(
            success=False, booking_id="b_fallback", message=""
        )
        assert to_set_meta_data_result(
            {"__typename": "SomethingNew"}, "b_fallback"
        ) == SetMetaDataResult(success=False, booking_id="b_fallback", message="")
