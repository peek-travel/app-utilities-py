"""Pure resolution of caller-supplied custom-question answers against an
activity's actual custom questions. No I/O — the questions are fetched by the
service and passed in, so this whole module is unit-testable without a client
(and, deliberately, without minting the answer ``refid`` s, which the service
adds afterward).

Each :class:`CustomQuestionAnswerInput` is matched to exactly one question and
its ``value`` validated/resolved by question type into the shape the quote
mutation expects. Any ambiguity or mismatch raises ``ValueError`` before the
booking is made.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from peek_app_utilities.models.peek.booking import CustomQuestionAnswerInput
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption

# Peek question-type values this resolver knows how to answer.
QUESTION_TYPE_CHECK_BOX: Final = "CHECK_BOX"
QUESTION_TYPE_TEXT: Final = "TEXT"
QUESTION_TYPE_SELECT_ONE: Final = "SELECT_ONE"
QUESTION_TYPE_LOCATION: Final = "LOCATION"

# A `cq_…` question id vs. free-text; a `cqao_…` option id vs. an option label.
_QUESTION_ID_RE: Final = re.compile(r"cq_[a-z0-9]+")
_OPTION_ID_RE: Final = re.compile(r"cqao_[a-z0-9]+")
_NON_ALNUM_RE: Final = re.compile(r"[^a-z0-9]")

# Checkbox truthiness — `value` (lowercased) must be one of the valid set.
_CHECKBOX_TRUE: Final = frozenset({"yes", "true"})
_CHECKBOX_VALID: Final = frozenset({"yes", "no", "true", "false"})

# Display text the API expects in `questionAnswerText` for a checkbox.
_CHECKBOX_TEXT_TRUE: Final = "Yes"
_CHECKBOX_TEXT_FALSE: Final = "No"

# Wire keys of a resolved answer on the quote payload.
_WIRE_QUESTION_ID: Final = "questionId"
_WIRE_ANSWER_TEXT: Final = "questionAnswerText"
_WIRE_ANSWER_OPTION_ID: Final = "questionAnswerOptionId"
_WIRE_IS_CHECKED: Final = "isChecked"


# ─── Error messages ──────────────────────────────────────────────────────────
def _err_unknown_question_id(v: str) -> str:
    return f'No custom question matches id "{v}" for this activity'


def _err_no_text_match(v: str) -> str:
    return f'No custom question matches text "{v}" for this activity'


def _err_ambiguous_text(v: str) -> str:
    return f'Custom question text "{v}" matches more than one question'


def _err_per_guest_unsupported(question_id: str) -> str:
    return f'Per-guest custom question "{question_id}" is not yet supported'


def _err_unsupported_type(question_type: str, question_id: str) -> str:
    return f'Custom question "{question_id}" has unsupported type "{question_type}"'


def _err_invalid_checkbox(v: str, question_id: str) -> str:
    return f'Checkbox answer for question "{question_id}" must be yes/no/true/false, got "{v}"'


def _err_unknown_option_id(v: str, question_id: str) -> str:
    return f'No option matches id "{v}" for question "{question_id}"'


def _err_no_option_match(v: str, question_id: str) -> str:
    return f'No option matches "{v}" for question "{question_id}"'


def _err_ambiguous_option(v: str, question_id: str) -> str:
    return f'Option "{v}" matches more than one option for question "{question_id}"'


def _err_missing_required(text: str, question_id: str) -> str:
    return f'Custom question "{text}" ({question_id}) is required but was not answered'


def is_custom_question_id(id_or_text: str) -> bool:
    """Whether ``id_or_text`` is a custom-question id (``cq_…``) rather than
    free-text. The service uses this to decide whether it must fetch the
    activity's questions: a by-name answer always needs the list to resolve, a
    by-id answer does not when unknown ids are being accepted (see
    :attr:`ResolveCustomQuestionOptions.accept_all_ids`)."""
    return _QUESTION_ID_RE.fullmatch(id_or_text) is not None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedCustomAnswer:
    """A resolved answer, minus the ``refid`` the service mints.
    :attr:`question_answer_text` is always set (the API requires it): the raw
    value for text, the exact option label for select-one/location, and
    ``"Yes"``/``"No"`` for a checkbox. The type-specific field
    (:attr:`question_answer_option_id` / :attr:`is_checked`) is set in addition,
    per the question's type."""

    question_id: str
    question_answer_text: str
    question_answer_option_id: str | None = None
    is_checked: bool | None = None


def resolved_answer_to_wire(answer: ResolvedCustomAnswer) -> dict[str, Any]:
    """The quote-mutation payload for a resolved answer (type-specific fields
    only when set; the caller adds the ``refid``)."""
    wire: dict[str, Any] = {
        _WIRE_QUESTION_ID: answer.question_id,
        _WIRE_ANSWER_TEXT: answer.question_answer_text,
    }
    if answer.question_answer_option_id is not None:
        wire[_WIRE_ANSWER_OPTION_ID] = answer.question_answer_option_id
    if answer.is_checked is not None:
        wire[_WIRE_IS_CHECKED] = answer.is_checked
    return wire


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolveCustomQuestionOptions:
    """Options controlling how the answer set as a whole is validated."""

    require_required: bool | None = None
    """When ``True``, every question the activity marks ``is_required`` must have
    an answer — resolution raises for the first required question left
    unanswered. Per-guest questions are excluded (they cannot be answered here
    anyway)."""
    accept_all_ids: bool | None = None
    """When ``True``, an answer identified by a ``cq_…`` id that is **not** in the
    activity's question list is accepted as-is (passed through as a text answer)
    instead of raising. By-name answers are unaffected — they still must match a
    question, since there is no id to accept. Default: ``False``."""


