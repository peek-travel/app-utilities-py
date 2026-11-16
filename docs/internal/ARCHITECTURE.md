# Architecture — `peek-app-utilities`

A small, dependency-light **async** Python library that wraps the Peek
"backoffice" GraphQL API. It hides the raw GraphQL queries, authentication, HTTP
transport, retry logic, and response shapes behind a single authenticated entry
point (`PeekAccessService`) that hands out per-resource services returning clean,
frozen dataclass models.

Consumers never see GraphQL. They construct one access service per install and
`await` typed methods on the per-resource services, e.g.
`await peek.get_product_service().get_all_products()`.

The package also ships **sibling accessors for other backoffices** —
`CngAccessService` and `AcmeAccessService` (both REST, not GraphQL). They reuse
this package's auth (`TokenManager`), retry/backoff loop, `Logger`, base error
types, and tooling — differing only in transport (REST vs GraphQL) and routing
(`cng_backoffice_api-v1` / `acme_backoffice_api-v1` vs `peek_backoffice_api-v1`).
See "CNG accessor" and "ACME accessor" below.

## Relationship to the TypeScript package

This is the Python port of `@peektravel/app-utilities` (repo
`peek-travel/app-utilities`). The two packages ship **the same version number**
(`pyproject.toml` ↔ `package.json`), the same resources, the same models, and
the same behaviour; a change that lands in one is ported to the other. The
mechanical TypeScript → Python mapping (file layout, naming, type mapping, async
rules, test fakes, and the deprecated TypeScript surface that was deliberately
**not** ported) lives in [`CONVENTIONS.md`](./CONVENTIONS.md) — read it before
porting anything. In short: `camelCase` → `snake_case` for methods and fields,
class names unchanged, `interface` → frozen keyword-only `@dataclass`,
`null`/`undefined` → `None`, `Promise` → `async def`, `jsonwebtoken` → `PyJWT`,
`fetch` → `httpx`.

## Layers

```
                consumer code
                      │
                      ▼
            ┌──────────────────────┐
            │  PeekAccessService   │  public root; validates config,
            │  (peek_access_       │  wires transport + token manager,
            │   service.py)        │  lazily memoizes resource services,
            └──────────┬───────────┘  owns (or borrows) the httpx client
                       │ owns
        ┌──────────────┼───────────────────────────┐
        ▼              ▼                             ▼
 ┌─────────────┐ ┌──────────────┐         ┌────────────────────────┐
 │ TokenManager│ │ GraphQLClient│◄────────│ per-resource services  │
 │ mints/caches│ │ httpx+retry+ │  shared │ (products, bookings,   │
 │ the JWT     │ │ error mapping│  client │ timeslots, …)          │
 └─────────────┘ └──────┬───────┘         └───────────┬────────────┘
                        │                             │ uses
                        ▼                             ▼
                 Peek backoffice API       ┌──────────────────────────┐
                                           │ queries  + converters    │
                                           │ (raw nodes → dataclasses)│
                                           └──────────────────────────┘
```

Package root: `src/peek_app_utilities/`. Paths below are relative to it.

### 1. `PeekAccessService` — the authenticated root
`peek_access_service.py`

- Takes one `PeekAccessServiceConfig` (a frozen dataclass extending the shared
  `BaseAccessServiceConfig` from `access_service_config.py` with
  `gateway_key` / `mode` / `item_options_page_size`).
- Validates the config and raises `ValueError`: `mode` must be `"v1"` or
  `"v2"` (`ERROR_MODE_REQUIRED` — it is a required dataclass field with no
  default, so omitting it already fails at `PeekAccessServiceConfig(...)` with a
  `TypeError`); `install_id`, `jwt_secret`, `issuer` must be non-empty always;
  `"v2"` must carry an `api_url` (`ERROR_V2_API_URL_REQUIRED`); and `app_id` +
  `gateway_key` must be non-empty only in `"v1"` **without** an `api_url` (both
  are unneeded when `api_url` is set — see the endpoint-URL note below).
- Constructs a single shared `TokenManager` and `GraphQLClient`.
- Exposes one `get_<resource>_service()` accessor per resource. Each is **lazily
  created and memoized** — repeated calls return the same instance.
- **No short-form proxies.** The TypeScript package historically exposed
  top-level methods such as `peek.getAllProducts()` that delegate to the
  underlying service; they are `@deprecated` there and were **deliberately not
  ported** (this package has no legacy consumers). Callers reach a resource
  method only through its accessor. Do not add any.
- Exposes `verify_peek_auth_token(token)` to verify HMAC-signed JWTs issued by
  the Peek app registry (`iss: "app_registry_v2"`, `aud: "Joken"`), returning a
  fully typed `PeekAuthTokenClaims` (including the nested, nullable
  `PeekAuthTokenUser`). Raises PyJWT's `jwt.InvalidTokenError` subclasses
  (`ExpiredSignatureError`, `InvalidSignatureError`, `InvalidIssuerError`,
  `InvalidAudienceError`, `ImmatureSignatureError`, `DecodeError`) on failure.
  Claim *extraction* is defensive and never raises: the shared
  `map_peek_token_user` returns `None` for an absent `user` block and
  normalizes every field independently (a sentinel `""`/`"null"` becomes
  `None`). The signature-check core (issuer + audience + user mapping) lives in
  the internal `internal/peek/peek_auth_token.py` module, shared with
  `parse_install_webhook` (§ install webhooks) so the two can't drift apart.
  That core (`verify_peek_jwt`) also strips a leading `Bearer ` prefix from the
  token, so every entry point in the family accepts the raw `x-peek-auth`
  header value.
- **Lifecycle.** The access service holds an `OwnedHttpClient`
  (`internal/rest_access.py`): when the config supplies no `http_client` it
  creates its own `httpx.AsyncClient` (30 s timeout, `create_http_client` in
  `access_service_config.py`) and closes it on `aclose()`; a caller-supplied
  client is used as-is and never closed. `__aenter__`/`__aexit__` make
  `async with PeekAccessService(...) as peek:` the idiomatic form. CNG and ACME
  share the exact same lifecycle.
- Composes dependencies between services where needed:
  - `TimeslotService` receives the resource-pool and account-user services (for
    guide resolution).
  - `BookingService` receives the product service (for add-on → parent-item
    resolution, custom-question validation, and list-price currency lookup).
- Required config beyond the base fields: `mode` (`GatewayMode =
  Literal["v1", "v2"]` — see below). Optional config: `api_url` (see the
  endpoint-URL note below; required with `"v2"`), `base_url`, `token_ttl_seconds` (3600),
  `token_refresh_leeway_seconds` (60), `retry_delays_ms` (`(1000, 2000, 4000)`),
  `logger` (no-op default), `http_client` (package-owned default),
  `item_options_page_size` (50), and `access_options` (see "Access options /
  PII" below).
- **Base API URL + per-service slug.** Every request URL is
  `base_api_url / <slug> [ / <path> ]`, where the **base API URL** is the
  install's app endpoint with no routing segment and the **slug** is chosen *per
  service / per endpoint* from that platform's endpoint lookup (`ApiEndpoints`,
  in `internal/api_endpoints.py`). Two services on one platform can therefore
  route through different slugs — a new API is one more entry in the lookup
  (`peek_api_endpoints` in `internal/peek/gateway_endpoints.py`;
  `CNG_API_ENDPOINTS` / `ACME_API_ENDPOINTS` in each `endpoints.py`). The
  clients hold only `{ base_api_url, endpoints }` and build the URL via
  `join_url`, so an empty slug collapses cleanly to `base_api_url / <path>`.
- **Resolving the base — `api_url` (preferred) vs. `base_url`/`app_id` (deprecated).**
  When the config carries `api_url`, the access-service constructor runs it
  through the shared `resolve_base_api_url(api_url, platform_slug, service_name)`
  helper (`access_service_config.py`) to recover the base: it **returns the URL
  as-is** when no slug is present, **strips this platform's slug** back off when
  the URL already ends in one (dashes and underscores interchangeable, so both
  `peek_backoffice_api-v1` and `peek-backoffice-api-v1` match), and **raises
  `ValueError`** when it ends in a *different* platform's slug (a wiring
  mistake). When `api_url` is absent the base is `base_url/app_id` (the
  deprecated default construction, with a hardcoded default `base_url`) — the
  fallback will be removed and a URL will become required. Either way, no app-id
  segment is inserted beyond the base, so `app_id` is unused with `api_url` (and
  `gateway_key` isn't required — the registry endpoint authenticates on the JWT,
  like v2). `create_access_service_for_install` (§ below) is the front door for
  the `api_url` path.
