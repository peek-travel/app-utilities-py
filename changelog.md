# Changelog

Consumer-facing changelog for `peek-app-utilities`. It records only changes a
**caller** can observe or needs to act on — new capabilities, behavior changes,
and breaking changes — grouped by version, newest first. Internal refactors,
test-only changes, and invisible cleanups are intentionally omitted.

Each entry states **what** changed, **why**, and — when relevant — the **caller
action** required. Entries tagged `[breaking]` change observable behavior an
existing consumer could depend on; `[fix]` corrects broken behavior with no
action needed; `[additive]` only adds capability.

This package versions **in lockstep with `@peektravel/app-utilities`**: a
release here carries the same version number as the TypeScript release it
mirrors. For the history of how the shared surface evolved before the port,
see the TypeScript package's `changelog.md`.

---

## 1.3.0

### `BookingService.create` accepts a `promo_code` `[additive]`

- **What:** `CreateBookingInput` gains an optional `promo_code: str | None`.
  When set to a non-empty string (surrounding whitespace is trimmed), the
  booking's `createQuoteV2` quote carries it as an enabled promo code
  (`promoCodes: [{ code, refid, isEnabled: true }]`, with a freshly generated
  `refid`); the API validates and prices it. An empty/whitespace-only value or
  `None`/omitted sends no promo code, so existing callers are unaffected.
- **Why:** callers need to apply a discount code at booking time without
  dropping to raw GraphQL.
- **Caller action:** none to keep current behavior. To apply a code, pass
  `promo_code`. It **cannot** be combined with `parent_order_id` — attaching to
  an existing order takes the amendment path, which creates no new quote, so
  `create` raises `ValueError` rather than silently dropping the code; apply the
  promo to the parent order separately in that case.

### `parse_install_webhook` now rejects a non-Peek `api_url` `[breaking]`

- **What:** when an install/update webhook body carries a non-empty `api.url`,
  `parse_install_webhook` now validates that its host is a Peek-owned domain —
  `peek.com` (production) or `peeklabs.com` (sandbox), or a subdomain of either.
  A foreign or unparseable host raises `InstallWebhookError` with the new
  `reason="invalid_api_url"` (a new member of the `InstallWebhookErrorReason`
  `Literal`); a value delivered without a scheme is treated as `https`. An
  absent/empty `api_url` is unaffected and still parses. Nothing else about the
  parser changes.
- **Why:** the `api_url` is the endpoint the app points its API calls at, so a
  spoofed webhook with an attacker-controlled `api_url` could redirect those
  calls to a foreign gateway. Pinning the host to Peek-owned domains closes that.
- **Caller action:** none for genuine Peek deliveries. If you branch on
  `InstallWebhookError.reason`, note the added `"invalid_api_url"` case; the
  existing `except jwt.InvalidTokenError` → `401` handling (which
  `InstallWebhookError` subclasses) already covers it with no change.

---

## 1.2.1

### `SeatmapService.get_seatmap_ids_for_product` added `[additive]`

- **What:** new `get_seatmap_ids_for_product(product_id)` on `SeatmapService`
  returns the `id` and `name` of every seating map assigned to a product as
  `list[SeatmapSummary]` (a new exported model) — a lightweight alternative to
  `get_seatmap_for_product` that omits the zone/section/seat layout.
- **Why:** callers that only need to list a product's maps (e.g. to pick one)
  had to fetch and discard the full layout payload.
- **Caller action:** none — purely additive. Like the full read it is structural
  layout, not customer data, so it is unaffected by `full_customer_access`.

---

## 1.2.0

### `AvailabilityTime.minimumTicketsRequired` removed upstream — never present here

- **What:** the TypeScript package removed the `minimumTicketsRequired` field it
  had added to `AvailabilityTime` in 1.0.1 (the value did not mean what callers
  assumed — the smallest bookable party size — so it was better omitted than
  surfaced with the wrong semantics). The Python port moved from 0.9.4 straight
  to this surface, so `AvailabilityTime` here **never carried**
  `minimum_tickets_required` and nothing is removed.
- **Caller action:** none. If you need a minimum party size, do not look for
  this field — it was not a reliable source.

### `BookingService.create` with `parent_order_id` now attaches to the order `[fix]`

- **What:** passing `parent_order_id` to `create()` now adds the new booking to
  that existing order instead of silently creating a brand-new one. The returned
  `CreatedBooking.order_id` equals the `parent_order_id` you passed, and
  `booking_id`/`display_id`/`balance_*` describe the newly added booking. When
  `mark_as_paid` is set it charges that new booking's own balance (not the order
  total, which now includes the pre-existing bookings).