def _normalize(value: str) -> str:
    """Lowercases and strips non-alphanumerics for lenient matching."""
    return _NON_ALNUM_RE.sub("", value.lower())


def _resolve_question(
    id_or_text: str, questions: Sequence[CustomQuestion], accept_all_ids: bool
) -> CustomQuestion | None:
    """Finds the one question an input targets, by id or by lenient text match.
    Returns ``None`` (rather than raising) for an unknown ``cq_…`` id when
    ``accept_all_ids`` is set — the caller then accepts the id blindly as a text
    answer. A by-name input is always resolved against the list (there is no id
    to accept), so ``accept_all_ids`` never relaxes an unmatched/ambiguous text
    match."""
    if is_custom_question_id(id_or_text):
        by_id = next((q for q in questions if q.id == id_or_text), None)
        if by_id is None:
            if accept_all_ids:
                return None
            raise ValueError(_err_unknown_question_id(id_or_text))
        return by_id
    target = _normalize(id_or_text)
    matches = [q for q in questions if _normalize(q.question_text) == target]
    if not matches:
        raise ValueError(_err_no_text_match(id_or_text))
    if len(matches) > 1:
        raise ValueError(_err_ambiguous_text(id_or_text))
    return matches[0]


def _resolve_option(value: str, question: CustomQuestion) -> CustomQuestionOption:
    """Finds the one option a value targets, by id or by lenient label match."""
    if _OPTION_ID_RE.fullmatch(value):
        by_id = next((o for o in question.options if o.id == value), None)
        if by_id is None:
            raise ValueError(_err_unknown_option_id(value, question.id))
        return by_id
    target = _normalize(value)
    matches = [o for o in question.options if _normalize(o.value) == target]
    if not matches:
        raise ValueError(_err_no_option_match(value, question.id))
    if len(matches) > 1:
        raise ValueError(_err_ambiguous_option(value, question.id))
    return matches[0]


def _resolve_one(
    answer: CustomQuestionAnswerInput, questions: Sequence[CustomQuestion], accept_all_ids: bool
) -> ResolvedCustomAnswer:
    """Resolves a single answer input against the matched question's type."""
    question = _resolve_question(answer.question_id_or_text, questions, accept_all_ids)
    # An unknown id accepted blindly (accept_all_ids): there is no question
    # definition to type-check against, so pass the id and value through as a
    # plain text answer.
    if question is None:
        return ResolvedCustomAnswer(
            question_id=answer.question_id_or_text, question_answer_text=answer.value
        )
    # Per-guest answers require per-guest wiring the quote payload does not carry
    # yet — reject rather than silently drop the distinction.
    if question.per_guest:
        raise ValueError(_err_per_guest_unsupported(question.id))
    question_type = question.question_type
    if question_type == QUESTION_TYPE_CHECK_BOX:
        normalized = answer.value.strip().lower()
        if normalized not in _CHECKBOX_VALID:
            raise ValueError(_err_invalid_checkbox(answer.value, question.id))
        is_checked = normalized in _CHECKBOX_TRUE
        # The API requires questionAnswerText even for a checkbox.
        return ResolvedCustomAnswer(
            question_id=question.id,
            is_checked=is_checked,
            question_answer_text=_CHECKBOX_TEXT_TRUE if is_checked else _CHECKBOX_TEXT_FALSE,
        )
    if question_type == QUESTION_TYPE_TEXT:
        return ResolvedCustomAnswer(question_id=question.id, question_answer_text=answer.value)
    if question_type in (QUESTION_TYPE_SELECT_ONE, QUESTION_TYPE_LOCATION):
        # Select the option only — Peek applies each location option's configured
        # lat/long. questionAnswerText must be the option's exact current label.
        option = _resolve_option(answer.value, question)
        return ResolvedCustomAnswer(
            question_id=question.id,
            question_answer_option_id=option.id,
            question_answer_text=option.value,
        )
    raise ValueError(_err_unsupported_type(question_type, question.id))


def resolve_custom_question_answers(
    answers: Sequence[CustomQuestionAnswerInput],
    questions: Sequence[CustomQuestion],
    options: ResolveCustomQuestionOptions | None = None,
) -> list[ResolvedCustomAnswer]:
    """Resolves every caller-supplied answer against the activity's custom
    questions, raising ``ValueError`` on the first unmatched question, ambiguous
    match, or invalid value. The returned objects carry no ``refid`` — the service
    adds one per answer.

    With ``require_required``, the resolved set is additionally checked for
    coverage: any required, non-per-guest question with no answer raises. This
    check runs even when ``answers`` is empty, so an activity with unanswered
    required questions fails rather than booking without them.

    With ``accept_all_ids``, an answer whose ``cq_…`` id is not in ``questions``
    is accepted as a plain text answer instead of raising."""
    accept_all_ids = bool(options.accept_all_ids) if options else False
    resolved = [_resolve_one(answer, questions, accept_all_ids) for answer in answers]
    if options and options.require_required:
        _assert_required_answered(resolved, questions)
    return resolved


def _assert_required_answered(
    resolved: Sequence[ResolvedCustomAnswer], questions: Sequence[CustomQuestion]
) -> None:
    """Raises for the first required, non-per-guest question left unanswered."""
    answered = {answer.question_id for answer in resolved}
    for question in questions:
        if question.is_required and not question.per_guest and question.id not in answered:
            raise ValueError(_err_missing_required(question.question_text, question.id))
