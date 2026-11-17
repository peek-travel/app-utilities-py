from typing import Any

import pytest

from peek_app_utilities.internal.peek.bookings.custom_question_answer import (
    ResolveCustomQuestionOptions,
    ResolvedCustomAnswer,
    is_custom_question_id,
    resolve_custom_question_answers,
    resolved_answer_to_wire,
)
from peek_app_utilities.models.peek.booking import CustomQuestionAnswerInput
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption


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


def a(question_id_or_text: str, value: str) -> CustomQuestionAnswerInput:
    return CustomQuestionAnswerInput(question_id_or_text=question_id_or_text, value=value)


CHECK = q(id="cq_check", question_text="Adult Only?", question_type="CHECK_BOX")
TEXT = q(id="cq_text", question_text="Dietary Notes", question_type="TEXT")
PICK_OPTIONS = [
    CustomQuestionOption(id="cqao_a", order=1, value="Loyola University"),
    CustomQuestionOption(id="cqao_b", order=2, value="Hilton Chicago"),
]
PICK = q(
    id="cq_pick", question_text="Pickup Spot", question_type="SELECT_ONE", options=PICK_OPTIONS
)
LOC = q(id="cq_loc", question_text="Pickup Spot", question_type="LOCATION", options=PICK_OPTIONS)

ALL = [CHECK, TEXT, PICK, LOC]
REQUIRE = ResolveCustomQuestionOptions(require_required=True)
ACCEPT_ALL = ResolveCustomQuestionOptions(accept_all_ids=True)


class TestQuestionMatching:
    def test_matches_by_id(self):
        assert resolve_custom_question_answers([a("cq_text", "vegan")], ALL) == [
            ResolvedCustomAnswer(question_id="cq_text", question_answer_text="vegan")
        ]

    def test_matches_by_lenient_text_case_punctuation_insensitive(self):
        assert resolve_custom_question_answers([a("  dietary NOTES!! ", "vegan")], ALL) == [
            ResolvedCustomAnswer(question_id="cq_text", question_answer_text="vegan")
        ]

    def test_raises_on_an_unknown_id(self):
        with pytest.raises(ValueError, match='No custom question matches id "cq_nope"'):
            resolve_custom_question_answers([a("cq_nope", "x")], ALL)

    def test_raises_on_unmatched_text(self):
        with pytest.raises(ValueError, match="No custom question matches text"):
            resolve_custom_question_answers([a("totally unknown", "x")], ALL)

    def test_raises_on_ambiguous_text_two_questions_normalize_the_same(self):
        dupes = [q(id="cq_1", question_text="Pick Up"), q(id="cq_2", question_text="pickup")]
        with pytest.raises(ValueError, match="matches more than one question"):
            resolve_custom_question_answers([a("pickup", "x")], dupes)


class TestCheckbox:
    @pytest.mark.parametrize(
        ("value", "is_checked", "text"),
        [
            ("yes", True, "Yes"),
            ("true", True, "Yes"),
            ("YES", True, "Yes"),
            ("no", False, "No"),
            ("false", False, "No"),
            ("  False  ", False, "No"),
        ],
    )
    def test_maps_value_to_is_checked_with_text(self, value: str, is_checked: bool, text: str):
        assert resolve_custom_question_answers([a("cq_check", value)], ALL) == [
            ResolvedCustomAnswer(
                question_id="cq_check", is_checked=is_checked, question_answer_text=text
            )
        ]

    def test_raises_on_an_invalid_checkbox_value(self):
        with pytest.raises(ValueError, match="must be yes/no/true/false"):
            resolve_custom_question_answers([a("cq_check", "maybe")], ALL)


class TestText:
    def test_passes_the_value_through_verbatim(self):
        assert resolve_custom_question_answers([a("cq_text", "  Keep As-Is  ")], ALL) == [
            ResolvedCustomAnswer(question_id="cq_text", question_answer_text="  Keep As-Is  ")
        ]


class TestSelectOneLocationOptions:
    def test_matches_an_option_by_id_and_sets_text_to_the_exact_label(self):
        assert resolve_custom_question_answers([a("cq_pick", "cqao_b")], ALL) == [
            ResolvedCustomAnswer(
                question_id="cq_pick",
                question_answer_option_id="cqao_b",
                question_answer_text="Hilton Chicago",
            )
        ]

    def test_matches_an_option_by_lenient_label_but_stores_the_exact_label(self):
        assert resolve_custom_question_answers([a("cq_loc", "hilton chicago")], ALL) == [
            ResolvedCustomAnswer(
                question_id="cq_loc",
                question_answer_option_id="cqao_b",
                question_answer_text="Hilton Chicago",
            )
        ]

    def test_raises_on_an_unknown_option_id(self):
        with pytest.raises(ValueError, match='No option matches id "cqao_zzz"'):
            resolve_custom_question_answers([a("cq_pick", "cqao_zzz")], ALL)

    def test_raises_on_an_unmatched_option_label(self):
        with pytest.raises(ValueError, match='No option matches "nowhere"'):
            resolve_custom_question_answers([a("cq_pick", "nowhere")], ALL)

    def test_raises_on_an_ambiguous_option_label(self):
        dupe = q(
            id="cq_dup",
            question_type="SELECT_ONE",
            question_text="Dup",
            options=[
                CustomQuestionOption(id="cqao_1", order=1, value="Main St"),
                CustomQuestionOption(id="cqao_2", order=2, value="main st."),
            ],
        )
        with pytest.raises(ValueError, match="matches more than one option"):
            resolve_custom_question_answers([a("cq_dup", "main st")], [dupe])


