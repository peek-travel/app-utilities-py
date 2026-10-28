"""Command-line harness for exercising the Peek access-service calls against a
live API. It is a **developer test tool**, not part of the published package —
it lives outside ``src/`` and is never packaged.

Auth model (see the folder README): the API only checks two headers,
``pk-api-key`` (the gateway key) and ``X-Peek-Auth: Bearer <token>``. All
config — gateway key, app id, base url, and the bearer token — lives in a
gitignored ``.env``. The token changes/expires; when ``PEEK_AUTH_TOKEN`` is
unset the harness prompts for it (hidden input) at call time. Because the token
is supplied directly, this harness skips the JWT-minting machinery in
``PeekAccessService`` and builds the internal ``GraphQLClient`` itself, then
wires the real resource services onto it — so it exercises the exact same
service + converter code a consumer would.

Usage::

    run.sh <function_name> [param1] [param2] ...
    run.sh help
    run.sh help <function_name>
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import sys
import types
import typing
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from getpass import getpass
from pathlib import Path
from typing import Any, Final

from peek_app_utilities import (
    AccountUserService,
    AddAddonInput,
    AvailabilityService,
    AvailabilityTimesQuery,
    BookingReadOptions,
    BookingService,
    BookingServiceOptions,
    BookingTimeRangeSearch,
    ClearOverridesInput,
    CreateBookingInput,
    CreateEngineInput,
    CreatePromoCodeInput,
    DailyNoteService,
    GuideAssignment,
    Logger,
    MakePaymentInput,
    MembershipPurchaseInput,
    MembershipService,
    PricingService,
    ProductService,
    PromoCodeService,
    RefundInput,
    ResellerService,
    ResourcePoolService,
    ReviewService,
    SetMetaDataAttachmentInput,
    SetMetaDataGuestInput,
    TimeslotService,
    UpdateEngineInput,
    UpsertOverridesInput,
    noop_logger,
)
from peek_app_utilities.access_options import ResolvedAccessOptions
from peek_app_utilities.access_service_config import (
    DEFAULT_RETRY_DELAYS_MS,
    create_http_client,
    require_non_empty,
    resolve_base_api_url,
)
from peek_app_utilities.internal.peek.gateway_endpoints import (
    V2_EXTENDABLE_SLUG,
    peek_api_endpoints,
)
from peek_app_utilities.internal.peek.graphql_client import GraphQLClient, GraphQLClientOptions
from peek_app_utilities.logger import LogContext

HARNESS_NAME: Final = "gql-cli"
"""Name the harness reports in config-validation errors."""
DEFAULT_BASE_URL: Final = "https://apps.peekapis.com/backoffice-gql"
"""API default when ``.env`` sets no ``PEEK_BASE_URL``/``PEEK_API_URL``."""
DOTENV_FILE: Final = ".env"
TOKEN_PROMPT: Final = "X-Peek-Auth token: "
HELP_COMMAND: Final = "help"
SIGNATURE_COLUMN_WIDTH: Final = 52
JSON_INDENT: Final = 2

ENV_AUTH_TOKEN: Final = "PEEK_AUTH_TOKEN"
ENV_API_URL: Final = "PEEK_API_URL"
ENV_GATEWAY_KEY: Final = "PEEK_GATEWAY_KEY"
ENV_APP_ID: Final = "PEEK_APP_ID"
ENV_BASE_URL: Final = "PEEK_BASE_URL"
ENV_FULL_CUSTOMER_ACCESS: Final = "PEEK_FULL_CUSTOMER_ACCESS"
ENV_INTEGRATOR: Final = "PEEK_INTEGRATOR"
ENV_DEBUG: Final = "PEEK_DEBUG"

PII_FLAG: Final = "--pii"
"""Command-line switch that enables PII-gated calls for this one invocation."""

ERROR_NO_TOKEN: Final = (
    f"No auth token. Set {ENV_AUTH_TOKEN} in {DOTENV_FILE} or enter it when prompted."
)
ERROR_ABORTED: Final = "Aborted."

_TRUTHY_RE: Final = re.compile(r"^(1|true|yes)$", re.IGNORECASE)
_FALSY_RE: Final = re.compile(r"^(0|false|no)$", re.IGNORECASE)
_CAMEL_BOUNDARY_RE: Final = re.compile(r"(?<!^)(?=[A-Z])")

# Error attributes surfaced by `describe_error` when present on the exception.
_ERROR_DETAIL_ATTRS: Final = ("operation", "status_code", "url", "body", "graphql_errors")


# ─── Auth token resolution ───────────────────────────────────────────────────


def prompt_secret(label: str) -> str:
    """Reads a secret from the terminal without echoing it. Falls back to reading
    a piped line when stdin is not a TTY (``echo "$TOKEN" | run.sh …``)."""
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    try:
        return getpass(label)
    except (EOFError, KeyboardInterrupt) as exc:
        raise RuntimeError(ERROR_ABORTED) from exc


def resolve_auth_token() -> str:
    """Resolves the ``X-Peek-Auth`` bearer token: ``PEEK_AUTH_TOKEN`` from
    ``.env``/env if set, otherwise prompts for it. Prompting happens only at call
    time, so ``help`` and arg errors never ask for a token."""
    from_env = os.environ.get(ENV_AUTH_TOKEN, "").strip()
    if from_env:
        return from_env
    entered = prompt_secret(TOKEN_PROMPT).strip()
    if not entered:
        raise RuntimeError(ERROR_NO_TOKEN)
    return entered


# ─── .env loading (no dependency) ────────────────────────────────────────────


def load_dotenv() -> None:
    """Reads simple ``KEY=VALUE`` lines from ``.env`` in the working directory and
    fills any keys not already present in the environment (real env wins). A
    missing file is fine — the harness just relies on the ambient environment."""
    try:
        raw = (Path.cwd() / DOTENV_FILE).read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, _, value = trimmed.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str) -> str | None:
    """An environment value, with the empty string normalized to ``None``."""
    return os.environ.get(name) or None


def _is_truthy(value: str | None) -> bool:
    return bool(value) and _TRUTHY_RE.match(value or "") is not None


# ─── Service context ─────────────────────────────────────────────────────────


class _StderrLogger:
    """Diagnostics to stderr (``PEEK_DEBUG=1``) so stdout stays pure JSON."""

    def info(self, message: str, context: LogContext | None = None) -> None:
        self._emit("info", message, context)

    def warn(self, message: str, context: LogContext | None = None) -> None:
        self._emit("warn", message, context)

    def error(self, message: str, context: LogContext | None = None) -> None:
        self._emit("error", message, context)

    @staticmethod
    def _emit(level: str, message: str, context: LogContext | None) -> None:
        print(f"[{level}] {message}", context if context is not None else "", file=sys.stderr)


@dataclass(frozen=True, slots=True, kw_only=True)
class Ctx:
    """The real resource services, wired onto one shared client."""

    products: ProductService
    account_users: AccountUserService
    resource_pools: ResourcePoolService
    timeslots: TimeslotService
    resellers: ResellerService
    promo_codes: PromoCodeService
    pricing: PricingService
    daily_notes: DailyNoteService
    availability: AvailabilityService
    memberships: MembershipService
    bookings: BookingService
    reviews: ReviewService
    aclose: Callable[[], Awaitable[None]]
    """Closes the harness-owned HTTP client."""


def build_context(auth_token: str, *, full_customer_access: bool) -> Ctx:
    """Builds the internal client with the pasted token, then wires every service
    exactly the way :class:`PeekAccessService` does."""
    api_url = _env(ENV_API_URL)
    gateway_key = _env(ENV_GATEWAY_KEY)
    app_id = _env(ENV_APP_ID)
    base_url = _env(ENV_BASE_URL) or DEFAULT_BASE_URL
    integrator = _env(ENV_INTEGRATOR) or app_id or HARNESS_NAME

    # Mirror PeekAccessService's constructor guards: without an `api_url` the
    # legacy v1 gateway needs both `app_id` (the URL path segment) and
    # `gateway_key` (the `pk-api-key` header). Fail fast with a clear message
    # instead of silently building a `…/None/sales` URL (or dropping the key) and
    # getting an opaque API error.
    if not api_url:
        require_non_empty(app_id, ENV_APP_ID, HARNESS_NAME)
        require_non_empty(gateway_key, ENV_GATEWAY_KEY, HARNESS_NAME)

    logger: Logger = _StderrLogger() if _is_truthy(_env(ENV_DEBUG)) else noop_logger

    # Mirror PeekAccessService's URL model: an `api_url` is the base directly
    # (its own routing slug stripped back off) and routes through the registry
    # slug; otherwise the base is `base_url/app_id` on the legacy v1 gateway.
    use_registry_slug = bool(api_url)
    base_api_url = (
        resolve_base_api_url(api_url, V2_EXTENDABLE_SLUG, HARNESS_NAME)
        if api_url
        else f"{base_url}/{app_id}"
    )
    http_client = create_http_client()
    client = GraphQLClient(
        GraphQLClientOptions(
            base_api_url=base_api_url,
            endpoints=peek_api_endpoints(use_registry_slug),
            gateway_key=gateway_key,
            get_token=lambda: auth_token,
            retry_delays_ms=DEFAULT_RETRY_DELAYS_MS,
            logger=logger,
            http_client=http_client,
        )
    )

    products = ProductService(client)
    account_users = AccountUserService(client)
    resource_pools = ResourcePoolService(client)
    access_options = ResolvedAccessOptions(full_customer_access=full_customer_access)
    return Ctx(
        products=products,
        account_users=account_users,
        resource_pools=resource_pools,
        timeslots=TimeslotService(
            client,
            resource_pool_service=resource_pools,
            account_user_service=account_users,
        ),
        resellers=ResellerService(client),
        promo_codes=PromoCodeService(client),
        pricing=PricingService(client),
        daily_notes=DailyNoteService(client),
        availability=AvailabilityService(client),
        memberships=MembershipService(client),
        bookings=BookingService(
            client,
            product_service=products,
            options=BookingServiceOptions(access_options=access_options, integrator=integrator),
        ),
        reviews=ReviewService(client, access_options),
        aclose=http_client.aclose,
    )


# ─── JSON → dataclass input building ─────────────────────────────────────────


def to_snake_case(key: str) -> str:
    """``includeGuests`` → ``include_guests`` (already-snake keys pass through)."""
    return _CAMEL_BOUNDARY_RE.sub("_", key).lower()


def _strip_optional(hint: Any) -> Any:
    """``X | None`` → ``X``; anything else unchanged."""
    if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union:
        members = [m for m in typing.get_args(hint) if m is not type(None)]
        if len(members) == 1:
            return members[0]
    return hint


def _dataclass_variants(hint: Any) -> list[type[Any]]:
    """The dataclass members of a (possibly single-member) union hint."""
    candidates = (
        typing.get_args(hint)
        if typing.get_origin(hint) in (types.UnionType, typing.Union)
        else (hint,)
    )
    return [c for c in candidates if isinstance(c, type) and dataclasses.is_dataclass(c)]


def _pick_variant(variants: Sequence[type[Any]], data: Mapping[str, Any]) -> type[Any]:
    """For a discriminated union, the variant whose field set best fits the keys
    present: every key must be a field and every required field must be
    present. Falls back to the first variant so the dataclass constructor
    reports the real problem."""
    keys = {to_snake_case(k) for k in data}
    for variant in variants:
        fields = dataclasses.fields(variant)
        names = {f.name for f in fields}
        required = {
            f.name
            for f in fields
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        }
        if keys <= names and required <= keys:
            return variant
    return variants[0]


def coerce_value(hint: Any, value: Any) -> Any:
    """Recursively converts a JSON value into the shape ``hint`` names: nested
    dataclasses from objects, ``list``/``Sequence`` of them from arrays, and
    everything else passed through."""
    if value is None:
        return None
    hint = _strip_optional(hint)
    origin = typing.get_origin(hint)
    if origin in (list, Sequence, typing.Sequence) and isinstance(value, list):
        (item_hint,) = typing.get_args(hint) or (Any,)
        return [coerce_value(item_hint, item) for item in value]
    variants = _dataclass_variants(hint)
    if variants and isinstance(value, Mapping):
        return from_dict(_pick_variant(variants, value), value)
    return value


def from_dict(cls: type[Any], data: Mapping[str, Any]) -> Any:
    """Instantiates the frozen ``kw_only`` dataclass ``cls`` from a JSON object,
    accepting either ``snake_case`` or ``camelCase`` keys (so the TypeScript
    README examples work verbatim) and recursing into nested models."""
    hints = typing.get_type_hints(cls)
    kwargs = {
        to_snake_case(key): coerce_value(hints.get(to_snake_case(key), Any), value)
        for key, value in data.items()
    }
    return cls(**kwargs)


def from_dict_list(cls: type[Any], data: Any) -> list[Any]:
    """A list of ``cls`` from a JSON array."""
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of {cls.__name__} objects.")
    return [from_dict(cls, item) for item in data]


def _optional(cls: type[Any], data: Any) -> Any:
    """``from_dict`` for an optional object param (``None`` when omitted)."""
    return None if data is None else from_dict(cls, data)


def _given(**kwargs: Any) -> dict[str, Any]:
    """Keyword arguments for the optional params the caller actually passed, so
    the service's own defaults apply to the rest."""
    return {k: v for k, v in kwargs.items() if v is not None}


