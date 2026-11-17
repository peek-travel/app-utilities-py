"""The clean data model for a Peek Pro daily (dashboard) note."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class DailyNote:
    """The daily note shown on the Peek Pro dashboard."""

    note: str
    """The note text."""