- **Peek registry (`"v2"`) vs. legacy (`"v1"`).** `mode` is a **required**
  `GatewayMode` (`Literal["v1", "v2"]`, defined in `access_service_config.py`)
  field on `PeekAccessServiceConfig` (it used to be `GatewayMode | None` and
  default to v1; it is now mandatory, with a constructor guard that raises
  `ValueError` on any other value so a caller gets a loud, actionable error).
  `"v2"` routes the `sales` endpoint through the `peek_backoffice_api-v1` slug,
  so the GraphQL POST hits `<base>/peek_backoffice_api-v1` (no trailing `sales`
  segment); it **requires** the install's `api_url` (the constructor raises
  without it — there is no silent default). `V2_FALLBACK_URL_PREFIX`
  (`https://apps.peek.com/installations-api`, in `peek_access_service.py`) is not
  applied automatically and is **not a complete URL** — it is only the
  documented prefix a developer appends their **app slug** to
  (`<prefix>/<app-slug>`, the same shape as the webhook's `api.url`) and passes
  as `api_url` when they lack a webhook URL; the error message quotes it. `"v1"`
  (**deprecated, will be removed**) is the legacy backoffice-GraphQL gateway: no
  extendable slug, so `sales` sits directly under the base
  (`<base_url>/<app_id>/sales`), the default `base_url` (`DEFAULT_BASE_URL`) is
  the backoffice-GraphQL gateway, and `gateway_key` is required. An app-endpoint
  `api_url` on `"v1"` also routes through the slug and, when set, supersedes
  `base_url` entirely (the slug choice is `use_registry_slug = bool(api_url)`).
  All other behaviour (JWT auth, headers, retries, resource services) is
  unchanged.

### 1b. `create_access_service_for_install` — the install factory
`access_service_factory.py`

Turns a persisted install (or the parsed `InstallWebhook` itself) into the right
access service for its platform. `InstallAccessTarget` is a `runtime_checkable`
`Protocol` (`platform`, `api_url`, `install_id` properties) so any record shaped
like the webhook qualifies. `InstallAccessConfig` is the per-app credential/option
set (everything in `PeekAccessServiceConfig` except the per-install
`install_id`/`api_url`, the deprecated URL controls, and `mode`); the factory
splats it into `PeekAccessServiceConfig` for `"peek"` **injecting the required
`mode="v2"`** (a persisted install with an `api_url` is always the registry
connection), and drops the Peek-only
`gateway_key`/`item_options_page_size` before building a `BaseAccessServiceConfig`
for `"cng"`/`"acme"`. An unknown or `None` platform raises `ValueError`. The
return type is the `InstallAccessService` union alias.

### 2. `TokenManager` — auth
`internal/token_manager.py`

- Signs a short-lived HS256 JWT with PyJWT (`sub = install_id`, `iss = issuer`,
  `iat`/`exp` from `ttl_seconds`). Payload is otherwise empty.
- Caches the token and re-mints it once it is within `leeway_seconds` of expiry.
  Takes an injectable `clock` for tests.

### 3. `GraphQLClient` — transport
`internal/peek/graphql_client.py`

The place that touches the network for Peek, built on `httpx.AsyncClient`. The
retry/backoff loop and 418/429 mapping are **shared** with the CNG/ACME
transport in `internal/http_transport.py` (`request_with_retry`): both clients
build their own URL/headers/body, log their own "Making … request" line, and
pass a per-response `on_response` coroutine that handles the transport-specific
success/error parsing. Responsibilities:

- Builds the endpoint URL as `join_url(base_api_url, endpoints.path_for(endpoint_name))`.
  Today every operation routes through the single `sales` endpoint
  (`gateway_endpoints.py`), whose slug is `peek_backoffice_api-v1` in registry
  modes and empty (the `sales` segment itself) on the legacy v1 gateway.
- Sets headers: `X-Peek-Auth: Bearer <jwt>`, `pk-api-key: <gateway_key>` (only
  when configured), `Content-Type: application/json`, `x-peek-sdk: py-<version>`.
- Collapses query whitespace (`\s+` → single space) before sending.
- Retries HTTP 429 using the configured backoff delays (via an injectable async
  `sleep`), then raises `RateLimitError`.
- Reads the response body via the shared `parse_body` helper (`response.text` →
  try `json.loads`, falling back to raw text) *before* branching on status, so a
  non-JSON error page never raises a decode error that hides the real status.
- Maps known failures to typed errors:
  - HTTP 418 → `AdminAccountRequiredError`
  - HTTP 429 (after retries) → `RateLimitError`
  - GraphQL `errors` array present → `PeekGraphQLError` (raw errors preserved on
    `.graphql_errors`)
  - other non-2xx → `PeekHttpError` (carries `.status_code`, `.url`, and raw
    `.body`).

#### 3b. `x-peek-sdk` — SDK identification header
`internal/sdk_headers.py`

All three transports (Peek `GraphQLClient`, CNG and ACME `RestClient`) send
`x-peek-sdk: py-<version>` on every request so the downstream platforms can
attribute traffic to this package and its version (the TypeScript package sends
`js-<version>`). The module exports `SDK_HEADER_NAME`, `SDK_VERSION`, and the
precomputed `SDK_HEADER_VALUE`; it is internal and not re-exported from
`__init__.py`.

The version is a **static literal**, not an `importlib.metadata` lookup, so the
header is correct from a source checkout and costs nothing at import time.
`tests/test_sdk_headers.py` is a drift guard that asserts `SDK_VERSION` equals
`pyproject.toml`'s `project.version` — **bump both together**, and keep them
equal to the matching `@peektravel/app-utilities` release.

#### 3c. Errors
`errors.py`

Every error the package raises on its own derives from `AppUtilitiesError`
(`except AppUtilitiesError` catches them all; PyJWT errors from token
verification are the deliberate exception). `AdminAccountRequiredError` and
`RateLimitError` are shared by all platforms and carry a `status_code` class
attribute; `PeekGraphQLError`/`PeekHttpError` are Peek-only; `CngApiError` /
`CngPermissionError` CNG-only; `AcmeApiError` ACME-only; `PiiAccessDisabledError`
carries the blocked `operation` (snake_case method name). The seatmap errors
`UnknownSeatmapDisplayTypeError` (`.type`), `UnknownSeatmapBlockStatusError`
(`.status`), `UnknownSeatmapAssignmentParentError` (`.typename`), and
`SeatmapDeleteError` (the API message) live here too (§4 seatmaps).
`InstallWebhookError` is the one dual-parent error: it subclasses **both**
PyJWT's `jwt.InvalidTokenError` and `AppUtilitiesError`, so a receiver's
`except jwt.InvalidTokenError` → 401 covers it unchanged; `.reason` is an
`InstallWebhookErrorReason` `Literal` (`"install_id_mismatch"` /
`"missing_subject"` / `"invalid_api_url"`), with the three reason constants
(`INSTALL_WEBHOOK_*`) and their messages kept beside it. The status constants
(`FORBIDDEN_STATUS`, `ADMIN_ACCOUNT_REQUIRED_STATUS`, `RATE_LIMIT_STATUS`) live
here too so the transports import them rather than restating the numbers.

#### 3d. Logger
`logger.py`

`Logger` is a `runtime_checkable` `Protocol` (`info`/`warn`/`error`, each taking
a message plus an optional `Mapping[str, Any]` context). `noop_logger` is the
silent default; `logging_adapter(logging.Logger)` wraps a standard-library
logger, forwarding the context as `extra={"context": {...}}`. Tests use the
`RecordingLogger` fake from `tests/conftest.py`.

### 4. Per-resource services
`internal/peek/<resource>/`

Every Peek resource lives under `internal/peek/` (mirrored by the CNG/ACME
resources under `internal/cng/` and `internal/acme/` — see §5b/§5c); the shared
plumbing (`token_manager.py`, `http_transport.py`, `rest_client.py`,
`rest_access.py`, `api_endpoints.py`, `sdk_headers.py`) stays at `internal/`.

Each resource follows the same **three-file triad**:

| File | Role |
| --- | --- |
| `*_queries.py` | Raw GraphQL query/mutation strings (`Final` constants), the matching raw `TypedDict` response shapes, and small variable-builder/normalizer helpers. **Internal only** — never re-exported. |
| `*_converter.py` | Pure, I/O-free functions mapping raw nodes → clean dataclass models. Easy to unit-test. |
| `*_service.py` | Public `async` class holding the business logic; calls the shared client, then runs the converter. |

Resources: `products`, `custom_questions`, `account_users`, `resource_pools`,
`timeslots`, `resellers`, `promo_codes`, `pricing`, `daily_notes`,
`availability`, `memberships`, `bookings`, `reviews`, `seatmaps`, plus the
webhook-only `waivers` and `installs`. Clean data shapes are split by brand:
Peek models in `models/peek/`, CNG models in `models/cng/`, ACME models in
`models/acme/`. One small resource (`promo_codes`) folds its converter functions
into the `*_queries.py` module rather than a separate file; the purity rule
still applies to it.

Seating maps are their own resource triad under `internal/peek/seatmaps/` —
`seatmap_queries.py` (query/mutation strings, builders, and raw `TypedDict`
nodes, internal), the pure `seatmap_converter.py`, and `SeatmapService`
(`get_seatmap_service()`). `get_seatmap_for_product(product_id)` returns every
`Seatmap` configured on an activity (`list[Seatmap]`, empty when the activity is
missing or has none; `_seating_maps` lifts `data.activity.seatingMaps`); it is
unaffected by `full_customer_access` (seating maps are structural layout, not
customer data). A map carries `zones` (pricing tiers, each with a nullable
`color_hex` and mapping to `list[SeatmapTicket]`) and a tree of `SeatmapSection`
→ `SeatmapGroup` (tables) → `SeatmapBlock` (seats). All three rendered levels
share one `SeatmapDisplay` geometry dataclass: only `x`/`y` are always present,
and every other field (`width`/`height`/`label`/`type` on sections;
`table`/`table_width`/`table_height` on groups) collapses to `None` where the
API does not select it. `SeatmapDisplay.type` is narrowed to
`SeatmapDisplayType` (`Literal["SHAPE", "SECTION", "LABEL"]`, with the
`SEATMAP_DISPLAY_TYPES` tuple beside it); a non-`None` value outside that set
makes the converter raise the exported `UnknownSeatmapDisplayTypeError` rather
than silently widen the model. Every `product_id` is checked non-blank up front
(`ERROR_PRODUCT_ID_REQUIRED`, `ValueError`).

`get_seatmap_ids_for_product(product_id)` is the lightweight sibling of
`get_seatmap_for_product`: a trimmed query (`SEATMAP_IDS_QUERY`) selecting only
each map's `id`/`name` (no zones/sections/groups/blocks), mapped by the pure
`from_seatmap_summary_nodes` to `list[SeatmapSummary]` (empty when the activity
is missing or has none). Same validation and non-PII posture as the full read;
use it when a caller only needs to list the maps assigned to a product.

`get_seat_map_assignments(product_id, range_start, range_end)` reads a product's
maps through the same `activity(id).seatingMaps` entry as the plain read (the
API has no top-level `seatingMap(id)`), with every seat enriched by its
occupancy over a datetime range, returning `list[AssignedSeatmap]` (empty when
the activity is missing or has no maps). The query
(`build_seatmap_assignments_query(full_customer_access)`) selects the same
structural fields as the plain read plus each seat's
`availability(datetimeRange)`. The assignment-enriched tree is modeled with
`AssignedSeatmapBlock(SeatmapBlock)` — a dataclass subclass adding `status`
(`SeatmapBlockStatus`) and `assigned_to` (`list[SeatmapAssignment]`) — and
three parallel dataclasses `AssignedSeatmapGroup` / `AssignedSeatmapSection` /
`AssignedSeatmap` that mirror their base types with the narrowed child
collection (Python dataclasses cannot override a field's type on inheritance,
so the containers are restated rather than subclassed; keep their field lists
in step with the base types). An occupant's kind (`SeatmapOccupantType`) is
derived from the assignment parent's `__typename` (`Ticket`→`GUEST`,
`AccountUser`→`ACCOUNT_USER`, `FieldLocation`→`FIELD_LOCATION`; `BlockedSeat` is
not an occupant and drops out — the `PARENT_*` constants in the queries module
and `SEATMAP_ASSIGNMENT_PARENTS`); an unknown status or parent raises
`UnknownSeatmapBlockStatusError` / `UnknownSeatmapAssignmentParentError`.
`range_start`/`range_end` are normalized in the service
(`_normalize_naive_datetime`) to the API's naive `YYYY-MM-DDTHH:MM:SS` form
(seconds added when omitted, timezone and fractional seconds stripped,
components range-checked) and sent as a half-open `[start, end)` range literal;
the two bounds must fall on the same date (`ERROR_RANGE_SAME_DATE`,
`ValueError`). A guest's name is **customer PII**: `SeatmapService` takes the
`ResolvedAccessOptions` (threaded from `PeekAccessService` like
`BookingService`/`ReviewService`) and the query builder omits the
`primaryGuest { firstName lastName }` selection (`_primary_guest_selection`)
when it is off, so a GUEST occupant's `guest_name` is `None`; staff
(`AccountUser`) names are not gated. The plain `get_seatmap_for_product` read is
unaffected — it returns the base `SeatmapBlock` without `status`/`assigned_to`.

