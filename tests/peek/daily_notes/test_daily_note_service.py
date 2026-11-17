from peek_app_utilities.internal.peek.daily_notes.daily_note_service import DailyNoteService
from peek_app_utilities.models.peek.daily_note import DailyNote

# ─── get_today ────────────────────────────────────────────────────────────────


async def test_get_today_queries_the_dashboard_note_and_returns_it(gql):
    gql.queue({"dailyNote": {"dailyNote": {"note": "Hello"}}})

    note = await DailyNoteService(gql).get_today()

    assert note == DailyNote(note="Hello")
    assert gql.calls[0].endpoint_name == "sales"
    assert gql.calls[0].variables["type"] == "DASHBOARD"
    assert "query dailyNote($type: GlobalNoteType!)" in gql.calls[0].query


async def test_get_today_returns_none_when_not_found(gql):
    gql.queue({"dailyNote": {"message": "none"}})
    assert await DailyNoteService(gql).get_today() is None


# ─── update ───────────────────────────────────────────────────────────────────


async def test_update_upserts_the_note_and_returns_the_saved_value(gql):
    gql.queue({"upsertDailyNote": {"dailyNote": {"note": "Updated"}}})

    note = await DailyNoteService(gql).update("Updated")

    assert note == DailyNote(note="Updated")
    assert gql.calls[0].variables["input"] == {"type": "DASHBOARD", "note": "Updated"}
    assert "mutation Account($input: UpsertDailyNoteInput!)" in gql.calls[0].query


async def test_update_returns_none_when_the_upsert_response_carries_no_note(gql):
    gql.queue_body({})
    assert await DailyNoteService(gql).update("x") is None
