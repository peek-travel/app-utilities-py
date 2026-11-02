"""Raw Peek GraphQL query/mutation and response shapes for the daily note.
Internal.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

GLOBAL_NOTE_TYPE: Final = "DASHBOARD"
"""The global-note type for the dashboard daily note."""

DAILY_NOTE_TODAY_QUERY: Final = """
  query dailyNote($type: GlobalNoteType!) {
    dailyNote(type: $type) {
      ... on DailyNoteSuccess {
        dailyNote {
          note
        }
      }
      ... on NotFoundError {
        message
      }
    }
  }
"""
"""Fetches today's daily note."""

UPSERT_DAILY_NOTE_MUTATION: Final = """
  mutation Account($input: UpsertDailyNoteInput!) {
    upsertDailyNote(input: $input) {
      ... on UpsertDailyNoteSuccess {
        dailyNote {
          note
        }
      }
    }
  }
"""
"""Upserts the daily note."""

DAILY_NOTE_KEY: Final = "dailyNote"
"""Wire key of the nested note on the success branch (and of the query root)."""


class DailyNoteNode(TypedDict, total=False):
    note: str | None


class DailyNoteUnion(TypedDict, total=False):
    """The success/not-found union: the success branch carries a nested
    ``dailyNote``; the not-found branch carries ``message``."""

    dailyNote: DailyNoteNode | None
    message: str


class DailyNoteResponse(TypedDict, total=False):
    """``data`` payload of :data:`DAILY_NOTE_TODAY_QUERY` (a success/not-found union)."""

    dailyNote: DailyNoteUnion | None


class UpsertDailyNoteResult(TypedDict, total=False):
    dailyNote: DailyNoteNode | None


class UpsertDailyNoteResponse(TypedDict, total=False):
    """``data`` payload of :data:`UPSERT_DAILY_NOTE_MUTATION`."""

    upsertDailyNote: UpsertDailyNoteResult | None


def build_upsert_daily_note_variables(note: str) -> dict[str, Any]:
    """Builds the variables for :data:`UPSERT_DAILY_NOTE_MUTATION`."""
    return {"input": {"type": GLOBAL_NOTE_TYPE, "note": note}}
