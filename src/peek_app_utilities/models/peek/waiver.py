"""The clean data model for a signed Peek Pro waiver (liability agreement),
delivered by the waiver webhook."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Waiver:
    """A signed waiver."""

    template_id: str
    """Id of the agreement template that was signed."""
    booking_id: str
    """Id of the booking the waiver is attached to."""
    file_url: str
    """URL of the signed waiver document. ``""`` unless the parser was given
    ``full_customer_access``."""
    signed_at: str
    """When the waiver was signed (ISO datetime)."""
    is_signed_by_guardian: bool
    """Whether a guardian signed on the participant's behalf."""
    guest_name: str | None
    """Participant name captured on the waiver, if any. ``None`` unless the
    parser was given ``full_customer_access``."""
    is_optin_marketing: bool
    """Whether the participant opted in to marketing."""
    is_optin_sms: bool
    """Whether the participant opted in to SMS."""
