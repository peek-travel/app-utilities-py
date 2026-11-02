"""The clean data model for a Peek Pro resource pool (e.g. guides, equipment)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ResourcePoolMode = Literal["ACTIVITY", "ALL"]
"""Filter mode for which resource pools to return."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourcePoolAccountUser:
    """Minimal account-user reference attached to a :class:`ResourcePool`."""

    id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourcePool:
    """A resource pool on a Peek Pro account."""

    id: str
    """Unique identifier."""
    name: str
    """Display name."""
    image_url: str | None
    """Image URL, or ``None``."""
    mode: str
    """Allocation mode reported by Peek."""
    color_hex: str | None
    """Display color as a hex string, or ``None``."""
    quantity: int | None
    """Configured quantity, or ``None`` when not set."""
    category: str
    """Category (e.g. ``"guide"``)."""
    capacity: int | None
    """Capacity, or ``None`` when not set."""
    resource_tracking_mode: str | None
    """How the resource is tracked, or ``None``."""
    account_user: ResourcePoolAccountUser | None
    """The account user backing this pool (e.g. for guides), or ``None``."""