- **Why:** the old implementation mapped `parent_order_id` to a quote
  `clonedFromId` and still called `createOrderFromQuote`, which always mints a
  new order — so the booking was never attached and the call reported success
  against the wrong order. Attaching now goes through the amendment path
  (`createQuoteFromOrder` → `updateQuoteV2` → `amendOrder`).
- **Caller action:** none to adopt the fix. If you relied on the previous
  (broken) behavior of getting a separate new order, omit `parent_order_id` to
  keep creating the booking in its own order.

---

## 1.1.3

### `AssignableBooking.notes` — operator notes on assignable bookings `[additive]`

- **What:** `AssignableBooking` (returned by `SeatmapService.assignable_bookings`)
  gains a `notes: str` field carrying the booking's operator-facing notes — an
  empty string when the booking has none.
- **Why:** callers reconciling seat assignments need the same operator notes
  they see elsewhere, without a second booking lookup.
- **Caller action:** none — purely additive. The field is not PII-gated, so it
  is populated regardless of `full_customer_access`.

---

## 1.1.2

### `SeatmapZone.color_hex` — zone display color `[additive]`

- **What:** `SeatmapZone` gains a nullable `color_hex: str | None` field — the
  zone's display color as a hex string (e.g. `"#ff0000"`), or `None` when Peek
  reports none. It is populated on both `get_seatmap_for_product` and
  `get_seat_map_assignments` results.
- **Why:** callers rendering a seating map need the zone color to match Peek Pro.
- **Caller action:** none — purely additive.

---

## 1.1.1

### `SeatmapService.delete_seat_assignments` — delete seat assignments `[additive]`

- **What:** `SeatmapService` gains
  `delete_seat_assignments(assignment_ids: Sequence[str]) -> list[DeletedSeatAssignment]`
  — deletes seat assignments by id and returns the now-deleted assignments (for
  reloading state). New exported model `DeletedSeatAssignment` and typed error
  `SeatmapDeleteError`.
- **Why:** the write that clears seats, pairing with the assignment reads/writes.
- **Caller action:** none — purely additive. Notes for adopters: every id must
  start with `asa_` and at least one must be supplied (validated before any
  network call — raises `ValueError`); on success you get back the deleted
  assignments (`assignment_id`, `block_id`, `block_name`, `ticket_hash_id`); a
  batch-level failure from the API raises `SeatmapDeleteError` (reason on the
  message), while transport/GraphQL errors raise as usual.

### `SeatmapService.assign_tickets_to_seats` — bulk seat assignment `[additive]`

- **What:** `SeatmapService` gains
  `assign_tickets_to_seats(assignments: Sequence[SeatmapBlockAssignment]) -> AssignmentResponse`
  — assigns bookable tickets to seats in bulk (one batched mutation). New
  exported types `SeatmapBlockAssignment`, `AssignmentResponse`,
  `SuccessfulAssignment`, the `AssignmentStatus` `Literal`, and the
  `ASSIGNMENT_STATUSES` constant.
- **Why:** callers need to commit seat assignments (the write that pairs with
  the `assignable_bookings` / `get_seat_map_assignments` reads), in one round
  trip.
- **Caller action:** none — purely additive. Notes for adopters: each
  `SeatmapBlockAssignment` must carry an `assignable_id` starting with `t_` and
  a `block_id` starting with `csb_`, and at least one must be supplied — all
  validated before any network call (raises `ValueError`). The result's
  `status` is `"SUCCESS"` (all assigned), `"FAILED"` (none), or `"PARTIAL"`
  (some). `successful_assignments` are `(assignable_id, assignment_id)` pairs
  (the created `asa_…` record); `failed_assignments` lists the failed
  `assignable_id`s. **Per-assignment** failures (overbooking, invalid type, …)
  are reported in `failed_assignments`, not raised; only transport/GraphQL-level
  errors raise.

### `SeatmapService.assignable_bookings` — bookings assignable to seats `[additive]`

- **What:** `SeatmapService` gains
  `assignable_bookings(product_id, range_start, range_end) -> list[AssignableBooking]`
  — the confirmed bookings on a product that overlap a datetime range, each with
  the tickets that can be assigned to seats. New exported types
  `AssignableBooking`, `AssignableTicket`, and `CurrentSeatAssignment`.
- **Why:** seat assignment needs the list of bookings/tickets eligible for a map
  and time window, plus which seat (if any) each ticket already holds.