`assignable_bookings(product_id, range_start, range_end)` reads the confirmed
bookings on a product that overlap a range (via `bookings(filter: {
activityIds, overlapsRange, reservationStatuses: [CONFIRMED] })`,
`build_assignable_bookings_query(full_customer_access)`), returning
`list[AssignableBooking]` — each with `assignable_tickets` (`AssignableTicket`,
keyed by the ticket `hashid` as `assignable_id`) and, per ticket, the seat it
currently holds (`CurrentSeatAssignment`, `None` when unassigned — the
assignable case). Range bounds are parsed and validated by the same shared
`_build_naive_range` helper as `get_seat_map_assignments` (normalize both
bounds, enforce same date, emit the half-open `[start, end)` literal) and
booking `starts_at`/`ends_at` have fractional seconds stripped. `notes` carries
the operator-facing booking notes (`operatorNotes`, empty string when none —
always selected, not PII-gated). `guest_name` is the same PII-gated
primary-guest name. The query and converter live in the seatmaps triad alongside
the seatmap-read code and reuse its `_strip_fractional_seconds` /
`_join_guest_name` helpers; the models (`AssignableBooking`, `AssignableTicket`,
`CurrentSeatAssignment`) are named to avoid colliding with the existing
`Booking`/`Ticket` models.

