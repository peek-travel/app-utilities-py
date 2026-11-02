"""The clean data model for a Peek Pro account user (staff member / guide)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignedActivity:
    """An activity an :class:`AccountUser` is assigned to."""

    id: str
    """Activity (product) id."""
    name: str
    """Activity name."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountUser:
    """An account user on a Peek Pro account.

    Only **active** users are returned by the account-user service — inactive
    users are filtered out — so there is no status field on this model.
    """

    id: str
    """Unique identifier of the account user."""
    name: str
    """Full name."""
    email: str
    """Email address."""
    phone: str
    """Phone number."""
    assigned_activities: list[AssignedActivity]
    """The activities this user is assigned to."""