# ─── Function registry ───────────────────────────────────────────────────────


class ParamKind(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"


@dataclass(frozen=True, slots=True, kw_only=True)
class ParamSpec:
    name: str
    kind: ParamKind
    required: bool
    desc: str


RunFn = Callable[[Ctx, Sequence[Any]], Awaitable[Any]]


@dataclass(frozen=True, slots=True, kw_only=True)
class FnSpec:
    name: str
    group: str
    desc: str
    params: Sequence[ParamSpec]
    run: RunFn
    pii: bool = False
    """``True`` for calls blocked unless PEEK_FULL_CUSTOMER_ACCESS is on."""


def p(name: str, kind: ParamKind, desc: str, required: bool = True) -> ParamSpec:
    return ParamSpec(name=name, kind=kind, required=required, desc=desc)


S, N, B, J = ParamKind.STRING, ParamKind.NUMBER, ParamKind.BOOLEAN, ParamKind.JSON

# fmt: off
REGISTRY: Final[Sequence[FnSpec]] = (
    # ── products ──
    FnSpec(name="get_all_products", group="products", desc="Activities + add-ons, flat list.", params=[], run=lambda c, a: c.products.get_all_products()),
    FnSpec(name="get_all_activities", group="products", desc="ACTIVITY-typed products only.", params=[], run=lambda c, a: c.products.get_all_activities()),
    FnSpec(name="get_all_rentals", group="products", desc="RENTAL-typed products only.", params=[], run=lambda c, a: c.products.get_all_rentals()),
    FnSpec(name="get_all_addons", group="products", desc="Add-on products only.", params=[], run=lambda c, a: c.products.get_all_addons()),
    FnSpec(name="get_custom_questions", group="products", desc="An activity's custom questions.", params=[p("product_id", S, "Activity id")], run=lambda c, a: c.products.get_custom_questions(a[0])),

    # ── account users ──
    FnSpec(name="get_all_account_users", group="account-users", desc="All active account users.", params=[], run=lambda c, a: c.account_users.get_all()),
    FnSpec(name="get_account_user_by_id", group="account-users", desc="One active account user by id.", params=[p("user_id", S, "Account user id")], run=lambda c, a: c.account_users.get_by_id(a[0])),

    # ── resource pools ──
    FnSpec(name="get_all_resource_pools", group="resource-pools", desc="All resource pools.", params=[p("mode", S, 'Optional mode: ACTIVITY|ALL', False)], run=lambda c, a: c.resource_pools.get_all(a[0])),

    # ── timeslots ──
    FnSpec(name="get_timeslots_for_day", group="timeslots", desc="Timeslots for an activity on a date.", params=[p("product_id", S, "Activity id"), p("date", S, "YYYY-MM-DD"), p("filter", S, "Optional: all|withBookings|withoutBookings (default all)", False)], run=lambda c, a: c.timeslots.get_for_day(a[0], a[1], a[2])),
    FnSpec(name="get_timeslot_by_id", group="timeslots", desc="One timeslot by id.", params=[p("timeslot_id", S, "Timeslot id")], run=lambda c, a: c.timeslots.get_by_id(a[0])),
    FnSpec(name="set_timeslot_availability", group="timeslots", desc="Set a timeslot's availability status.", params=[p("timeslot_id", S, "Timeslot id"), p("status", S, "New status")], run=lambda c, a: c.timeslots.set_availability(a[0], a[1])),
    FnSpec(name="set_timeslot_notes", group="timeslots", desc="Set a timeslot's manifest notes.", params=[p("timeslot_id", S, "Timeslot id"), p("manifest_notes", S, "Notes text")], run=lambda c, a: c.timeslots.set_notes(a[0], a[1])),
    FnSpec(name="assign_timeslot_guide", group="timeslots", desc="Assign/unassign guides across timeslots.", params=[p("assignment", J, "GuideAssignment JSON")], run=lambda c, a: c.timeslots.assign_guide(from_dict(GuideAssignment, a[0]))),

    # ── resellers ──
    FnSpec(name="get_all_channels", group="resellers", desc="All reseller channels + agents.", params=[p("agents_per_channel", N, "Optional page size for agents", False)], run=lambda c, a: c.resellers.get_all_channels(a[0])),

    # ── promo codes ──
    FnSpec(name="get_all_promo_codes", group="promo-codes", desc="All promo codes.", params=[], run=lambda c, a: c.promo_codes.get_all()),
    FnSpec(name="create_promo_code", group="promo-codes", desc="Create a promo code.", params=[p("input", J, "CreatePromoCodeInput JSON")], run=lambda c, a: c.promo_codes.create(from_dict(CreatePromoCodeInput, a[0]))),

    # ── pricing ──
    FnSpec(name="create_pricing_engine", group="pricing", desc="Create a pricing engine.", params=[p("input", J, "CreateEngineInput JSON")], run=lambda c, a: c.pricing.create_engine(from_dict(CreateEngineInput, a[0]))),
    FnSpec(name="update_pricing_engine", group="pricing", desc="Update a pricing engine.", params=[p("input", J, "UpdateEngineInput JSON")], run=lambda c, a: c.pricing.update_engine(from_dict(UpdateEngineInput, a[0]))),
    FnSpec(name="delete_pricing_engine", group="pricing", desc="Delete a pricing engine.", params=[p("engine_id", S, "Engine id")], run=lambda c, a: c.pricing.delete_engine(a[0])),
    FnSpec(name="upsert_pricing_overrides", group="pricing", desc="Upsert pricing overrides.", params=[p("input", J, "UpsertOverridesInput JSON")], run=lambda c, a: c.pricing.upsert_overrides(from_dict(UpsertOverridesInput, a[0]))),
    FnSpec(name="clear_pricing_overrides", group="pricing", desc="Clear pricing overrides.", params=[p("input", J, "ClearOverridesInput JSON")], run=lambda c, a: c.pricing.clear_overrides(from_dict(ClearOverridesInput, a[0]))),

    # ── daily notes ──
    FnSpec(name="get_daily_note_today", group="daily-notes", desc="Today's daily note.", params=[], run=lambda c, a: c.daily_notes.get_today()),
    FnSpec(name="update_daily_note", group="daily-notes", desc="Set today's daily note.", params=[p("note", S, "Note text")], run=lambda c, a: c.daily_notes.update(a[0])),

    # ── availability ──
    FnSpec(name="get_availability_times", group="availability", desc="Availability times for a query.", params=[p("query", J, "AvailabilityTimesQuery JSON")], run=lambda c, a: c.availability.get_availability_times(from_dict(AvailabilityTimesQuery, a[0]))),

    # ── memberships ──
    FnSpec(name="get_all_memberships", group="memberships", desc="All memberships.", params=[], run=lambda c, a: c.memberships.get_all()),
    FnSpec(name="purchase_membership", group="memberships", desc="Purchase a membership.", params=[p("input", J, "MembershipPurchaseInput JSON")], run=lambda c, a: c.memberships.purchase(from_dict(MembershipPurchaseInput, a[0]))),

    # ── bookings ──
    FnSpec(name="get_booking_by_id", group="bookings", desc="One booking by id.", params=[p("booking_id", S, "Booking id"), p("options", J, "Optional BookingReadOptions JSON", False)], run=lambda c, a: c.bookings.get_by_id(a[0], _optional(BookingReadOptions, a[1]))),
    FnSpec(name="search_bookings_by_time_range", group="bookings", desc="Bookings within a time range.", params=[p("input", J, "BookingTimeRangeSearch JSON")], run=lambda c, a: c.bookings.search_by_time_range(from_dict(BookingTimeRangeSearch, a[0]))),
    FnSpec(name="search_bookings_by_timeslot", group="bookings", desc="Bookings on a timeslot.", params=[p("timeslot_id", S, "Timeslot id"), p("options", J, "Optional BookingReadOptions JSON", False)], run=lambda c, a: c.bookings.search_by_timeslot(a[0], _optional(BookingReadOptions, a[1]))),
    FnSpec(name="get_booking_guests", group="bookings", desc="Guests on a booking.", params=[p("booking_id", S, "Booking id")], run=lambda c, a: c.bookings.get_guests(a[0])),
    FnSpec(name="get_booking_payments_on_file", group="bookings", desc="Payments on file for a booking.", pii=True, params=[p("booking_id", S, "Booking id")], run=lambda c, a: c.bookings.get_payments_on_file(a[0])),
    FnSpec(name="append_booking_note", group="bookings", desc="Append/overwrite a booking note.", params=[p("booking_id", S, "Booking id"), p("note", S, "Note text"), p("mode", S, "Optional: append|overwrite (default append)", False)], run=lambda c, a: c.bookings.append_note(a[0], a[1], **_given(mode=a[2]))),
    FnSpec(name="set_booking_checkin_status", group="bookings", desc="Set a booking's check-in status.", params=[p("booking_id", S, "Booking id"), p("checked_in", B, "true|false")], run=lambda c, a: c.bookings.set_checkin_status(a[0], a[1])),
    FnSpec(name="cancel_booking", group="bookings", desc="Cancel a booking.", params=[p("booking_id", S, "Booking id"), p("notes", S, "Optional cancel note", False)], run=lambda c, a: c.bookings.cancel(a[0], **_given(notes=a[1]))),
    FnSpec(name="make_booking_payment", group="bookings", desc="Take a payment on a booking.", pii=True, params=[p("input", J, "MakePaymentInput JSON")], run=lambda c, a: c.bookings.make_payment(from_dict(MakePaymentInput, a[0]))),
    FnSpec(name="refund_booking", group="bookings", desc="Refund a booking.", pii=True, params=[p("input", J, "RefundInput JSON")], run=lambda c, a: c.bookings.refund(from_dict(RefundInput, a[0]))),
    FnSpec(name="create_booking_invoice_link", group="bookings", desc="Create an invoice link for a booking.", pii=True, params=[p("booking_id", S, "Booking id")], run=lambda c, a: c.bookings.create_invoice_link(a[0])),
    FnSpec(name="list_booking_addons", group="bookings", desc="Add-ons available/attached on a booking.", params=[p("booking_id", S, "Booking id")], run=lambda c, a: c.bookings.list_addons(a[0])),
    FnSpec(name="add_booking_addon", group="bookings", desc="Add an add-on to a booking.", pii=True, params=[p("booking_id", S, "Booking id"), p("input", J, "AddAddonInput JSON")], run=lambda c, a: c.bookings.add_addon(a[0], from_dict(AddAddonInput, a[1]))),
    FnSpec(name="remove_booking_addon", group="bookings", desc="Remove an add-on from a booking.", pii=True, params=[p("booking_id", S, "Booking id"), p("input", J, "AddAddonInput JSON")], run=lambda c, a: c.bookings.remove_addon(a[0], from_dict(AddAddonInput, a[1]))),
    FnSpec(name="create_booking", group="bookings", desc="Create a booking.", params=[p("input", J, "CreateBookingInput JSON")], run=lambda c, a: c.bookings.create(from_dict(CreateBookingInput, a[0]))),
    FnSpec(name="update_custom_status", group="bookings", desc="Set a booking's operator custom status.", params=[p("booking_id", S, "Booking id"), p("custom_status", S, "Non-empty status text")], run=lambda c, a: c.bookings.update_custom_status(a[0], a[1])),
    FnSpec(name="get_meta_data", group="bookings", desc="A booking's custom-field metadata (scoped by PEEK_INTEGRATOR).", params=[p("booking_id", S, "Booking id")], run=lambda c, a: c.bookings.get_meta_data(a[0])),
    FnSpec(name="set_meta_data_guest", group="bookings", desc="Upsert the guest metadata field.", params=[p("booking_id", S, "Booking id"), p("guests", J, "SetMetaDataGuestInput[] JSON")], run=lambda c, a: c.bookings.set_meta_data_guest(a[0], from_dict_list(SetMetaDataGuestInput, a[1]))),
    FnSpec(name="set_meta_data_attachment", group="bookings", desc="Upsert the attachment metadata field.", params=[p("booking_id", S, "Booking id"), p("attachments", J, "SetMetaDataAttachmentInput[] JSON")], run=lambda c, a: c.bookings.set_meta_data_attachment(a[0], from_dict_list(SetMetaDataAttachmentInput, a[1]))),
    FnSpec(name="set_meta_data_manifest_url", group="bookings", desc="Upsert the manifest_url metadata field.", params=[p("booking_id", S, "Booking id"), p("url", S, "Manifest URL")], run=lambda c, a: c.bookings.set_meta_data_manifest_url(a[0], a[1])),
    FnSpec(name="set_meta_data_reservation_id", group="bookings", desc="Upsert the reservation_id metadata field.", params=[p("booking_id", S, "Booking id"), p("reservation_id", S, "Reservation id")], run=lambda c, a: c.bookings.set_meta_data_reservation_id(a[0], a[1])),
    FnSpec(name="set_meta_data_booking_status", group="bookings", desc="Upsert the booking_status metadata field.", params=[p("booking_id", S, "Booking id"), p("status", S, "Status text")], run=lambda c, a: c.bookings.set_meta_data_booking_status(a[0], a[1])),
    FnSpec(name="set_meta_data_assigned_product", group="bookings", desc="Upsert the assigned_product metadata field.", params=[p("booking_id", S, "Booking id"), p("product_name", S, "Product name")], run=lambda c, a: c.bookings.set_meta_data_assigned_product(a[0], a[1])),
    FnSpec(name="set_meta_data_assigned_employee", group="bookings", desc="Upsert the assigned_employee metadata field.", params=[p("booking_id", S, "Booking id"), p("employee_name", S, "Employee name")], run=lambda c, a: c.bookings.set_meta_data_assigned_employee(a[0], a[1])),
    FnSpec(name="set_meta_data_insurance_purchased", group="bookings", desc="Upsert the insurance_purchased metadata field.", params=[p("booking_id", S, "Booking id"), p("insurance_purchased", B, "true|false")], run=lambda c, a: c.bookings.set_meta_data_insurance_purchased(a[0], a[1])),

    # ── reviews ──
    FnSpec(name="get_reviews", group="reviews", desc="Reviews for an activity.", params=[p("product_id", S, "Activity id"), p("review_count", N, "Optional page size (1-50)", False), p("review_offset", N, "Optional offset", False)], run=lambda c, a: c.reviews.get_reviews(a[0], **_given(review_count=a[1], review_offset=a[2]))),
    FnSpec(name="get_all_review_summaries", group="reviews", desc="Per-activity review summaries.", params=[], run=lambda c, a: c.reviews.get_all_review_summaries()),
)
# fmt: on

BY_NAME: Final[Mapping[str, FnSpec]] = {fn.name: fn for fn in REGISTRY}


# ─── Arg coercion + help ─────────────────────────────────────────────────────


def _coerce_number(param: ParamSpec, value: str) -> int | float:
    """``int`` when the text is integral, else ``float`` — the services take ``int``
    for counts and offsets."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        raise ValueError(f'Param "{param.name}" must be a number, got "{value}".') from None


def _coerce_boolean(param: ParamSpec, value: str) -> bool:
    if _TRUTHY_RE.match(value):
        return True
    if _FALSY_RE.match(value):
        return False
    raise ValueError(f'Param "{param.name}" must be true|false, got "{value}".')


def _coerce_json(param: ParamSpec, value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise ValueError(f'Param "{param.name}" must be valid JSON.') from None


def coerce_one(param: ParamSpec, value: str) -> Any:
    if param.kind is ParamKind.NUMBER:
        return _coerce_number(param, value)
    if param.kind is ParamKind.BOOLEAN:
        return _coerce_boolean(param, value)
    if param.kind is ParamKind.JSON:
        return _coerce_json(param, value)
    return value


def coerce(fn: FnSpec, raw: Sequence[str]) -> list[Any]:
    """Positional strings → typed args, one slot per declared param (``None`` for
    omitted optionals)."""
    required = sum(1 for param in fn.params if param.required)
    if len(raw) < required:
        raise ValueError(
            f'"{fn.name}" needs {required} param(s); got {len(raw)}. See: help {fn.name}'
        )
    return [
        coerce_one(param, raw[i]) if i < len(raw) else None for i, param in enumerate(fn.params)
    ]


def signature(fn: FnSpec) -> str:
    parts = [f"<{param.name}>" if param.required else f"[{param.name}]" for param in fn.params]
    return " ".join([fn.name, *parts])


def print_help() -> None:
    print("Usage: run.sh [--pii] <function_name> [params...]\n")
    print("       run.sh help                   list all functions")
    print("       run.sh help <function_name>   show a function's params\n")
    print(f"Config comes from {DOTENV_FILE} ({ENV_AUTH_TOKEN}, {ENV_GATEWAY_KEY}, {ENV_APP_ID},")
    print(f"{ENV_BASE_URL} or {ENV_API_URL}). {ENV_FULL_CUSTOMER_ACCESS}=1 (or the {PII_FLAG}")
    print(f"flag) enables PII-gated calls (marked [PII]). If {ENV_AUTH_TOKEN} is unset")
    print("you are prompted for the token at call time.\n")
    group = ""
    for fn in REGISTRY:
        if fn.group != group:
            group = fn.group
            print(f"\n{group}")
        tag = " [PII]" if fn.pii else ""
        print(f"  {signature(fn).ljust(SIGNATURE_COLUMN_WIDTH)} {fn.desc}{tag}")


def print_fn_help(name: str) -> int:
    fn = BY_NAME.get(name)
    if fn is None:
        print(f'Unknown function "{name}". Run: help', file=sys.stderr)
        return 1
    print(f"{signature(fn)}\n")
    pii = f"  [PII — needs {ENV_FULL_CUSTOMER_ACCESS}=1 or {PII_FLAG}]" if fn.pii else ""
    print(f"  {fn.desc}{pii}\n")
    if not fn.params:
        print("  No parameters.")
        return 0
    print("  Parameters:")
    for param in fn.params:
        req = "required" if param.required else "optional"
        print(f"    {param.name} ({param.kind.value}, {req}) — {param.desc}")
    return 0


# ─── Output ──────────────────────────────────────────────────────────────────


def to_jsonable(value: Any) -> Any:
    """Dataclasses (and lists of them) → plain dicts for ``json.dumps``."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


def dump_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), indent=JSON_INDENT, default=str, ensure_ascii=False)