`assign_tickets_to_seats(assignments)` is the one seatmap **write**: it batches
one aliased `assignBlocks` call per `SeatmapBlockAssignment` into a single
mutation (the queries module builds the aliases, variable declarations, and
variables — `build_assign_blocks_mutation(count)`, `assign_blocks_variables`;
`assign_blocks_alias` keeps the service/converter in sync). The service
validates up front — non-empty sequence, each `assignable_id` prefixed `t_`
(`ASSIGNABLE_ID_PREFIX`), each `block_id` prefixed `csb_` (`BLOCK_ID_PREFIX`) —
raising `ValueError` before any network call. The converter
(`to_assignment_response`) classifies each aliased result: a `__typename` of
`AssignmentResponse` (`ASSIGNMENT_SUCCESS_TYPENAME`) is a success, every other
union member (the `AssignBlocksError*` types, or a missing result) is a
per-assignment failure, yielding `"SUCCESS"`/`"FAILED"`/`"PARTIAL"`
(`AssignmentStatus` + `ASSIGNMENT_STATUSES`). Successes are returned as
`SuccessfulAssignment` pairs — the requested `assignable_id` (read back from
the result's `parent.Ticket.hashid`, falling back to the input) and the created
`assignment_id` (the `asa_…` from `assignments[].id`); failures list the
`assignable_id`. Per-assignment errors are reported in the `AssignmentResponse`,
not raised — only transport/GraphQL-level failures raise (via the shared
client).

`delete_seat_assignments(assignment_ids)` is the companion write: a single
`deleteAssignments(assignmentIds: [ID!]!)` mutation (`DELETE_ASSIGNMENTS_MUTATION`).
The service validates up front — non-empty sequence, each id prefixed `asa_`
(`ASSIGNMENT_ID_PREFIX`) — then inspects the union result: a
`DeleteAssignmentsSuccess` (`DELETE_ASSIGNMENTS_SUCCESS_TYPENAME`) maps (via
`from_deleted_assignments`) to the returned `list[DeletedSeatAssignment]` (the
now-deleted assignments, for reloading state), while any other member (e.g.
`AssignBlocksErrorInvalidBlockCount`) raises the exported `SeatmapDeleteError`
carrying the API `message`.

`ProductService` exposes three top-level product filters in addition to the
combined `get_all_products()`:
- `get_all_activities()` — fetches only the `activities` connection and keeps
  `ACTIVITY_PRODUCT_TYPE` (one request, no add-on pagination).
- `get_all_rentals()` — the same connection filtered to `RENTAL_PRODUCT_TYPE`.
- `get_all_addons()` — fetches only the `itemOptions` connection, paginated.

Custom questions are their own resource triad under
`internal/peek/custom_questions/` — `custom_question_queries.py` (query strings
and raw nodes, internal), the pure `custom_question_converter.py`, and
`CustomQuestionService`. Both reads map to the shared `list[CustomQuestion]`
model (each with `options: list[CustomQuestionOption]` for choice-style
questions), via the `... on ChoiceQuestion` inline fragment; the converter maps
`question.text` → `question_text`, `hint` → `hint_text`, and
`answerDefaultValue` → `default_value` (one private `_from_question_node` does
the mapping for both entry points):

- `CustomQuestionService.get_all()` reads the **account-wide** `questions`
  catalog across all activities (`ALL_CUSTOM_QUESTIONS_QUERY`). The catalog
  carries no per-activity configuration, so `order` is `0` and `is_required` is
  `False` on every entry; the converter entry point is `from_question_nodes`.
  Obtain the service via `PeekAccessService.get_custom_question_service()`.
- `ProductService.get_custom_questions(product_id)` reuses the same
  queries/converter module for the **single-activity** read (the `activity(id)`
  → `questionActivityConfigurations` query, `CUSTOM_QUESTIONS_QUERY`), lifting
  `order`/`is_required` from the configuration node via
  `from_question_configurations`. It raises `ValueError` on a blank `product_id`
  before any network call and returns `[]` for an unknown activity.

These are **question definitions, not customer answers**, so they carry no PII
and are unaffected by `full_customer_access`. `CustomQuestion` /
`CustomQuestionOption` and `CustomQuestionService` are exported from
`__init__.py`.

`ProductService` also surfaces each activity's `currency` on the clean
`Product` (empty string for add-ons, which have none) — the field pricing
consumers need to set the currency on fixed-price overrides.

For catalog/listing consumers, each activity `Product` additionally carries
`image_url`, `description`, and a `meeting_location` object
(`ProductMeetingLocation(summary, address, url)`). All are nullable: the scalars
are `str | None`, and `meeting_location` itself is `None` when Peek reports none
of the three underlying fields (`infoMeetingLocation` → `summary`,
`meetingLocationFormattedAddress` → `address`, `meetingLocationUrl` → `url`).
Add-ons always report `None` for all three. `ProductMeetingLocation` is exported
from `__init__.py` alongside `Product`/`ProductTicket`.

Each `Product.tickets[]` (a `ProductTicket`) additionally carries `min_price`
and `max_price` (`PricingMoney | None`), mapped from the resourceOption's
`priceRange { min max }`. They are `None` for add-on options (no range) and
when Peek reports none. The shared, internal `to_pricing_money` helper
(`internal/peek/money.py`) maps a raw money node (`{ amount, currency,
formatted }`) into `PricingMoney`, carrying `formatted` across as the optional
`display_price` display string; both the products and pricing converters reuse
it so that mapping lives in one place.

`pricing` is a **write-only, primitives-only** triad (`internal/peek/pricing/`,
model `models/peek/pricing.py`). It wraps the four Peek pricing mutations —
`createPricingEngine`, `updatePricingEngine`, `deletePricingEngine`, and
`upsertPricingOverridesActivityContexts` (used for both upsert and clear) —
behind `PricingService`
(`create_engine`/`update_engine`/`delete_engine`/`upsert_overrides`/`clear_overrides`).
It deliberately does **not** own the domain logic that decides *what* the
overrides are (segmenting an activity across time windows, ordering tiers,
computing `spots_taken` bounds, sunrise/sunset resolution): callers build a
clean `UpsertOverridesInput` and the service sends it faithfully. The clean
model expresses the TypeScript discriminated unions as one dataclass per
variant with a `mode: Literal[...]` default plus a union alias:
`FixedResourceOptionOverride` / `PercentageResourceOptionOverride`
(→ `ResourceOptionOverride`), `SpotsTakenFilter` / `StartTimeRangeFilter`
(→ `PricingOverrideFilter`), and `ResolvedFixedOverride` /
`ResolvedPercentageOverride` (→ `ResolvedOverride`). The union aliases, the
variant classes, and the top-level inputs/results are all exported from the
package root (documented in `docs/external/pricing-api.md`). The only transforms the service applies are
strip-the-`mode`-tag on each resource-option override (→ the bare `price` /
`percentageAdjustment` wire key, in `pricing_queries.py`) and, on the response,
the inverse plus filter-`__typename` normalization (in `pricing_converter.py`).
`delete_engine` is idempotent — the response union is not inspected, so a
`NotFoundError` resolves. Validation (engine/date-range presence, currency
format, numeric amounts, `percentage_adjustment > -100`) lives in the service
and raises `ValueError`; a non-success union member on the other mutations also
raises `ValueError` carrying Peek's message. The consumer-facing guide is
`docs/external/pricing-api.md` — **keep it in sync** whenever this surface
changes.

`availability` is a full triad (`internal/peek/availability/`, model
`models/peek/availability_time.py`): `AvailabilityService.get_availability_times`
reads `availabilityTimes` and `availability_converter.py` (`to_availability_time`)
maps each raw node to an `AvailabilityTime`. Each slot carries a per-ticket
`price` (`Money | None`, via the converter's `_to_money`). `Money`
(`models/peek/money.py`, `amount`/`currency`/`formatted`, all `str`) is the
shared, public clean-money dataclass reused across resources (booking add-ons'
`BookingAddon.total` via `addon_converter._to_addon_money`, availability prices);
it is distinct from the pricing domain's `PricingMoney` (which renames
`formatted` → optional `display_price`). The internal `to_pricing_money` helper
(`internal/peek/money.py`) and `PricingMoney` are unaffected. The TypeScript
package keeps `BookingAddonMoney` as a `@deprecated` alias of `Money`; this port
does not (see `CONVENTIONS.md`), and `AvailabilityTime` here never carried the
`minimumTicketsRequired` field TypeScript added in 1.0.1 and removed in 1.2.0.

`waivers` is a **webhook-only resource**: it has no GraphQL reads (so no
queries/service/converter triad), just `internal/peek/waivers/waiver_webhook.py`
and the `models/peek/waiver.py` model. See the webhook notes below.

A resource may split into more than one triad when it carries a distinct
sub-domain. `bookings` does: alongside `booking_queries`/`booking_converter`
(plus `booking_guest_converter.py` for the guests read), the add-on flows live
in `addon_queries.py` (the `sales` add-ons query + raw node shapes) and
`addon_converter.py` (raw node → the internal `AddonItem` detail model and the
clean public `BookingAddon`), and `payments_on_file_converter.py` maps the
payments-on-file read.

`bookings` carries a third sub-domain for **custom-field metadata** —
`metadata_queries.py` + `metadata_converter.py`, surfaced by
`BookingService.get_meta_data(booking_id)` → `list[MetaData]` (`[]` when the
booking is not found or has no matching fields). Its query is a variant of the
single-booking read: it reuses the shared `sales(...)` envelope
(`build_sales_query`, in `booking_queries.py` and shared by the
listing/guests/payments/metadata readers) and the shared
`build_bookings_variables` (filtering by `bookingFilter.ids`), selecting only
the `fieldResponses` tree. The clean model (`models/peek/booking_metadata.py`)
flattens each response's field (id/name/slug/type), prompt (label/hint/required),
and `refid`, and carries one typed `value: MetaDataValue | None` — a
**discriminated union keyed by `kind`**, one dataclass per gateway
`…FieldResponseValue` type, joined by a `Union` alias. The pure converter
discriminates on the value's `__typename` (selected in the query); an
unrecognized/future variant maps to `None` (never coerced). Numeric `Int` →
`int`, `Decimal` → `str` (no float loss), `Date`/`Time` → ISO string. The parent
`MetaData` carries a `display_value` — a display-safe human string the converter
renders per kind (booleans → `Yes`/`No`, amount+unit → `"3 hours"`, percent →
`"12.5%"`, location → comma-joined parts, meta → `json.dumps`, and the `html`
variant **HTML-escaped** via the local `_escape_html`); it is always present,
`""` when the value is absent. `MetaData`, `MetaDataValue`, and the unit/type
aliases (`MetaDataBarcodeType`/`MetaDataDurationUnit`/`MetaDataVolumeUnit`/
`MetaDataWeightUnit`) are exported from `__init__.py`.

**Integrator scoping.** `get_meta_data` returns only the fields whose `slug`
starts with `integrators:<integrator>:` (case-sensitive exact prefix), stripping
that prefix off each returned `slug` (pure `filter_meta_data_by_integrator`).
The integrator is **per `BookingService`**, supplied by
`PeekAccessService.get_booking_service(integrator=None)`; when omitted it
defaults to the install's `issuer`. The accessor memoizes one `BookingService`
per resolved integrator string (a `dict`), so the no-arg/default call and a
`get_booking_service(issuer)` call share an instance. The consumer-facing docs
deliberately describe the param only as "do not set unless Peek engineering
created a custom integrator id" and do **not** reveal the issuer default.

**Writing metadata.** The `upsertBookingFieldResponses` mutation
(`metadata_queries.py`) is surfaced through **eight fixed-field-name setters**
on `BookingService` — `set_meta_data_guest`, `set_meta_data_attachment`,
`set_meta_data_manifest_url`, `set_meta_data_reservation_id`,
`set_meta_data_booking_status`, `set_meta_data_assigned_product`,
`set_meta_data_assigned_employee`, `set_meta_data_insurance_purchased`. Each
hard-codes its `fieldName` (the `META_FIELD_*` constants; the caller only
supplies the value) and funnels through one private `_upsert_field_response`
helper that validates the booking id, injects the service `integrator`, and
maps the result union (`UpsertBookingFieldResponsesSuccess` /
`BookingNotFoundError` / `GenericError`, discriminated by `__typename`) into a
clean `SetMetaDataResult(success, booking_id, message)` via the pure
`to_set_meta_data_result` — the error variants resolve to `success=False`
rather than raising. `guest` takes `Sequence[SetMetaDataGuestInput]`
(name/email required; DOB/waiver/notes optional) and `attachment` takes
`Sequence[SetMetaDataAttachmentInput]` (name/attachment_url required); the
other six take a single `str`/`bool`. The setters are **not PII-gated**
(operator-facing writes of caller-supplied data). `SetMetaDataGuestInput`,
`SetMetaDataAttachmentInput`, and `SetMetaDataResult` are exported from
`__init__.py`.

`bookings` also carries the webhook surface (`booking_webhook.py`). A Peek
booking webhook's payload shape is defined by the GraphQL field selection
registered with it, so the registered query and the parser must stay in lockstep.
Crucially, that registration is done **once in an external system** (the App
Store `broadcast_to_url` config), not from consumer code — so the package
registers nothing at runtime, and the two halves split:

- **The query is a setup-time artifact, not a runtime API.**
  `BOOKING_WEBHOOK_GQL_QUERY` is the single maximal selection set (guests + full
  price breakdown always included) built from the same field fragments the read
  path uses (`BOOKING_QUERY_FIELDS`, `BOOKING_GUESTS_FIELDS`,
  `PRICE_BREAKDOWN_FIELDS`, exported from `booking_queries` for reuse). It is
  the bare selection set (no `query`/`sales` wrapper — the webhook system
  supplies that; whitespace collapsed so it drops into a JSON config string). It
  is **internal** — surfaced for humans/AI through `docs/webhooks.md` and pinned
  by a drift-guard test (`tests/peek/bookings/test_booking_webhook.py`) that
  snapshots the exact string, so a field change is caught here before it
  diverges from the external config. The string is identical to the TypeScript
  package's, so one registration serves both.
- **The parser is the only public runtime export.** The pure
  `parse_booking_webhook(body)` unwraps the `{"booking": …}` delivery envelope
  (or a bare node / JSON string) and runs the existing `from_booking_node`
  converter, auto-detecting guests/price-breakdown from the payload (nothing to
  keep in sync with the registered query) and never raising on malformed input.
  Parsing needs no auth, network, or client, so it is a **standalone function,
  not a method on `PeekAccessService`** (a receiver may not hold API
  credentials).

The **waiver** webhook (`waivers/waiver_webhook.py`) is the simpler sibling and
deliberately diverges from the booking shape because the upstream webhook does
too: it has **no GraphQL query** (the App Store `waiver_webhook_data` output
format ships a fixed payload, `output_fields_gql_query` is null), so there is no
query constant and no drift-guard — only a parser. `parse_waiver_webhook(body,
options=None)` unwraps the `{"waiver": …}` envelope (or a bare node / JSON
string) and runs the pure `from_waiver_node` converter, which maps the fixed
`snake_case` payload to the flat clean `Waiver` model (defaulting missing fields
to `""`/`None`/`False`, so it never raises). Same standalone-pure-function
rationale as bookings. Because there are no reads, `waivers` carries no
queries/service triad — just the webhook module and the model.

The **install** webhook (`installs/install_webhook.py` + `install_converter.py`)
is the third and most distinct. A single delivery carries **two payloads at
once**: a **signed `app_registry_v2` JWT** (the security boundary, delivered in
the `x-peek-auth` request header) and a plain **JSON body** (the event payload).
`parse_install_webhook(token, body, secret)` *verifies* the token (signature +
expiry + issuer + `Joken` audience, via the shared `peek_auth_token.py` core) and
merges both into one flat `InstallWebhook` (`models/peek/install.py`). The
`token` argument accepts the raw header value — the shared `verify_peek_jwt`
core strips a leading `Bearer ` scheme prefix (case-insensitive) before
verification (see §1 / `peek_auth_token.py`), so no token entry point makes the
caller unwrap it. Standalone-function rationale as above, with an extra reason:
the receiver has no per-install service to inherit a secret from yet (the
webhook can precede the first session or describe a tear-down), so the app
secret is passed directly. `installs` carries no queries/service triad — just
the parser, the pure `install_converter.py` helpers
(`extract_install_webhook_body`, `to_install_status`, `to_peek_platform`), and
the model.

The TypeScript package's deprecated `verifyInstallWebhook(token, secret)` (and
its `InstallWebhookClaims`/`InstallWebhookAccount` models) was **not ported**:
it reads only the signed token, so it cannot report the account name, platform,
test flag, timezone, or `api_url` that live in the JSON body.
`parse_install_webhook` is the only install-webhook entry point here.

