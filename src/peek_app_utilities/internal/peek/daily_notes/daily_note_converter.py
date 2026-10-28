"""Pure functions resolving the daily-note unions into the clean
:class:`DailyNote` model. A not-found / missing note maps to ``None``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from peek_app_utilities.internal.peek.daily_notes.daily_note_queries import DAILY_NOTE_KEY
from peek_app_utilities.models.peek.daily_note import DailyNote


def to_daily_note(response: Mapping[str, Any] | None) -> DailyNote | None:
    """Resolves a daily-note query response into a :class:`DailyNote`, or ``None``."""
    union = (response or {}).get(DAILY_NOTE_KEY)
    if not union:
        return None
    # Success branch carries a nested `dailyNote`; the not-found branch carries `message`.
    if DAILY_NOTE_KEY in union:
        return _clean_note(union.get(DAILY_NOTE_KEY))
    return None


def from_upsert_response(response: Mapping[str, Any] | None) -> DailyNote | None:
    """Resolves an upsert response into the saved :class:`DailyNote`, or ``None``."""
    result = (response or {}).get("upsertDailyNote") or {}
    return _clean_note(result.get(DAILY_NOTE_KEY))


def _clean_note(note: Mapping[str, Any] | None) -> DailyNote | None:
    if not note:
        return None
    text = note.get("note")
    if not isinstance(text, str):
        return None
    return DailyNote(note=text)