class TestMisc:
    def test_resolves_multiple_answers_in_order(self):
        resolved = resolve_custom_question_answers(
            [a("cq_check", "no"), a("cq_pick", "cqao_a")], ALL
        )
        assert resolved == [
            ResolvedCustomAnswer(
                question_id="cq_check", is_checked=False, question_answer_text="No"
            ),
            ResolvedCustomAnswer(
                question_id="cq_pick",
                question_answer_option_id="cqao_a",
                question_answer_text="Loyola University",
            ),
        ]

    def test_returns_empty_for_no_answers(self):
        assert resolve_custom_question_answers([], ALL) == []

    def test_raises_on_an_unsupported_question_type(self):
        weird = q(id="cq_weird", question_type="SIGNATURE")
        with pytest.raises(ValueError, match='unsupported type "SIGNATURE"'):
            resolve_custom_question_answers([a("cq_weird", "x")], [weird])

    def test_raises_on_a_per_guest_question_not_yet_supported(self):
        per_guest = q(id="cq_pg", question_type="TEXT", per_guest=True)
        with pytest.raises(
            ValueError, match='Per-guest custom question "cq_pg" is not yet supported'
        ):
            resolve_custom_question_answers([a("cq_pg", "x")], [per_guest])

    def test_wire_payload_includes_only_the_type_specific_fields_that_are_set(self):
        assert resolved_answer_to_wire(
            ResolvedCustomAnswer(question_id="cq_text", question_answer_text="vegan")
        ) == {"questionId": "cq_text", "questionAnswerText": "vegan"}
        assert resolved_answer_to_wire(
            ResolvedCustomAnswer(
                question_id="cq_check", is_checked=False, question_answer_text="No"
            )
        ) == {"questionId": "cq_check", "questionAnswerText": "No", "isChecked": False}
        assert resolved_answer_to_wire(
            ResolvedCustomAnswer(
                question_id="cq_pick", question_answer_option_id="cqao_a", question_answer_text="L"
            )
        ) == {
            "questionId": "cq_pick",
            "questionAnswerText": "L",
            "questionAnswerOptionId": "cqao_a",
        }


class TestRequireRequired:
    REQ_TEXT = q(id="cq_req", question_text="Dietary Notes", question_type="TEXT", is_required=True)

    def test_raises_when_a_required_question_is_unanswered_empty_answers(self):
        with pytest.raises(
            ValueError,
            match=r'Custom question "Dietary Notes" \(cq_req\) is required but was not answered',
        ):
            resolve_custom_question_answers([], [self.REQ_TEXT], REQUIRE)

    def test_raises_when_a_required_question_is_unanswered_among_other_answers(self):
        with pytest.raises(ValueError, match=r"\(cq_req\) is required but was not answered"):
            resolve_custom_question_answers([a("cq_check", "yes")], [CHECK, self.REQ_TEXT], REQUIRE)

    def test_passes_when_every_required_question_is_answered(self):
        assert resolve_custom_question_answers(
            [a("cq_req", "vegan")], [self.REQ_TEXT], REQUIRE
        ) == [ResolvedCustomAnswer(question_id="cq_req", question_answer_text="vegan")]

    def test_counts_a_required_checkbox_answered_no_as_answered(self):
        req_check = q(id="cq_rc", question_type="CHECK_BOX", is_required=True)
        assert resolve_custom_question_answers([a("cq_rc", "no")], [req_check], REQUIRE) == [
            ResolvedCustomAnswer(question_id="cq_rc", is_checked=False, question_answer_text="No")
        ]

    def test_ignores_required_per_guest_questions(self):
        req_per_guest = q(id="cq_rpg", question_type="TEXT", is_required=True, per_guest=True)
        assert resolve_custom_question_answers([], [req_per_guest], REQUIRE) == []

    def test_does_not_enforce_coverage_when_require_required_is_off(self):
        assert resolve_custom_question_answers([], [self.REQ_TEXT]) == []


class TestAcceptAllIds:
    def test_accepts_an_unknown_cq_id_as_a_text_answer_instead_of_raising(self):
        assert resolve_custom_question_answers([a("cq_unknown", "anything")], ALL, ACCEPT_ALL) == [
            ResolvedCustomAnswer(question_id="cq_unknown", question_answer_text="anything")
        ]

    def test_accepts_an_unknown_id_even_with_an_empty_question_list(self):
        assert resolve_custom_question_answers([a("cq_x", "v")], [], ACCEPT_ALL) == [
            ResolvedCustomAnswer(question_id="cq_x", question_answer_text="v")
        ]

    def test_still_type_resolves_a_known_id_when_accept_all_ids_is_set(self):
        assert resolve_custom_question_answers([a("cq_pick", "cqao_b")], ALL, ACCEPT_ALL) == [
            ResolvedCustomAnswer(
                question_id="cq_pick",
                question_answer_option_id="cqao_b",
                question_answer_text="Hilton Chicago",
            )
        ]

    def test_does_not_relax_an_unmatched_by_name_answer_no_id_to_accept(self):
        with pytest.raises(ValueError, match="No custom question matches text"):
            resolve_custom_question_answers([a("totally unknown", "x")], ALL, ACCEPT_ALL)

    def test_still_raises_on_an_unknown_id_when_accept_all_ids_is_off(self):
        with pytest.raises(ValueError, match='No custom question matches id "cq_unknown"'):
            resolve_custom_question_answers([a("cq_unknown", "x")], ALL)


class TestIsCustomQuestionId:
    @pytest.mark.parametrize("value", ["cq_abc123", "cq_x"])
    def test_is_true_for_a_cq_id(self, value: str):
        assert is_custom_question_id(value) is True

    @pytest.mark.parametrize("value", ["Dietary Notes", "cqao_a", "CQ_ABC", "cq_", "random"])
    def test_is_false_for_free_text_non_question_ids(self, value: str):
        assert is_custom_question_id(value) is False