Three design rules hold this together and are load-bearing:

- **`install_id` comes only from the token `sub`.** The body `install_id` never
  sets it; it is only compared. A non-empty body `install_id` that is not equal
  to `sub` raises `InstallWebhookError(reason="install_id_mismatch")`, and a
  verified token with no usable `sub` (absent, non-string, blank, or `"null"` —
  the shared `clean_token_string` sentinel rule) raises it with
  `reason="missing_subject"`. The check lives in `_resolve_install_id` in
  `install_webhook.py`; the converter stays pure.
- **A delivered `api_url` must be a Peek-owned domain.** When the body carries a
  non-empty `api.url`, its host must be `peek.com` (production) or
  `peeklabs.com` (sandbox), or a subdomain of either, or `parse_install_webhook`
  raises `InstallWebhookError(reason="invalid_api_url")` — a spoofed webhook must
  not be able to point the app's API calls at a foreign gateway. An absent
  `api_url` is not validated. The check (`_assert_allowed_api_url`, with the
  allow-list in the module-level `ALLOWED_API_URL_DOMAINS` and the host parsed
  by `urllib.parse.urlsplit`) lives in `install_webhook.py`; a scheme-less value
  is parsed as `https`, the suffix match is case-insensitive and
  label-anchored (`peek.com.evil.com` does not match), and the converter stays
  pure.
- **The JSON body is the source of the other event data; the JWT authenticates
  it and is the fallback.** `account_name`, `platform`, `is_test`, `timezone`,
  `api_url` are body-only, and `account_id`, `status`, `display_version`, `user`
  (from `modified_by`) fall back to the verified token when the body omits them.
  The install token does not reliably carry those four, so reading it first
  returned empty core fields — the body is where the data lives. The token does
  carry `sub`, and the registry sets the body `install_id` to the same value, so
  a real delivery passes the install-id check. `user` resolution is defensive on
  the body path (a `modified_by` without a real `id` is treated as absent) but
  keeps the strict `map_peek_token_user` `id` check on the token path.
- **`InstallWebhook` is flat and JSON-safe.** The shape the parser returns is the
  shape a consumer persists and later rehydrates (`dataclasses.asdict` round
  trips it), so there is exactly one representation of "who this install is and
  what happened" and no mapping layer. Do not add methods, nested objects, or
  non-JSON types to it.
- **`status` and `platform` are nullable, and unknown values are never coerced.**
  The package does not defend against malformed input here (the sender is
  first-party); it defends against the contract *growing*. An unrecognised value
  maps to `None` with the wire value kept on `InstallWebhook.raw_status`.
  Coercion would be unsafe: Peek treats any 2xx as delivered and does not
  redeliver, so a status quietly mapped onto a no-op loses a lifecycle
  transition permanently, and a defaulted platform points the install at the
  wrong backoffice. When a new status or platform ships, extend
  `INSTALL_STATUSES` / `PEEK_PLATFORMS` **and** the matching `InstallStatus` /
  `PeekPlatform` `Literal` alias — Python cannot derive one from the other, so
  the tuple and the `Literal` are kept side by side in the model module.

