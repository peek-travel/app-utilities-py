"""Pure, I/O-free mapping of raw availability-time nodes → the clean
:class:`AvailabilityTime` model.
"""

from __future__ import annotations

from peek_app_utilities.internal.peek.availability.availability_queries import (
    AvailabilityNode,
    AvailabilityTimeNode,
    DurationLengthNode,
    DurationNode,
    MoneyNode,
)
from peek_app_utilities.models.peek.availability_time import (
    Availability,
    AvailabilityTime,
    Duration,
    DurationLength,
)
from peek_app_utilities.models.peek.money import Money


def to_availability_time(node: AvailabilityTimeNode) -> AvailabilityTime:
    """Converts a raw availability-time node into the public model."""
    duration: DurationNode = node.get("duration") or {}
    length: DurationLengthNode = duration.get("length") or {}
    return AvailabilityTime(
        id=node.get("id") or "",
        time=node.get("time") or "",
        from_=node.get("from") or "",
        end=node.get("end") or "",
        duration=Duration(
            name=duration.get("name") or "",
            length=DurationLength(
                amount=int(length.get("amount") or 0), unit=length.get("unit") or ""
            ),
        ),
        status=node.get("status") or "",
        price=_to_money(node.get("price")),
        availability=[_from_availability_node(a) for a in node.get("availability") or []],
    )


def _to_money(node: MoneyNode | None) -> Money | None:
    if not node:
        return None
    return Money(
        amount=node.get("amount") or "",
        currency=node.get("currency") or "",
        formatted=node.get("formatted") or "",
    )


def _from_availability_node(node: AvailabilityNode) -> Availability:
    return Availability(
        qty=int(node.get("qty") or 0),
        taken=int(node.get("taken") or 0),
        resource_option_id=node.get("resourceOptionId") or "",
    )
