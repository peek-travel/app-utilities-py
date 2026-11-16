"""Pure functions that map raw Peek question nodes — whether wrapped in an
activity's question configuration or returned bare from the account-wide
catalog — into the clean :class:`CustomQuestion` model. No I/O.
"""

from __future__ import annotations

from collections.abc import Iterable

from peek_app_utilities.internal.peek.custom_questions.custom_question_queries import (
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
    return [
        _from_question_node(
            config.get("question") or {}, config.get("order"), config.get("isRequired")
        )
        for config in configs
    ]


def from_question_nodes(questions: Iterable[RawQuestionNode]) -> list[CustomQuestion]:
    """Converts bare question nodes (the account-wide catalog, which carries no
    per-activity configuration) into :class:`CustomQuestion` s. ``order`` and
    ``is_required`` have no meaning outside an activity's question list, so they
    default to ``0``/``False``."""
    return [_from_question_node(question) for question in questions]


def _from_question_node(
    question: RawQuestionNode, order: int | None = None, is_required: bool | None = None
) -> CustomQuestion:
    """Converts a single raw question node into a :class:`CustomQuestion`, folding
    in the per-activity ``order``/``is_required`` config when present."""
    return CustomQuestion(
        id=question.get("id") or "",
        order=0 if order is None else order,
        is_required=bool(is_required),
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