`account_id` deserves a note: it is what Peek elsewhere calls the **partner ID**,
and this webhook is its *only* source. No GraphQL query in this package selects
an account id (the API routes by install); the account id lives on the install
webhook alone — the session peek-auth token does not carry one
(`PeekAuthTokenUser.id` is the acting **user**, not the account). A consumer that
loses it cannot re-fetch it.

The detailed `AddonItem` model (refids + reservation statuses) is **internal
only** — consumers see just the grouped `BookingAddons`; the internal model
exists solely so add/remove can build their mutation payloads.

Recurring patterns inside services:
- **Cursor pagination** is handled internally and transparently — e.g.
  `ProductService` gathers every add-on page; `BookingService._fetch_paginated`
  walks `pageInfo.hasNextPage`/`endCursor`. Callers get a single flat list. The
  loop is the one place an `await` inside a `while` is correct (each page yields
  the next cursor); independent reads use `asyncio.gather`.
- **Offset/count review reads** — `ReviewService.get_reviews(product_id,
  review_count=50, review_offset=0)` fronts a `reviews` connection that returns
  newest-first (descending `reviewedAt`) with only per-edge `cursor`s (no
  `pageInfo`). It fetches a **single page** of up to `review_count` reviews
  (validated 1–50), skipping the first `review_offset` newest reviews
  (validated non-negative integer; `bool` is rejected as an integer). No
  pagination loop, no cache, no date filtering — callers slice the newest-first
  list by count and offset.

  The gateway cursor is the base64 of `range:<start>..<end>,<offset>` where
  `<offset>` is the absolute index of the object in the result set.
  `reviews/review_cursor.py` is a small pure module that encodes/decodes that
  format (the only place `base64` is used). Because the cursor resumes *after* a
  given offset, a non-zero `review_offset` is sent as
  `encode_cursor(review_offset - 1, review_count)`; an offset of 0 sends no
  cursor. This is the one resource whose triad carries a fourth helper file
  (`review_cursor.py`) alongside queries/converter/service.

  `ReviewService.get_all_review_summaries()` is a second, aggregate read on the
  same service: a single `activities { id name reviewMeta { … } }` query (the
  same `activities` connection `ProductService` reads) mapped by the pure
  `from_activity_review_summary_nodes` into `list[ProductReviewSummary]` —
  per-activity average rating and per-star counts. It carries no per-review
  detail or PII, so it is unaffected by `full_customer_access`; an activity with
  no reviews maps to a `None` `avg_rating` and zero counts.
  `ProductReviewSummary` is exported from `__init__.py`.
- **Composition** — `BookingService.add_addon` resolves an add-on's parent item
  through `ProductService`; `TimeslotService.assign_guide` resolves guides
  through the resource-pool + account-user services (fetched in parallel with
  `asyncio.gather`) using the pure `match_guide_to_resource_pool` matcher
  (`timeslots/guide_matcher.py`).
- **Multi-step mutations** — booking creation (`createQuoteV2` →
  `createOrderFromQuote`) and both add-on mutations (`createQuoteFromOrder` →
  `updateQuoteV2` → `amendOrder`) are orchestrated as ordered request chains
  with per-step error checks. When `CreateBookingInput.parent_order_id` is set,
  `create` instead takes the **amendment path** (`_create_via_amend`):
  `createQuoteFromOrder` seeds a quote bound to that order
  (`_create_quote_from_order_or_raise`, shared with the add-on flows),
  `updateQuoteV2` adds the new booking to it in the **sparse** input shape (same
  field names as the strict quote but with `reservationStatus: "CONFIRMED"`
  stamped explicitly at the booking and ticket level, since sparse drops those
  defaults), and `amendOrder` applies it (`_amend_order_or_raise`) —
  `createOrderFromQuote` is never called because it always mints a *new* order.
  The amended order holds every pre-existing booking plus the new one, so
  `create` locates the new booking by the client-generated `refid` it carried
  through the quote (the expanded `amendOrder` selection reads back `sales { …
  on Booking { id displayId refid balance } }`, matched on `BOOKING_TYPENAME`),
  never by list position; a missing refid match is a hard error
  (`ERROR_AMEND_NO_MATCHING_BOOKING`). `mark_as_paid` then charges that
  booking's own balance, not the order total. `parent_order_id` is
  format-checked by `assert_order_id` in `_validate_create_input`. When
  `CreateBookingInput.promo_code` is a non-empty string (trimmed via
  `_resolve_promo_code`), `create` attaches it to the `createQuoteV2`
  `quoteInput` as `promoCodes: [{ code, refid, isEnabled: true }]` with a fresh
  `refid`; it is rejected up front (`ERROR_PROMO_CODE_WITH_PARENT_ORDER`,
  `ValueError`) when combined with `parent_order_id` — the amendment path
  creates no quote — so the code is never silently dropped. When
  `CreateBookingInput.list_price` is set, the
  pure `bookings/list_price.py` (`distribute_list_price`, `Decimal`-based)
  splits that total across the expanded ticket seats in integer cents —
  `floor(total / n)` for the first n-1, the remainder to the last — and `create`
  attaches a per-ticket `price { amount, currency }` to the `createQuoteV2`
  tickets, resolving the currency from the activity via
  `ProductService.get_all_products()` (fallback `"USD"`, gathered in parallel
  with the question-answer read). A malformed `list_price` raises before any
  network call. When `CreateBookingInput.custom_question_answers` is supplied,
  `create` first fetches the activity's custom questions
  (`ProductService.get_custom_questions`) and runs the pure resolver in
  `bookings/custom_question_answer.py` (`resolve_custom_question_answers`) to
  match each answer (by id or lenient text) and validate its value by question
  type. Every resolved answer carries `questionAnswerText` (required by the
  gateway): the raw value for text, the option's exact label for
  select-one/location (which also set `questionAnswerOptionId`), and
  `"Yes"`/`"No"` for a checkbox (which also sets `isChecked`). Options are
  matched by id or lenient label. Per-guest questions are rejected (`not yet
  supported`). When `CreateBookingInput.require_required_questions` is set, the
  resolver also runs even if no answers were supplied and raises for the first
  required, non-per-guest question left unanswered. When
  `CreateBookingInput.accept_all_custom_question_ids` is set, a `cq_…` id that
  is not in the activity's question list is accepted as a plain text answer
  rather than raising (by-name answers are unaffected — they still must match a
  question); the service uses `is_custom_question_id` to skip the
  `get_custom_questions` fetch entirely when every answer is by id and no
  required-coverage check is enforced. This runs before the first
  `createQuoteV2`, so a bad answer fails before any quote exists; the service
  then tags each resolved answer with a fresh `refid` (`uuid4`) and attaches
  them as the quote's `questionAnswers`. `add_addon` and `remove_addon` first
  call the `sales` add-ons query to derive the order id from the booking and
  reuse existing item/option refids — `add_addon` reuses a non-canceled add-on's
  item refid rather than minting a duplicate, and `remove_addon` cancels options
  by their existing refids (pure `build_cancellation`), marking the parent
  add-on canceled only when all of its options end up canceled. Both finish by
  re-listing and returning the booking's refreshed add-ons.
- **Input validation** lives in the service and raises `ValueError` (3-letter
  currency, positive-integer quantities, allowed payment sources, etc.).
  `normalize_booking_id` lowercases and converts `-` → `_`. Every booking/order
  id accepted as a parameter is format-checked **before** normalization by
  `assert_booking_id`/`assert_order_id`: an id is valid only as a lowercase db id
  with `_` (`b_abc123` / `o_abc123`) or an uppercase display id with `-`
  (`B-ABC123` / `O-ABC123`) — bookings prefixed `b`, orders `o`. Mixed forms
  (`B_abc123`, `o-Ab123`), a missing prefix, or the wrong resource's id are
  rejected. Validating pre-normalization is deliberate: normalization would
  erase the case/separator distinction the check relies on. Static strings
  (error messages, status values, wire keys) are module-level `Final`
  constants, never inline literals.

### 4b. Access options / PII
`access_options.py`

Every access service (`PeekAccessService`, `CngAccessService`, `AcmeAccessService`)
accepts an optional `access_options` config field — the public `AccessOptions`
dataclass. Today it carries one flag, `full_customer_access` (default `False`);
it is an object rather than a bare boolean so future cross-cutting flags slot in
without changing any downstream signatures. `PeekAccessService` resolves it once
(`resolve_access_options`, which fills defaults into a `ResolvedAccessOptions`)
and threads the resolved value into the resource services that read customer
data (`BookingService` via `BookingServiceOptions`, `ReviewService` and
`SeatmapService` directly). CNG/ACME accept the field but have no PII surface,
so it is inert there.