- **Caller action:** none — purely additive. Notes for adopters: `assignable_id`
  on a ticket is its `hashid` (the handle you assign by); `currently_assigned_to`
  is `None` when a ticket has no seat yet; `range_start`/`range_end` take the
  same flexible datetimes as `get_seat_map_assignments` (seconds optional,
  timezone/fractional stripped, both bounds on the same date) sent half-open
  `[start, end)`; booking `starts_at`/`ends_at` are returned without fractional
  seconds; and `guest_name` is **customer PII**, so it is `None` unless the
  access service was created with `full_customer_access`.

### `SeatmapService.get_seat_map_assignments` — seat occupancy over a range `[additive]`

- **What:** `SeatmapService` gains
  `get_seat_map_assignments(product_id, range_start, range_end) -> list[AssignedSeatmap]`
  — every seating map on an activity with each seat enriched by its occupancy
  over a datetime range. New exported types: `AssignedSeatmap`,
  `AssignedSeatmapSection`, `AssignedSeatmapGroup`, and `AssignedSeatmapBlock`
  (`AssignedSeatmapBlock` extends `SeatmapBlock` and adds
  `status: SeatmapBlockStatus` and `assigned_to: list[SeatmapAssignment]`; the
  other three mirror their `Seatmap*` counterparts with the enriched child
  collections), plus `SeatmapAssignment`, the `SeatmapBlockStatus` /
  `SeatmapOccupantType` `Literal`s, the `SEATMAP_BLOCK_STATUSES` /
  `SEATMAP_OCCUPANT_TYPES` constants, and two typed errors
  `UnknownSeatmapBlockStatusError` and `UnknownSeatmapAssignmentParentError`.
- **Why:** callers need who/what occupies each seat (bookings/guests, staff,
  field locations, blocked seats) for a given map and time window — not just the
  static layout `get_seatmap_for_product` returns.
- **Caller action:** none — purely additive; `get_seatmap_for_product` is
  unchanged and still returns the base `list[Seatmap]` without
  `status`/`assigned_to`. When adopting the new call, note: it takes the
  **product id** and returns every map on that activity (like
  `get_seatmap_for_product`), empty when there are none;
  `range_start`/`range_end` accept flexible datetimes (seconds optional, any
  timezone/fractional seconds stripped) normalized to naive
  `YYYY-MM-DDTHH:MM:SS` and queried half-open `[start, end)` — and the two
  bounds must fall on the same date (it raises `ValueError` otherwise); an
  occupant's `guest_name` is **customer PII**, so for a `"GUEST"` it is `None`
  unless the access service was created with `full_customer_access`
  (staff/`"ACCOUNT_USER"` names are not gated); and an unrecognized seat status
  or assignment parent raises the matching new error (`.status` / `.typename`
  carry the offending value).

### New `SeatmapService` for reading product seating maps `[additive]`

- **What:** `PeekAccessService.get_seatmap_service()` returns a new
  `SeatmapService` with `get_seatmap_for_product(product_id) -> list[Seatmap]`
  — every seating map configured on an activity (empty when the activity is
  missing or has none). The clean models `Seatmap`, `SeatmapZone`,
  `SeatmapTicket`, `SeatmapSection`, `SeatmapGroup`, `SeatmapBlock`, and the
  shared `SeatmapDisplay` geometry are now exported, along with the
  `SeatmapDisplayType` `Literal`, the `SEATMAP_DISPLAY_TYPES` constant, and a
  new typed error `UnknownSeatmapDisplayTypeError`.
- **Why:** callers need the physical seat layout (zones/pricing tiers, sections,
  tables, and seats) a product sells against, exposed as clean models instead of
  raw GraphQL.
- **Caller action:** none — purely additive. Note two behaviors when adopting
  it: a product can have multiple maps, so the result is a list; and a
  `display.type` outside `SEATMAP_DISPLAY_TYPES` (`"SHAPE" | "SECTION" |
  "LABEL"`) raises `UnknownSeatmapDisplayTypeError` (`.type` holds the offending
  value) — catch it if you need to tolerate a newly-added kind. Seating maps are
  structural layout, not customer data, so the call is unaffected by
  `full_customer_access`.

## 1.1.0

### `parse_install_webhook` takes `install_id` from the token `sub` `[fix]`

- **What:** `InstallWebhook.install_id` is now always the verified token `sub`.
  The body `install_id` no longer sets it. `parse_install_webhook` now raises
  the new exported `InstallWebhookError` in two cases: the body has a non-empty
  `install_id` that is not equal to the token `sub`
  (`reason="install_id_mismatch"`), or the token has no `sub`
  (`reason="missing_subject"`). A body without `install_id` still parses, with
  `install_id` set from `sub`. `InstallWebhookError` subclasses PyJWT's
  `jwt.InvalidTokenError` (and `AppUtilitiesError`), so code that branches on
  `jwt.InvalidTokenError` also catches it; the reason is a
  `InstallWebhookErrorReason` `Literal` on `.reason`. Before, the body
  `install_id` was used first and the token `sub` only filled in when the body
  had none.
