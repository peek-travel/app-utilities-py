"""Pure functions that map raw Peek question configuration nodes into the clean
:class:`CustomQuestion` model. No I/O — straightforward, testable transforms.
"""

from __future__ import annotations

from collections.abc import Iterable

from peek_app_utilities.internal.peek.products.custom_question_queries import (
    QuestionConfigurationNode,
    RawQuestionNode,
    RawQuestionOptionNode,
)
from peek_app_utilities.models.peek.custom_question import (
    CustomQuestion,
    CustomQuestionOption,
)


def from_question_configurations(
    configs: Iterable[QuestionConfigurationNode],
) -> list[CustomQuestion]:
    """Converts an activity's question configurations into :class:`CustomQuestion` s."""
    return [_from_question_configuration(config) for config in configs]


def _from_question_configuration(config: QuestionConfigurationNode) -> CustomQuestion:
    """Converts a single question configuration node into a :class:`CustomQuestion`."""
    question: RawQuestionNode = config.get("question") or {}
    order = config.get("order")
    return CustomQuestion(
        id=question.get("id") or "",
        order=0 if order is None else order,
        is_required=bool(config.get("isRequired")),
        question_text=question.get("text") or "",
        hint_text=question.get("hint"),
        question_type=question.get("questionType") or "",
        internal_label=question.get("internalLabel"),
        per_guest=bool(question.get("perGuest")),
        default_value=question.get("answerDefaultValue"),
        options=[_from_question_option(option) for option in question.get("options") or []],
    )


def _from_question_option(option: RawQuestionOptionNode) -> CustomQuestionOption:
    """Converts a raw choice-question option node into a :class:`CustomQuestionOption`."""
    return CustomQuestionOption(
        id=option.get("id") or "",
        order=option.get("order") or 0,
        value=option.get("text") or "",
    )