When `full_customer_access` is `False` (the default), two things happen:

1. **PII is never requested (filtered at the query-builder layer, not in the
   converters).** The query *builders* omit the PII fields entirely, so the API
   never returns them and the pure converters map the now-absent fields to
   `None`/empty — the converters stay PII-agnostic. Affected:
   - **Bookings** (`booking_queries.py`): `build_booking_query_fields` /
     `build_booking_guests_fields` / `build_booking_guests_query` /
     `build_bookings_listing_query` drop the primary-guest block
     (`customer_name`/`customer_email`/`customer_phone`), the guest identity
     fields (name/country/DOB/email/phone/postal code/`is_gdpr`/field responses
     — the guest list keeps only ids + participation/opt-in flags), the custom
     question answers (booking- and ticket-level), and the customer
     `portal_url`. Operator-facing fields (notes, the operator custom status,
     the Peek Pro deep link, money, resources) always stay. The booking-metadata
     query (`metadata_queries.py`, behind `get_meta_data`) gates the
     `GuestFieldResponseValue` identity fields the same way — `name`/`email`/
     `dateOfBirth` are only selected with `full_customer_access`;
     `notes`/`waiverSigned` always stay.
   - **Reviews** (`build_reviews_query`): drops the reviewer `name`/`email`; the
     review `comment`, rating, dates, and credited guides always stay.
   - **Seatmaps** (`build_seatmap_assignments_query` /
     `build_assignable_bookings_query` in `seatmap_queries.py`): drop the
     booking `primaryGuest { firstName lastName }` selection, so a GUEST
     occupant's / assignable booking's `guest_name` is `None`. The layout, seat
     `status`, booking/ticket ids and names, `starts_at`/`ends_at`, operator
     `notes`, and staff (`AccountUser`) names always stay; the plain
     `get_seatmap_for_product` / `get_seatmap_ids_for_product` reads select no
     customer data at all.
   - **Waivers** (`parse_waiver_webhook`): the webhook delivers a *fixed*
     payload with no selection to trim, so this is the one place filtering is
     applied at parse time — the participant `guest_name` becomes `None` and the
     signed-document `file_url` becomes `""` (`dataclasses.replace` on the
     already-mapped `Waiver`). `parse_waiver_webhook(body, options=None)` takes
     the same `AccessOptions`; `from_waiver_node` stays a pure full mapping.

2. **Payment / booking-modification operations are disabled.** `BookingService`
   gates the operations that touch customer financial data —
   `get_payments_on_file`, `make_payment`, `refund`, `create_invoice_link`,
   `add_addon`, `remove_addon` — raising `PiiAccessDisabledError` (an exported
   typed error carrying the snake_case `operation`) via `_assert_pii_enabled`
   before any network call. Non-payment reads/mutations (`get_by_id`,
   `get_guests`, `cancel`, `append_note`, `set_checkin_status`,
   `update_custom_status`, `get_meta_data`, the `set_meta_data_*` setters) and
   `create` (**including `mark_as_paid`**) remain available.

The webhook **registration** query (`BOOKING_WEBHOOK_GQL_QUERY`) is deliberately
unaffected — it is the maximal selection built from the full field fragments
(`build_*_fields(True)`) and pinned by the drift-guard test;
`full_customer_access` governs only the runtime read path.

### 5. Public API surface
`__init__.py`

The barrel re-exports only the public contract: `PeekAccessService` + its
config, `BaseAccessServiceConfig`, the `create_access_service_for_install`
factory (+ its `InstallAccessTarget` / `InstallAccessConfig` /
`InstallAccessService` types — builds the right access service for an install's
`platform`, wired to its `api_url`), `AccessOptions` (see §4b), each resource
service class (and the options/result types callers need:
`AccountUserServiceOptions`, `BookingServiceOptions`, `ProductServiceOptions`,
`PromoCodeServiceOptions`, `AddAddonInput`, `CancelBookingResult`), all
data-model dataclasses and `Literal` aliases (including `PeekAuthTokenClaims`,
`PeekAuthTokenUser`, `PeekPlatform`/`PEEK_PLATFORMS`, `InstallWebhook`,
`InstallStatus`/`INSTALL_STATUSES`, `Waiver`, the shared `Money`, the
`CustomQuestion` models, the seatmap models — `Seatmap`/`SeatmapZone`/
`SeatmapTicket`/`SeatmapSection`/`SeatmapGroup`/`SeatmapBlock`/`SeatmapDisplay`,
`SeatmapSummary`, the `Assigned*` tree + `SeatmapAssignment`,
`AssignableBooking`/`AssignableTicket`/`CurrentSeatAssignment`,
`SeatmapBlockAssignment`/`AssignmentResponse`/`SuccessfulAssignment`,
`DeletedSeatAssignment`, with the `SeatmapDisplayType`/`SeatmapBlockStatus`/
`SeatmapOccupantType`/`AssignmentStatus` aliases and their `SEATMAP_*` /
`ASSIGNMENT_STATUSES` tuples — and the product-type constants), the `Logger`
protocol + `noop_logger` + `logging_adapter`, the three webhook parsers
(`parse_booking_webhook`, `parse_waiver_webhook`, `parse_install_webhook`), and
the typed error classes (`AppUtilitiesError`, `AdminAccountRequiredError`,
`RateLimitError`, `PeekGraphQLError`, `PeekHttpError`, `PiiAccessDisabledError`,
`UnknownSeatmapDisplayTypeError`, `UnknownSeatmapBlockStatusError`,
`UnknownSeatmapAssignmentParentError`, `SeatmapDeleteError`,
`InstallWebhookError` (subclasses PyJWT's `jwt.InvalidTokenError`; + its
`InstallWebhookErrorReason` alias), `CngApiError`, `CngPermissionError`,
`AcmeApiError`). `V2_FALLBACK_URL_PREFIX` / `DEFAULT_BASE_URL` stay on
`peek_access_service.py` (not in the barrel). Query strings, raw `TypedDict`s, the transports, and the
internal detail models are deliberately kept internal — including the
booking-webhook registration query (`BOOKING_WEBHOOK_GQL_QUERY` stays internal,
documented via `docs/webhooks.md`). `__all__` is the authoritative list.


### 5a. Shared REST plumbing (CNG + ACME)
`internal/rest_client.py`, `internal/rest_access.py`, `internal/http_transport.py`

Where the TypeScript package carries a near-identical `RestClient` per REST
platform, this port has **one** `RestClient` parameterized per platform through
`RestClientOptions`: the log label (`"CNG"`/`"ACME"`), the `api_error` factory
raised on a non-2xx response, and an optional `on_forbidden` handler for the
CNG-only HTTP 403 branch. It GETs `join_url(base_api_url,
endpoints.path_for(endpoint), path)` with `X-Peek-Auth: Bearer` and
`x-peek-sdk` (no `pk-api-key`, no `{query, variables}` body), reads the body
with the shared `parse_body`, and runs through the shared `request_with_retry`
loop (`http_transport.py`), which owns the 429 backoff and the 418 → `AdminAccountRequiredError`
/ 429 → `RateLimitError` mapping for every platform.

`rest_access.py` is the matching shared wiring for the two REST access
services: `OwnedHttpClient` (owns-or-borrows the `httpx.AsyncClient`, giving
every access service `aclose()` + `async with`), `validate_rest_config` (the
required fields; `app_id` only without `api_url`), `resolve_rest_base_api_url`
(`api_url` with the slug stripped, else `base_url/app_id` with the app-registry
default base), and `build_rest_client`, which each REST access service calls
with its own slug/endpoints/label/error types. The access services are
therefore thin, declarative shells.

### 5b. CNG accessor (REST)
`cng_access_service.py`, `internal/cng/`, `models/cng/product.py`

A second, brand-parallel accessor for the **CNG** backoffice — REST, not
GraphQL. Deliberately low-churn: it sits alongside the Peek code and shares the
plumbing rather than forking the package.

- **`CngAccessService`** — `CngAccessServiceConfig` is an alias of
  `BaseAccessServiceConfig` (**no `gateway_key`** — the CNG API needs no
  `pk-api-key`). Validates `install_id`, `jwt_secret`, `issuer` (and `app_id`
  without `api_url`), builds the shared `TokenManager` and a `RestClient` via
  `build_rest_client` (with the CNG `forbidden_error` handler), defaults the
  base URL to the app-registry installations API, and exposes
  `get_product_service()` only (no short-form).