- **Why:** the install id of the event is now the one the signed token states.
  Peek's own deliveries put the same id in both places, so they parse as before.
- **Caller action:** keep one `try`/`except jwt.InvalidTokenError` around
  `parse_install_webhook` and respond `401` for every raise (also
  `InstallWebhookError`). If your tests mint tokens, give each token a `sub`
  equal to the body `install_id`, or leave `install_id` out of the body.

---

## 1.0.1

### Shared `Money` model; `BookingAddonMoney` replaced `[breaking]`

- **What:** the money shape `(amount, currency, formatted)` is now exported as a
  single shared `Money` dataclass. `BookingAddon.total` is typed as
  `Money | None`. The previously-exported `BookingAddonMoney` is **removed** —
  unlike the TypeScript package, which keeps it as a `@deprecated` alias of
  `Money`, this port carries no compatibility shims (see `README.md`
  "Relationship to `@peektravel/app-utilities`").
- **Why:** the same money shape is now returned by more than one resource
  (booking add-ons and availability prices), so it lives in one place instead of
  a resource-specific type.
- **Caller action:** replace any `BookingAddonMoney` import or annotation with
  `Money`. The fields and values are identical.

### `AvailabilityTime` gains `price` `[additive]`

- **What:** each `AvailabilityTime` returned by
  `get_availability_service().get_availability_times(...)` now carries
  `price: Money | None` — the per-ticket price, when Peek reports one. (The
  TypeScript 1.0.1 release also added `minimumTicketsRequired`; it was removed
  again in 1.2.0 and was never added to the Python port.)
- **Why:** callers choosing a slot need the per-ticket price alongside the
  remaining availability.
- **Caller action:** none — additive.

## 1.0.0

### `PeekAccessServiceConfig.mode` is now a required `"v1" | "v2"` field `[breaking]`

- **What:** `mode` on `PeekAccessServiceConfig` was an optional
  `GatewayMode | None` field (omitting it meant the legacy `"v1"` route). It is
  now a **required** `GatewayMode` (`Literal["v1", "v2"]`) field with no
  default: omitting it fails dataclass construction (`TypeError`), and the
  `PeekAccessService` constructor raises `ValueError` (`"mode" is required …`)
  for any value other than `"v1"`/`"v2"` — so a caller gets a loud error instead
  of silently running on v1. `"v2"` is the app-registry connection to use going
  forward and now **requires** the install webhook's `api_url` — the
  constructor raises `ValueError` if `"v2"` is selected without one (there is no
  silent default base URL). `"v1"` is the legacy gateway and is now
  **deprecated** and will be removed. If you don't yet have a webhook `api_url`,
  build one by appending your app slug to the registry prefix and pass that as
  the `api_url` yourself — `https://apps.peek.com/installations-api/<app-slug>`
  (the trailing app-slug segment is required — the prefix alone is not a valid
  `api_url`; the old `app-registry.peeklabs.com` sandbox host is gone).
- **Why:** v2 (the per-install `api_url` from the install webhook) is the
  forward-looking connection, and we want every consumer to move to it. Making
  `mode` mandatory turns a silent default into a deliberate, visible choice at
  update time rather than a behaviour that can drift unnoticed.
- **Caller action:** pass `mode` explicitly.
  - If you relied on the previous default, the fastest no-behaviour-change
    update is to add `mode="v1"` (keep your existing `app_id` + `gateway_key`).
    Then plan the migration to v2.
  - For v2, pass `mode="v2"` and the install's `api_url` (persisted from the
    install webhook; see `docs/webhooks.md`). `create_access_service_for_install`
    already sets `mode="v2"` for you, so callers using the install factory need
    no change. CNG/ACME configs are unaffected (they have no `mode`).

## 0.9.5

### New `CustomQuestionService` with account-wide `get_all()` `[additive]`

- **What:** a new `CustomQuestionService`, obtained via
  `PeekAccessService.get_custom_question_service()`, exposes `get_all()` —
  returning every custom question defined on the account (across all
  activities) as a `list[CustomQuestion]`, the same clean model as
  `get_product_service().get_custom_questions(product_id)`. Because the
  account-wide catalog carries no per-activity configuration, `order` is `0`
  and `is_required` is `False` on every entry. These are question definitions,
  not customer answers — no PII, so the result is unaffected by
  `full_customer_access`.