def describe_error(err: BaseException) -> dict[str, Any]:
    """Renders a raised error into a readable, structured object."""
    out: dict[str, Any] = {"name": type(err).__name__, "message": str(err)}
    for key in _ERROR_DETAIL_ATTRS:
        value = getattr(err, key, None)
        if value is not None:
            out[key] = value
    return out


# ─── Entry ───────────────────────────────────────────────────────────────────


async def run_call(fn: FnSpec, args: Sequence[Any], *, full_customer_access: bool) -> Any:
    """Resolves the token, wires the services, runs the call, and closes the client."""
    ctx = build_context(resolve_auth_token(), full_customer_access=full_customer_access)
    try:
        return await fn.run(ctx, args)
    finally:
        await ctx.aclose()


def main(argv: Sequence[str]) -> int:
    load_dotenv()
    args = list(argv)
    pii_flag = PII_FLAG in args
    if pii_flag:
        args.remove(PII_FLAG)

    if not args or args[0] == HELP_COMMAND:
        if len(args) > 1 and args[0] == HELP_COMMAND:
            return print_fn_help(args[1])
        print_help()
        return 0

    fn_name, *rest = args
    fn = BY_NAME.get(fn_name)
    if fn is None:
        print(f'Unknown function "{fn_name}". Run: help', file=sys.stderr)
        return 1

    full_customer_access = pii_flag or _is_truthy(_env(ENV_FULL_CUSTOMER_ACCESS))
    try:
        # Coerce args first so bad input fails fast without prompting for a token.
        call_args = coerce(fn, rest)
        result = asyncio.run(run_call(fn, call_args, full_customer_access=full_customer_access))
    except Exception as err:  # the CLI boundary renders every failure as JSON
        print(dump_json(describe_error(err)), file=sys.stderr)
        return 1
    print(dump_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
