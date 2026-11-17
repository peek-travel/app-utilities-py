from peek_app_utilities.internal.peek.daily_notes.daily_note_converter import (
    from_upsert_response,
    to_daily_note,
)
from peek_app_utilities.models.peek.daily_note import DailyNote

# ─── to_daily_note ────────────────────────────────────────────────────────────


def test_to_daily_note_returns_the_note_on_the_success_branch():
    assert to_daily_note({"dailyNote": {"dailyNote": {"note": "Hi"}}}) == DailyNote(note="Hi")


def test_to_daily_note_returns_none_on_the_not_found_branch():
    assert to_daily_note({"dailyNote": {"message": "not found"}}) is None


def test_to_daily_note_returns_none_when_the_success_branch_has_a_null_note():
    assert to_daily_note({"dailyNote": {"dailyNote": None}}) is None


def test_to_daily_note_returns_none_when_the_note_is_not_a_string():
    assert to_daily_note({"dailyNote": {"dailyNote": {"note": 123}}}) is None


def test_to_daily_note_returns_none_for_none_data():
    assert to_daily_note(None) is None
    assert to_daily_note({}) is None


# ─── from_upsert_response ─────────────────────────────────────────────────────


def test_from_upsert_response_returns_the_saved_note():
    response = {"upsertDailyNote": {"dailyNote": {"note": "Saved"}}}
    assert from_upsert_response(response) == DailyNote(note="Saved")


def test_from_upsert_response_returns_none_when_the_saved_note_is_missing():
    assert from_upsert_response(None) is None
    assert from_upsert_response({"upsertDailyNote": {"dailyNote": None}}) is None
