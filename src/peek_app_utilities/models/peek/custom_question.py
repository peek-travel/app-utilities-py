"""The clean, transport-agnostic data model for an activity's custom questions.

Custom questions are the operator-configured questions attached to a bookable
activity (per-guest waiver-style prompts, free-text inputs, multiple-choice
pickers, etc.). This is the shape consumers work with — it is decoupled from
the underlying Peek ``Question``/``ChoiceQuestion`` schema, which stays internal.

Note: this describes the **question definitions** on an activity, not any
customer's answers — so there is no PII here and nothing gated behind
``full_customer_access``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomQuestionOption:
    """A single selectable option on a choice-style :class:`CustomQuestion`."""

    id: str
    """Unique identifier of the option (e.g. ``"cqao_mwdgvw"``)."""
    order: int
    """1-based position of the option within the question's option list."""
    value: str
    """The option's display label (Peek's ``text``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomQuestion:
    """A single custom question configured on an activity.

    The ordering and requiredness come from the activity's question
    configuration; the remaining fields describe the reusable question itself.
    """

    id: str
    """Unique identifier of the question (e.g. ``"cq_anq67"``)."""
    order: int
    """1-based position of the question within the activity's question list."""
    is_required: bool
    """Whether the activity requires an answer to this question."""
    question_text: str
    """The question prompt shown to the guest (Peek's ``text``)."""
    hint_text: str | None
    """Helper/hint text shown alongside the prompt, or ``None`` when none."""
    question_type: str
    """The question's input type as reported by Peek — e.g. ``"CHECK_BOX"``,
    ``"TEXT"``, ``"LOCATION"``, ``"SELECT_ONE"``. Left as a string so new Peek
    question types flow through without a package change."""
    internal_label: str | None
    """Operator-only label for the question, or ``None`` when none."""
    per_guest: bool
    """``True`` when the question is answered once per guest rather than per booking."""
    default_value: str | None
    """Pre-filled default answer, or ``None`` when none."""
    options: list[CustomQuestionOption]
    """Selectable options for choice-style questions (``SELECT_ONE``, ``LOCATION``,
    …). Empty for free-text/checkbox questions that carry no options."""
