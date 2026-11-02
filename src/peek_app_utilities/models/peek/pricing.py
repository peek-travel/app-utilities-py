"""The clean data model for Peek Pro pricing engines and pricing overrides.

A **pricing engine** is a named container Peek Pro applies at checkout. A caller
creates one lazily, stores its id, then repeatedly **upserts pricing overrides**
onto it for a given date range. Overrides adjust ticket prices (fixed
replacement or percentage adjustment) for an activity, optionally gated by how
many spots are already taken and/or a start-time window.

Scope note: this package is a thin wrapper over the Peek pricing primitives. It
does **not** own the domain logic that decides *what* the overrides should be —
segmenting an activity across time windows, ordering overrides by tier, or
computing the ``spots_taken`` bounds. The caller builds an
:class:`UpsertOverridesInput` and the service sends it faithfully; the service
only maps between these clean shapes and the raw payload.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

FIXED_OVERRIDE_MODE: Final = "fixed"
""":attr:`FixedResourceOptionOverride.mode` — replace the ticket price outright."""
PERCENTAGE_OVERRIDE_MODE: Final = "percentage"
""":attr:`PercentageResourceOptionOverride.mode` — adjust the price by a percentage."""

OverrideMode = Literal["fixed", "percentage"]
"""Discriminant of a resource-option override."""


# ─── Shared value types ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingMoney:
    """A monetary value on a pricing override.

    ``amount`` is intentionally a **string** (e.g. ``"50.00"``), never a number —
    the Peek API rejects floats here, and stringly-typed money avoids precision
    loss.
    """

    amount: str
    """Numeric amount as a decimal string (e.g. ``"50.00"``)."""
    currency: str
    """ISO 4217 currency code (e.g. ``"USD"``)."""
    display_price: str | None = None
    """Human-formatted display string for the amount (e.g. ``"$50.00"``), as
    rendered by Peek.

    Populated on values **read back** (resolved overrides, product ticket price
    ranges). It is optional and purely informational — omit it when *building*
    an override input; Peek derives it from ``amount``/``currency``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingNamedRef:
    """An ``{id, name}`` reference to a Peek entity echoed back in a response."""

    id: str
    """Stable Peek identifier."""
    name: str
    """Human-readable display name."""