- **Products triad** (`internal/cng/products/`) — same shape as every Peek
  resource: `product_queries.py` (raw REST `ProductNode`/`ProductsResponse`
  `TypedDict`s, internal), `product_converter.py` (pure `from_product_nodes` →
  `Activity`), `product_service.py` (`CngProductService.get_all_activities()`,
  reading the `{ data: [...] }` resource collection). Endpoint segments live in
  `internal/cng/endpoints.py` — the products path
  `api/v2/app-registry/products?active=1`; the `active=1` filter is applied by
  the gateway, so inactive/archived products never reach the converter (ACME
  filters client-side instead, on `reviewState`).
- **HTTP 403** (`internal/cng/permissions.py`) → `CngPermissionError` (the
  gateway's "app is missing permission X" rejection — the permission names are
  parsed off `errors.permission` onto `.permissions`, and it is logged at
  **`warn`**, not `error`, because a misconfigured install is expected rather
  than a fault); any other non-2xx (other than 418/429) → `CngApiError`
  (status + body). The 403 branch is CNG-only — ACME and Peek still surface 403
  as their generic HTTP error.
- **Model** `models/cng/product.py` — `Activity`/`ActivityTicket`, mirroring the
  Peek `Product` shape so both brands read uniformly. The CNG products payload
  carries no type discriminator and no sub-options, so `type` is always
  `ACTIVITY` and `tickets` is always empty (same as ACME); `product_id` is the
  numeric REST `id` stringified, and `color` comes from
  `access_control_color_hex`.
- **Public exports:** `CngAccessService` + `CngAccessServiceConfig`,
  `CngProductService`, the `Activity`/`ActivityTicket` models, and
  `CngApiError`/`CngPermissionError`. REST paths and raw response shapes stay
  internal.

### 5c. ACME accessor (REST)
`acme_access_service.py`, `internal/acme/`, `models/acme/product.py`

A third, brand-parallel accessor for the **ACME** backoffice. Same
auth/transport/tooling reuse as CNG (§5a/§5b) — only the routing, endpoint, and
response shape differ:

- **`AcmeAccessService`** — identical shell to `CngAccessService`
  (`AcmeAccessServiceConfig` is also an alias of `BaseAccessServiceConfig`),
  built with the `acme_backoffice_api-v1` slug, the `"ACME"` log label, and
  `AcmeApiError` on non-2xx; no `on_forbidden` handler. Exposes
  `get_product_service()` only.
- **Products triad** (`internal/acme/products/`) — `product_queries.py` (raw
  `TemplateNode`/`TemplatesResponse` for the `{ list: [...] }` envelope, plus
  the `PUBLISHED_REVIEW_STATE` constant, internal), `product_converter.py` (pure
  `from_template_nodes` → `AcmeActivity`, **filtering to published templates
  only** and mapping `colorCategory.backgroundColor` → `color`),
  `product_service.py` (`AcmeProductService.get_all_activities()`, tolerating a
  `{ list: [...] }` envelope or a bare array). Endpoint segments live in
  `internal/acme/endpoints.py` — the template-names path
  `v2/b2b/event/templates/names?pageSize=-1&page=1`.
- **Model** `models/acme/product.py` — `AcmeActivity`/`AcmeActivityTicket`,
  mirroring the CNG `Activity` shape. ACME exposes no tickets today, so
  `tickets` is always empty; only `product_id`/`name`/`color`/`type` are
  populated.
- **Public exports:** `AcmeAccessService` + `AcmeAccessServiceConfig`,
  `AcmeProductService`, the `AcmeActivity`/`AcmeActivityTicket` models, and
  `AcmeApiError`. Distinct type names avoid the collision with CNG's
  `Activity`. REST paths and raw response shapes stay internal.

### 6. UI components — not ported

The TypeScript package ships a second, browser-only surface
(`@peektravel/app-utilities/ui`: Odyssey Web Components, tokens, CSS). That
surface is **TypeScript-only** and has no Python counterpart — a Python
backend has nothing to render it with. There is no `ui` module, no `ui.html`
reference, and nothing to keep in sync here; consumers who need the components
install the TypeScript package for the browser side.

## Build & tooling

- **Packaging:** `hatchling` via `pyproject.toml`; `uv build` produces the sdist
  + wheel into `dist/`. The wheel ships `src/peek_app_utilities` (with
  `py.typed`); the sdist additionally includes `README.md`, `changelog.md`,
  `llms.txt`, `docs/webhooks.md`, and `LICENSE`. `docs/internal/` is
  deliberately **not** shipped.
- **Python:** `requires-python >= 3.11` (needed for `typing.Self`,
  `datetime.UTC`, `X | Y` in `isinstance`, and keyword-only/slotted
  dataclasses). CI runs 3.11, 3.12, and 3.13.
- **Dependencies:** `httpx` (transport) and `PyJWT` (HS256 signing and
  verification) are the only runtime dependencies. Dev group: `pytest`,
  `pytest-asyncio` (`asyncio_mode = auto`), `pytest-cov`, `respx`, `mypy`,
  `ruff`, `python-dotenv` (for the harness).
- **Lint/format:** `ruff` (`E F W I UP B ASYNC RUF ANN N SIM T20`, line length
  100, `py311` target); `ruff format`.
- **Types:** `mypy --strict` over `src`, `tests`, and `scripts`
  (`warn_unreachable`); tests get a relaxed per-module override.
- **Tests:** `pytest` with `filterwarnings = error`. Coverage via
  `pytest --cov` with **`fail_under = 95`** on lines **and branches**
  (`branch = true`). Tests never hit the network: `tests/conftest.py` provides
  `FakeGraphQLClient` (the `gql` fixture — records every `(endpoint_name,
  query, variables)` call and replays queued `{"data": …}` bodies or
  exceptions) for resource-service tests, `mock_http_client(handler)` (an
  `httpx.AsyncClient` over `httpx.MockTransport`, the analogue of injecting a
  fake `fetch`) for transport tests, `RecordingLogger`, and `no_sleep` for retry
  tests. Service tests assert on `gql.calls[n].variables` and on substrings of
  `gql.calls[n].query` (e.g. that a PII field is or is not selected). Every
  TypeScript `describe`/`it` case is ported one-to-one, including the
  drift-guard snapshot tests.
- **Developer harness:** `scripts/gql_cli/cli.py` drives the real resource
  services against the live API (outside `src/`, never packaged; CI checks it
  compiles with `python -m py_compile`). Its `REGISTRY` must be kept in sync
  with the public service surface (see `CLAUDE.md`) — it carries a
  `custom-questions` and a `seatmaps` group alongside the older ones, and mirrors
  `PeekAccessService`'s URL model (`PEEK_API_URL` set → the registry-slug route
  that `mode="v2"` uses; unset → the legacy v1 `base_url/app_id` route with
  `PEEK_GATEWAY_KEY`).
- **Generated HTML changelog:** `docs/html/changelog.html` is rendered from
  `changelog.md` by `scripts/build-changelog-html.mjs` — a Node script vendored
  from the TypeScript package (branding aside, unchanged) so both ports render
  the same Markdown subset into the same page shell as `docs/html/*.html`
  (left-nav of versions, filter, light/dark toggle, `[breaking]`/`[fix]`/
  `[additive]`/`[deprecated]` badges). `changelog.md` is the single source of
  truth; the HTML is never hand-edited. `tests/test_changelog_html.py` is the
  drift guard: it runs the script with `--check` (skipped when `node` is not on
  `PATH`) and fails when the committed HTML differs from a fresh render, so
  `pytest` catches a stale file. The page is linked from `docs/index.html`
  under its own "Changelog" card.
- **CI:** `.github/workflows/ci.yml` runs on every push to `main` and every pull
  request, across the three Python versions: `uv sync --group dev` → `ruff check`
  + `ruff format --check` → `mypy` → `pytest --cov` (coverage gate) → harness
  compile check → `uv build`.
- **Distribution:** published to **PyPI** as `peek-app-utilities`. Releases are
  automated by `.github/workflows/publish.yml`, which runs on a `v*` tag push:
  it asserts the tag matches `pyproject.toml`'s `project.version`, builds with
  `uv build`, and publishes through `pypa/gh-action-pypi-publish` using PyPI
  **Trusted Publishing** (OIDC, `id-token: write`, the `pypi` GitHub
  environment) — no API token is stored. The version is bumped in lockstep with
  the matching `@peektravel/app-utilities` release, together with `SDK_VERSION`
  and the `changelog.md` heading (see `CLAUDE.md` "Versioning").
