import json

from peek_app_utilities.access_options import AccessOptions
from peek_app_utilities.internal.peek.waivers.waiver_webhook import (
    from_waiver_node,
    parse_waiver_webhook,
)
from peek_app_utilities.models.peek.waiver import Waiver

FULL_ACCESS = AccessOptions(full_customer_access=True)


def waiver_node() -> dict:
    return {
        "account_id": "acc_1",
        "agreement_signature_id": "sig_1",
        "agreement_template_id": "tpl_1",
        "booking_id": "b_1",
        "file_url": "https://files/waiver.pdf",
        "signed_at": "2026-06-26T10:00:00Z",
        "signed_by_guardian": True,
        "waiver_data": {
            "participant_name": "Ada",
            "participant_optin_marketing": True,
            "participant_optin_sms": False,
        },
    }


# ─── parse_waiver_webhook ─────────────────────────────────────────────────────


def test_parses_the_waiver_envelope_into_a_waiver():
    waiver = parse_waiver_webhook({"waiver": waiver_node()}, FULL_ACCESS)
    assert waiver == Waiver(
        template_id="tpl_1",
        booking_id="b_1",
        file_url="https://files/waiver.pdf",
        signed_at="2026-06-26T10:00:00Z",
        is_signed_by_guardian=True,
        guest_name="Ada",
        is_optin_marketing=True,
        is_optin_sms=False,
    )


def test_parses_a_bare_waiver_node_no_envelope():
    waiver = parse_waiver_webhook(waiver_node())
    assert waiver.template_id == "tpl_1"
    assert waiver.booking_id == "b_1"


def test_parses_a_json_string_body():
    waiver = parse_waiver_webhook(json.dumps({"waiver": waiver_node()}), FULL_ACCESS)
    assert waiver.file_url == "https://files/waiver.pdf"


def test_redacts_participant_name_and_document_url_by_default_no_pii():
    waiver = parse_waiver_webhook({"waiver": waiver_node()})
    assert waiver.guest_name is None
    assert waiver.file_url == ""
    # Non-PII fields still come through.
    assert waiver.booking_id == "b_1"
    assert waiver.template_id == "tpl_1"
    assert waiver.signed_at == "2026-06-26T10:00:00Z"
    assert waiver.is_signed_by_guardian is True
    assert waiver.is_optin_marketing is True


def test_redacts_when_options_leave_full_customer_access_unset():
    waiver = parse_waiver_webhook({"waiver": waiver_node()}, AccessOptions())
    assert waiver.guest_name is None
    assert waiver.file_url == ""


def test_defaults_guest_fields_when_waiver_data_is_absent():
    node = waiver_node()
    del node["waiver_data"]
    waiver = parse_waiver_webhook({"waiver": node}, FULL_ACCESS)
    assert waiver.guest_name is None
    assert waiver.is_optin_marketing is False
    assert waiver.is_optin_sms is False


def test_coerces_the_guardian_flag_and_empty_strings_for_missing_ids():
    waiver = parse_waiver_webhook({"waiver": {"signed_by_guardian": False}})
    assert waiver.is_signed_by_guardian is False
    assert waiver.template_id == ""
    assert waiver.booking_id == ""
    assert waiver.file_url == ""
    assert waiver.signed_at == ""


def test_returns_an_empty_ish_waiver_for_malformed_input_rather_than_raising():
    assert parse_waiver_webhook(None).template_id == ""
    assert parse_waiver_webhook("not json").template_id == ""
    assert parse_waiver_webhook(42).template_id == ""
    assert parse_waiver_webhook({"waiver": "nope"}).template_id == ""
    assert parse_waiver_webhook("[1, 2]").booking_id == ""


# ─── from_waiver_node ─────────────────────────────────────────────────────────


def test_from_waiver_node_maps_a_raw_node_directly():
    assert from_waiver_node(waiver_node()).guest_name == "Ada"


def test_from_waiver_node_tolerates_none():
    assert from_waiver_node(None).template_id == ""
    assert from_waiver_node({}).is_optin_sms is False


def test_from_waiver_node_maps_an_empty_participant_name_to_none():
    node = waiver_node()
    node["waiver_data"]["participant_name"] = ""
    assert from_waiver_node(node).guest_name is None