- **Why:** callers need the full catalog of custom questions for an account, not
  just those configured on a single activity.
- **Caller action:** none — additive. Reach the new read via
  `peek.get_custom_question_service().get_all()`.

## 0.9.4

### Initial Python port of `@peektravel/app-utilities` 0.9.4 `[additive]`

- **What:** first release of `peek-app-utilities` (import name
  `peek_app_utilities`), a port of `@peektravel/app-utilities` 0.9.4 with the
  same resources, models, and behaviour. Included:
  - **Peek:** `PeekAccessService` + `PeekAccessServiceConfig` with every
    resource service — `ProductService`, `AccountUserService`,
    `ResourcePoolService`, `TimeslotService`, `ResellerService`,
    `PromoCodeService`, `PricingService`, `DailyNoteService`,
    `AvailabilityService`, `MembershipService`, `BookingService` (reads,
    guests, metadata read + the eight `set_meta_data_*` setters, payments,
    notes, check-in, custom status, cancel, add-ons, create), and
    `ReviewService` — plus `verify_peek_auth_token`.
  - **CNG / ACME:** `CngAccessService` and `AcmeAccessService` with their
    product services, models (`Activity`/`ActivityTicket`,
    `AcmeActivity`/`AcmeActivityTicket`), and errors (`CngApiError`,
    `CngPermissionError`, `AcmeApiError`), and the
    `create_access_service_for_install` factory (`InstallAccessConfig`,
    `InstallAccessTarget`, `InstallAccessService`).
  - **Models:** every clean data model as a frozen, keyword-only dataclass
    (bookings, add-ons, metadata, payments, products, custom questions,
    timeslots, resource pools, account users, availability, channels, daily
    notes, memberships, promo codes, pricing, reviews, auth-token claims,
    install, waiver) with the TypeScript field names in `snake_case`.
  - **Webhooks:** `parse_booking_webhook`, `parse_waiver_webhook`, and
    `parse_install_webhook`, with the same booking registration query
    (documented in `docs/webhooks.md`) and the same `full_customer_access`
    semantics (`AccessOptions`, `PiiAccessDisabledError`).
- **Python-specific surface** (the places the port is not a literal
  transliteration):
  - **Async-only.** Every method that touches the network is `async def`;
    there is no synchronous API.
  - **Frozen dataclasses.** Inputs and outputs are
    `@dataclass(frozen=True, slots=True, kw_only=True)`; construct inputs with
    keyword arguments (`CreateBookingInput(activity_id=..., ...)`) and read
    results by attribute. `null` is `None`.
  - **HTTP client injection + lifecycle.** The access services take an optional
    `http_client: httpx.AsyncClient` (replacing the TypeScript `fetch`
    option). Without one they own a client, closed by `await aclose()` or the
    async context manager (`async with PeekAccessService(...) as peek:`); a
    caller-supplied client is never closed.
  - **Logging.** `Logger` is a protocol; `logging_adapter(logging.Logger)`
    bridges to the standard library (context goes out as
    `extra={"context": {...}}`). `noop_logger` is the silent default.
  - **Errors.** Every package error derives from the new `AppUtilitiesError`
    base, so `except AppUtilitiesError` catches anything the package raises on
    its own. Validation/precondition failures raise `ValueError` (where
    TypeScript throws a plain `Error`), keeping the same messages.
    `PiiAccessDisabledError.operation` is the snake_case method name.
  - **Token verification** (`verify_peek_auth_token`, `parse_install_webhook`)
    raises PyJWT's `jwt.InvalidTokenError` subclasses (`ExpiredSignatureError`,
    `InvalidSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`,
    `DecodeError`, …) instead of `jsonwebtoken` errors.
  - **Waiver redaction** without `full_customer_access` sets `guest_name` to
    `None` and `file_url` to `""`.
  - The outbound SDK header is `x-peek-sdk: py-<version>`.
- **Deliberately not carried over** from the TypeScript package:
  - the `@deprecated` top-level short-form proxies on the access services
    (`peek.getAllProducts()`, `peek.createPricingEngine()`, …) — use the
    `get_<resource>_service()` accessors;
  - the `@deprecated` `verifyInstallWebhook` (and its `InstallWebhookClaims` /
    `InstallWebhookAccount` types) — use `parse_install_webhook`;
  - the `AddAddonInput.addonId` alias — `AddAddonInput` takes `addon_option_id`
    only;
  - the browser UI components (`@peektravel/app-utilities/ui`) — they remain in
    the TypeScript package.
- **Caller action:** none — new package. Install with
  `pip install peek-app-utilities` (Python ≥ 3.11).