# ─── Pricing engine: inputs & outputs ────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateEngineInput:
    """Input for creating a pricing engine."""

    name: str
    """Display name for the engine."""
    activity_ids: Sequence[str] | None = None
    """Optional list of activity ids the engine is scoped to. Omit (or pass an
    empty list) to create an unfiltered engine that applies to all activities."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreatedPricingEngine:
    """The result of creating a pricing engine.

    The create mutation returns only the new engine's id; store it for
    subsequent override upserts.
    """

    id: str
    """The new engine's id."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateEngineInput:
    """Input for updating a pricing engine's name and/or activity scope."""

    engine_id: str
    """The engine to update."""
    name: str
    """New display name."""
    activity_ids: Sequence[str] | None = None
    """Activity ids the engine should be scoped to. An empty list (or omitting
    the field) **clears** the filter so the engine applies to all activities."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingEngine:
    """A pricing engine reference as echoed back by the API."""

    id: str
    """Engine id."""
    name: str
    """Engine display name."""


# ─── Override building blocks (used to build an upsert) ───────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class FixedResourceOptionOverride:
    """A single ticket (resourceOption) price override that **replaces** the
    ticket price outright with :class:`PricingMoney`."""

    id: str
    """The Peek resourceOption (ticket) id being overridden."""
    price: PricingMoney
    """The replacement price."""
    mode: Literal["fixed"] = FIXED_OVERRIDE_MODE


@dataclass(frozen=True, slots=True, kw_only=True)
class PercentageResourceOptionOverride:
    """A single ticket (resourceOption) price override that **adjusts** the
    ticket price by a percentage."""

    id: str
    """The Peek resourceOption (ticket) id being overridden."""
    percentage_adjustment: str
    """Percentage adjustment as a decimal string, e.g. ``"-25"`` for 25% off.
    Must be greater than ``-100``."""
    mode: Literal["percentage"] = PERCENTAGE_OVERRIDE_MODE


ResourceOptionOverride = FixedResourceOptionOverride | PercentageResourceOptionOverride
"""A single ticket price override, discriminated by ``mode``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SpotsTakenBounds:
    """Bounds for a :class:`SpotsTakenFilter`.

    ``min_spots``/``max_spots`` are **zero-indexed spots-taken counts**, not
    ticket counts — e.g. "applies from the 5th ticket onward" is
    ``SpotsTakenBounds(min_spots=4)``. The caller is responsible for this
    off-by-one conversion from ticket-count ranges.
    """

    min_spots: int | None = None
    """Lower bound (inclusive) on spots already taken. ``None`` for no lower bound."""
    max_spots: int | None = None
    """Upper bound (inclusive) on spots already taken. ``None`` for no upper bound."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SpotsTakenFilter:
    """Restricts an override by how many spots are already taken."""

    spots_taken: SpotsTakenBounds
    """The inclusive spots-taken bounds."""


@dataclass(frozen=True, slots=True, kw_only=True)
class StartTimeRangeFilter:
    """Restricts an override to a start-time window."""

    start_time_range: str
    """A PostgreSQL-style inclusive range string ``"[HH:MM:SS,HH:MM:SS]"``."""


PricingOverrideFilter = SpotsTakenFilter | StartTimeRangeFilter
"""A filter gating when an override applies. An override may carry zero, one,
or both variants."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingOverride:
    """One override entry for an activity: which tickets it adjusts, in what
    order, under which filters."""

    order: int
    """The override's precedence index (0-based). The caller assigns this — Peek
    evaluates lower ``order`` values first, so higher-discount / more-specific
    tiers should get lower numbers."""
    resource_options: Sequence[ResourceOptionOverride]
    """The per-ticket price overrides applied by this entry."""
    filters: Sequence[PricingOverrideFilter] = ()
    """Zero or more filters gating when this entry applies."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivityOverrides:
    """The set of overrides to apply for a single activity."""

    activity_id: str
    """The Peek activity id these overrides apply to."""
    overrides: Sequence[PricingOverride]
    """The overrides for this activity. Pass an **empty list to clear** all
    overrides for the activity — never omit the activity to clear it."""


# ─── Upsert / clear: inputs ──────────────────────────────────────────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class UpsertOverridesInput:
    """The full input for upserting pricing overrides onto an engine.

    Mirrors the Peek ``upsertPricingOverridesActivityContexts`` input verbatim.
    The caller owns all segmentation and ordering; the service sends this as-is.
    """

    engine_id: str
    """The engine to write overrides to (its :attr:`CreatedPricingEngine.id`)."""
    date_range: str
    """The date range the overrides apply to, as a PostgreSQL-style inclusive
    range string. For a single day, both ends are the same:
    ``"[2025-07-04,2025-07-04]"``."""
    activities: Sequence[ActivityOverrides]
    """One entry per activity being written (or cleared)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ClearOverridesInput:
    """Convenience input for clearing all overrides across a set of activities
    for a date range. Equivalent to an :class:`UpsertOverridesInput` whose every
    activity carries ``overrides=[]``."""

    engine_id: str
    """The engine to clear overrides on."""
    date_range: str
    """The date range to clear, same format as :attr:`UpsertOverridesInput.date_range`."""
    activity_ids: Sequence[str]
    """The activity ids to clear. Recover these from a prior sync's payload."""


# ─── Upsert / clear: output (the resolved state Peek echoes back) ─────────────


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedFixedOverride:
    """A ticket price override as **resolved** by Peek: a fixed replacement price."""

    price: PricingMoney
    """The resolved replacement price."""
    mode: Literal["fixed"] = FIXED_OVERRIDE_MODE


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedPercentageOverride:
    """A ticket price override as **resolved** by Peek: a percentage adjustment."""

    percentage_adjustment: str
    """The resolved percentage adjustment as a decimal string."""
    mode: Literal["percentage"] = PERCENTAGE_OVERRIDE_MODE


ResolvedOverride = ResolvedFixedOverride | ResolvedPercentageOverride
"""A ticket price override as resolved by Peek, discriminated by ``mode``. This
normalizes Peek's union (a ``price`` object vs a bare ``percentageAdjustment``)
into the same ``mode``-tagged shape used on input."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedResourceOption:
    """A single ticket's resolved override within a returned context."""

    resource_option: PricingNamedRef
    """The ticket (resourceOption) this override resolved for."""
    override: ResolvedOverride
    """The resolved fixed or percentage override."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedPricingOverride:
    """A single resolved override entry within a returned activity context."""

    order: int
    """The override's precedence index as stored by Peek."""
    resource_options: list[ResolvedResourceOption]
    """The resolved per-ticket overrides."""
    filters: list[PricingOverrideFilter]
    """The filters gating this override, normalized to the same shape as the
    :data:`PricingOverrideFilter` used on input."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingActivityContext:
    """The resolved pricing state for one activity on one date, as returned by
    an upsert or clear. Useful as an audit record of exactly what Peek stored."""

    date: str
    """The date the context applies to (ISO ``YYYY-MM-DD``)."""
    activity: PricingNamedRef
    """The activity the overrides belong to."""
    engine: PricingNamedRef
    """The engine the overrides live under."""
    overrides: list[ResolvedPricingOverride]
    """The resolved overrides (empty when the date was cleared)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UpsertOverridesResult:
    """The result of an upsert or clear: the resolved contexts Peek returned."""

    activity_contexts: list[PricingActivityContext] = field(default_factory=list)
    """One entry per activity written or cleared in the request."""
