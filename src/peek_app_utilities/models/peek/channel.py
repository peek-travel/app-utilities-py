"""The clean data model for Peek Pro reseller channels and their agents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Agent:
    """An agent (contact) belonging to a :class:`Channel`."""

    email: str | None
    """Email address, or ``None``."""
    name: str
    """Agent name."""
    internal_notes: str | None
    """Internal notes, or ``None``."""
    phone: str | None
    """Phone number, or ``None``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Channel:
    """A reseller channel on a Peek Pro account."""

    id: str
    """Unique identifier."""
    name: str
    """Channel name."""
    notes: str | None
    """Free-text notes, or ``None``."""
    pricing_model: str
    """Pricing model reported by Peek."""
    state: str
    """Channel state (e.g. active/inactive)."""
    type: str
    """Channel type."""
    agents: list[Agent]
    """Agents belonging to this channel."""
