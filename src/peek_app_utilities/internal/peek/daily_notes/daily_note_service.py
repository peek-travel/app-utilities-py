"""Daily-note operations against the Peek backoffice API.

Obtain an instance via ``PeekAccessService.get_daily_note_service()``.
"""

from __future__ import annotations

from peek_app_utilities.internal.peek.daily_notes.daily_note_converter import (
    from_upsert_response,
    to_daily_note,
)
from peek_app_utilities.internal.peek.daily_notes.daily_note_queries import (
    DAILY_NOTE_TODAY_QUERY,
    GLOBAL_NOTE_TYPE,
    UPSERT_DAILY_NOTE_MUTATION,
    build_upsert_daily_note_variables,
)
from peek_app_utilities.internal.peek.gateway_endpoints import SALES_ENDPOINT
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient
from peek_app_utilities.models.peek.daily_note import DailyNote


class DailyNoteService:
    def __init__(self, client: GraphQLClient) -> None:
        self._client = client

    async def get_today(self) -> DailyNote | None:
        """Returns today's daily note, or ``None`` when none is set."""
        body = await self._client.request(
            SALES_ENDPOINT, DAILY_NOTE_TODAY_QUERY, {"type": GLOBAL_NOTE_TYPE}
        )
        return to_daily_note(body.get("data"))

    async def update(self, note: str) -> DailyNote | None:
        """Upserts the daily note and returns the saved note, or ``None``."""
        body = await self._client.request(
            SALES_ENDPOINT, UPSERT_DAILY_NOTE_MUTATION, build_upsert_daily_note_variables(note)
        )
        return from_upsert_response(body.get("data"))
