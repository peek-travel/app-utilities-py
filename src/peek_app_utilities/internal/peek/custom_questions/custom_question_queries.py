"""Raw Peek GraphQL query and response shapes for custom questions — both the
per-activity configuration read and the account-wide question catalog. These are
an internal implementation detail of the package and are deliberately not
re-exported from the public entry point.
"""

from __future__ import annotations

from typing import Final, TypedDict

ALL_CUSTOM_QUESTIONS_QUERY: Final = """
  query Sales {
    questions {
      id
      questionType
      text
      answerDefaultValue
      hint
      internalLabel
      perGuest
      ... on ChoiceQuestion {
        options {
          id
          text
          order
        }
      }
    }
  }
"""
"""Fetches every custom question defined on the account, regardless of activity."""

CUSTOM_QUESTIONS_QUERY: Final = """
  query Sales($id: ID!) {
    activity(id: $id) {
      id
      name
      questionActivityConfigurations {
        isRequired
        order
        question {
          id
          questionType
          text
          answerDefaultValue
          hint
          internalLabel
          perGuest
          ... on ChoiceQuestion {
            options {
              id
              text
              order
            }
          }
        }
      }
    }
  }
"""
"""Fetches every custom question configured on a single activity."""


class RawQuestionOptionNode(TypedDict, total=False):
    """A single selectable option on a raw ``ChoiceQuestion`` node."""

    id: str
    text: str
    order: int


class RawQuestionNode(TypedDict, total=False):
    """A raw question node as returned inside a question configuration."""

    id: str
    questionType: str
    text: str
    answerDefaultValue: str | None
    hint: str | None
    internalLabel: str | None
    perGuest: bool | None
    options: list[RawQuestionOptionNode] | None
    """Present only on ``ChoiceQuestion`` nodes (via the inline fragment)."""


class QuestionConfigurationNode(TypedDict, total=False):
    """A single ``questionActivityConfigurations`` entry pairing config + question."""

    isRequired: bool | None
    order: int | None
    question: RawQuestionNode


class CustomQuestionsActivityNode(TypedDict, total=False):
    id: str
    name: str
    questionActivityConfigurations: list[QuestionConfigurationNode] | None


class CustomQuestionsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`CUSTOM_QUESTIONS_QUERY`."""

    activity: CustomQuestionsActivityNode | None


class AllCustomQuestionsResponse(TypedDict, total=False):
    """The ``data`` payload of :data:`ALL_CUSTOM_QUESTIONS_QUERY`."""

    questions: list[RawQuestionNode] | None
