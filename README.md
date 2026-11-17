# peek-app-utilities

The **Python port of [`@peektravel/app-utilities`](https://github.com/peek-travel/app-utilities)**:
an async client library for the Peek "backoffice" API (plus the CNG and ACME
backoffice APIs). The package owns the queries, authentication, transport, and
the conversion into clean Python dataclasses — callers work only with the
high-level `PeekAccessService` and the plain data shapes it returns.

The two packages ship in lockstep: a `peek-app-utilities` release carries the
**same version number** as the `@peektravel/app-utilities` release it mirrors,
with the same resources, models, and behaviour. If you know one, you know the
other — the TypeScript `getBookingService().getById()` is the Python
`get_booking_service().get_by_id()`.

## Install

This package is published to **PyPI**. It requires **Python ≥ 3.11** and has two
runtime dependencies (`httpx` and `PyJWT`).

```bash
pip install peek-app-utilities
# or
uv add peek-app-utilities
```

Before updating to a new version, consult [`changelog.md`](./changelog.md) —
it records every caller-visible change grouped by version, including any
breaking changes and the concrete action you need to take to migrate.

See [Releasing](#releasing) for how new versions are published.

## Usage

The library is **async-only**: every call that touches the network is a
coroutine. Configure one access service per install with everything it needs to
authenticate and reach the API. It mints and caches a short-lived JWT on demand
and hands out per-resource services that own the resource-specific calls.

```python
import os

from peek_app_utilities import PeekAccessService, PeekAccessServiceConfig, Product


async def main() -> None:
    async with PeekAccessService(
        PeekAccessServiceConfig(
            install_id="install-123",  # JWT subject
            jwt_secret=os.environ["PEEK_INTERNAL_SECRET"],  # signs the JWT
            issuer=os.environ["APP_NAME"],  # JWT issuer
            mode="v2",  # connection generation — required (see below)
            api_url=install.api_url,  # per-install base URL from the install webhook (persisted)
        )
    ) as peek:
        products: list[Product] = await peek.get_product_service().get_all_products()
```

The access service is the authenticated root; each `get_<resource>_service()`
returns a (memoized) service that owns that resource's calls. Use it as an async
context manager (or call `await peek.aclose()` when you are done) so the HTTP
client it owns is closed; a client you pass in yourself via `http_client` is
never closed by the package.

### Connection mode (`v1` / `v2`) — **required**

`mode` is a **mandatory** config field — you must choose a connection generation
explicitly. (It used to be optional, defaulting to `v1`; it is now required so
that updating the package forces a deliberate choice instead of silently keeping
the old behaviour. Omitting it fails dataclass construction, and any value other
than `"v1"`/`"v2"` makes the constructor raise `ValueError`.)

- **`mode="v2"`** — **use this going forward.** The app-registry connection. It
  **requires** the install's `api_url` — the per-install base URL delivered on
  the install webhook (`api.url`); the constructor raises `ValueError` without
  it. Persist that URL per install (see [Webhooks](#webhooks)) and pass it as
  `api_url`; no `gateway_key` is needed. If you don't yet have a webhook
  `api_url` (e.g. an older install you don't want to uninstall/reinstall just to
  get one), build one by appending your **app slug** to the registry prefix and
  pass that as the `api_url` yourself —
  `https://apps.peek.com/installations-api/<app-slug>` (same shape as the
  webhook's `api.url`; the trailing app-slug segment is required — the prefix
  alone is not a valid URL). Treat it as a transitional bridge and move to the
  webhook URL.
- **`mode="v1"`** — **deprecated; will be removed.** The legacy gateway; needs
  `app_id` + `gateway_key`. If your install relied on the previous default, the
  fastest no-behaviour-change update is to pass `mode="v1"` — then plan the
  migration to `v2`.

```python
# Legacy v1 (deprecated) — fastest update for an install that used the old default:
peek = PeekAccessService(
    PeekAccessServiceConfig(
        install_id="install-123",
        jwt_secret=os.environ["PEEK_INTERNAL_SECRET"],
        issuer=os.environ["APP_NAME"],
        app_id=os.environ["PEEK_APP_ID"],  # gateway path segment
        gateway_key=os.environ["PEEK_GATEWAY_KEY"],  # pk-api-key header
        mode="v1",
    )
)
```

`get_all_products()` returns a single flat list of activities **and** add-ons
(add-ons tagged with `ADD_ON_PRODUCT_TYPE`), gathering all cursor-paginated
add-on pages for you.

### Targeting an install

Pass the install webhook's `api_url` as the config `api_url` (together with
`mode="v2"`). It is the install's **base API URL**; each service appends its own
routing slug when it makes a call. If the URL you pass already carries this
platform's slug it is stripped back to the base; a URL carrying a *different*
platform's slug is rejected (the constructor raises `ValueError`). `app_id` /
`base_url` are still accepted for the legacy `mode="v1"` route but are
deprecated — prefer `api_url`, or hand the whole install to
[`create_access_service_for_install`](#building-the-access-service-from-an-install),
which sets `mode="v2"` for you.

## Resources

| Accessor | Methods |
| --- | --- |
| `get_product_service()` | `get_all_products()`, `get_all_activities()`, `get_all_rentals()`, `get_all_addons()`, `get_custom_questions(product_id)` |
| `get_account_user_service()` | `get_all()`, `get_by_id(user_id)` |
| `get_resource_pool_service()` | `get_all(mode=None)` |
| `get_timeslot_service()` | `get_for_day(product_id, date, filter=None)`, `get_by_id(timeslot_id)`, `set_availability(timeslot_id, status)`, `set_notes(timeslot_id, manifest_notes)`, `assign_guide(assignment)` |
| `get_reseller_service()` | `get_all_channels(agents_per_channel=None)` |
| `get_promo_code_service()` | `get_all()`, `create(input)` |
| `get_pricing_service()` | `create_engine(input)`, `update_engine(input)`, `delete_engine(engine_id)`, `upsert_overrides(input)`, `clear_overrides(input)` — see [`docs/external/pricing-api.md`](docs/external/pricing-api.md) |
| `get_daily_note_service()` | `get_today()`, `update(note)` |
| `get_availability_service()` | `get_availability_times(query)` |
| `get_membership_service()` | `get_all()`, `purchase(input)` |
| `get_booking_service(integrator=None)` | `get_by_id()`, `search_by_time_range()`, `search_by_timeslot()`, `get_guests()`, `get_meta_data()`, `set_meta_data_*()` (8 field setters), `get_payments_on_file()`, `append_note()`, `set_checkin_status()`, `update_custom_status()`, `cancel()`, `make_payment()`, `refund()`, `create_invoice_link()`, `list_addons()`, `add_addon()`, `remove_addon()`, `create()` |
| `get_review_service()` | `get_reviews(product_id, review_count=50, review_offset=0)`, `get_all_review_summaries()` |
| `get_custom_question_service()` | `get_all()` — every custom question defined on the account, across all activities (`order` is `0` and `is_required` is `False`; definitions, not answers) |
| `get_seatmap_service()` | `get_seatmap_for_product(product_id)` — every seating map on an activity (zones, sections, tables, seats); `get_seatmap_ids_for_product(product_id)` — just each map's `id`/`name`; `get_seat_map_assignments(product_id, range_start, range_end)` — the maps with per-seat occupancy over a datetime range; `assignable_bookings(product_id, range_start, range_end)` — confirmed bookings overlapping the range with their seat-assignable tickets; `assign_tickets_to_seats(assignments)` — bulk ticket→seat assignment (`SUCCESS`/`PARTIAL`/`FAILED`); `delete_seat_assignments(assignment_ids)` — clear seats by `asa_…` id |

> `get_booking_service(integrator=None)` takes an optional `integrator` string
> that scopes `get_meta_data()` results. **Do not set it** unless Peek
> engineering created a custom integrator id for this integration.

Every input and output is a frozen `@dataclass` (keyword-only), so calls read
as `await service.create(CreateBookingInput(activity_id=..., ...))` and results
are plain attribute access (`booking.display_id`). Missing/absent values are
`None`. Monetary values shared across resources — a booking add-on's `total`,
an `AvailabilityTime.price` — use the single exported `Money` dataclass
(`amount` as a decimal string, `currency`, `formatted`).

Seat occupancy reads (`get_seat_map_assignments`, `assignable_bookings`) carry a
`guest_name` that is **customer PII** — it is `None` unless the access service
was created with `full_customer_access` (see [Access options /
PII](#access-options--pii)). Seating-map layouts and custom-question definitions
carry no PII and are unaffected by the flag.

### Optional configuration

| Option | Default | Purpose |
| --- | --- | --- |
| `mode` | **required** | `"v2"` (app-registry connection, needs `api_url`) or `"v1"` (legacy gateway, **deprecated**) — see [Connection mode](#connection-mode-v1--v2--required) |
| `api_url` | — | The install's base API URL (from the install webhook). **Required with `mode="v2"`**; preferred over `base_url`/`app_id` |
| `base_url` | Peek production gateway | Override the legacy v1 gateway base URL (**deprecated**) |
| `app_id` | — | Legacy v1 gateway path segment, required only in `mode="v1"` without `api_url` (**deprecated**) |
| `gateway_key` | — | `pk-api-key` header, required only in `mode="v1"` without `api_url`; not used by `v2` |
| `token_ttl_seconds` | `3600` | JWT lifetime |
| `token_refresh_leeway_seconds` | `60` | Re-mint this long before expiry |
| `retry_delays_ms` | `(1000, 2000, 4000)` | Backoff for HTTP 429 retries |
| `logger` | no-op | Inject a `Logger` for diagnostics — see [Logging](#logging) |
| `http_client` | package-owned `httpx.AsyncClient` | Supply your own client (e.g. for tests or connection pooling); never closed by the package |
| `item_options_page_size` | `50` | Add-on pagination page size |
| `access_options` | `AccessOptions(full_customer_access=False)` | PII exposure — see [Access options / PII](#access-options--pii) |

### Access options / PII

Every access service accepts `access_options: AccessOptions | None` — today a
single flag, `full_customer_access` (default `False`). It is an object so future
cross-cutting flags can be added without breaking signatures.

With `full_customer_access` **off** (the default):

- **Customer PII is never requested** (the queries omit the fields, so they come
  back `None`/empty): booking guest identity (name/email/phone/DOB/postal
  code/GDPR + custom field responses — guests keep only ids and
  participation/opt-in flags), booking custom question answers, the customer
  `portal_url`, the guest identity fields inside booking metadata, review
  reviewer `customer_name`/`customer_email`, and the primary-guest `guest_name`
  on seat occupancy reads (`get_seat_map_assignments` / `assignable_bookings`;
  staff names are not gated). Waiver webhooks (a fixed payload
  with no query to trim) instead have `guest_name` (→ `None`) and `file_url`
  (→ `""`) redacted at parse time.
- **Payment / booking-modification operations are disabled** —
  `get_payments_on_file`, `make_payment`, `refund`, `create_invoice_link`,
  `add_addon`, and `remove_addon` raise `PiiAccessDisabledError` before any
  request. `create` (including `mark_as_paid`) and non-payment reads/mutations
  remain available.

```python
from peek_app_utilities import AccessOptions, PeekAccessService, PeekAccessServiceConfig

peek = PeekAccessService(
    PeekAccessServiceConfig(
        install_id=install_id,
        jwt_secret=jwt_secret,
        issuer=issuer,
        mode="v2",
        api_url=api_url,
        access_options=AccessOptions(
            full_customer_access=True
        ),  # opt into PII + payment operations
    )
)
```

### Logging

The package writes diagnostics to a small `Logger` protocol (`info` / `warn` /
`error`, each taking a message and an optional context mapping). It is silent by
default (`noop_logger`). To route it into the standard library, wrap any
`logging.Logger` with `logging_adapter` — the context mapping is passed as
`extra={"context": {...}}`:

```python
import logging

from peek_app_utilities import logging_adapter

config = PeekAccessServiceConfig(..., logger=logging_adapter(logging.getLogger("peek")))
```

### Errors

Three kinds of failures surface as exceptions.

**Typed package errors** (importable; every one derives from
`AppUtilitiesError`, so `except AppUtilitiesError` catches anything the package
raises on its own):

- `AdminAccountRequiredError` — the API returned HTTP 418 (install lacks admin
  rights). Carries `.status_code == 418`.
- `RateLimitError` — HTTP 429 after the configured `retry_delays_ms` backoff was
  exhausted. Carries `.status_code == 429`.
- `PeekGraphQLError` — the response contained a GraphQL `errors` array (a
  resolver-level failure), preserved on `.graphql_errors`.
- `PeekHttpError` — the Peek API returned a non-2xx status (other than 418/429)
  with no GraphQL `errors` array — a transport-level failure such as `401`
  (auth/secret wrong), `404` (wrong app id / not provisioned), or `5xx`. Carries
  `.status_code`, `.url`, and the raw `.body` (parsed JSON when possible,
  otherwise the response text), so a non-JSON error page reports its real
  status instead of a decode error.
- `PiiAccessDisabledError` — a payment / booking-modification operation was
  called on an access service created without `full_customer_access` (see
  [Access options / PII](#access-options--pii)). Carries `.operation` (the
  blocked method name, e.g. `"make_payment"`).
- `InstallWebhookError` — `parse_install_webhook` got a validly signed token
  but rejected the delivery: the token has no `sub`
  (`.reason == "missing_subject"`), the body `install_id` is not equal to it
  (`.reason == "install_id_mismatch"`), or the body `api_url` is not a
  Peek-owned domain (`.reason == "invalid_api_url"`). It also subclasses PyJWT's
  `jwt.InvalidTokenError`, so an `except jwt.InvalidTokenError` branch catches
  it too. Respond `401`.
- `UnknownSeatmapDisplayTypeError` / `UnknownSeatmapBlockStatusError` /
  `UnknownSeatmapAssignmentParentError` — a seatmap read returned a
  `display.type`, seat status, or assignment parent outside the known set
  (`SEATMAP_DISPLAY_TYPES` / `SEATMAP_BLOCK_STATUSES` / the known parent types);
  the offending value is on `.type` / `.status` / `.typename`. Catch one if you
  need to tolerate a newly-added kind.
- `SeatmapDeleteError` — `delete_seat_assignments` got a batch-level failure
  back from the API; its explanation is the message.
- `CngApiError` / `CngPermissionError` / `AcmeApiError` — the CNG and ACME
  equivalents; see [CNG and ACME](#cng-and-acme).

**Token verification failures** come from PyJWT, not from the package:
`verify_peek_auth_token` and `parse_install_webhook` raise a
`jwt.InvalidTokenError` subclass (`ExpiredSignatureError`,
`InvalidSignatureError`, `InvalidIssuerError`, `InvalidAudienceError`,
`DecodeError`, …) on a bad token (and `parse_install_webhook` raises the
package's `InstallWebhookError`, itself a `jwt.InvalidTokenError`, when a
verified token does not name the delivered install). Once a token's signature verifies, claim
*extraction* never raises: the whole `user` block may be absent
(`claims.user is None`) and every field inside it is independently nullable,
with a sentinel value (`""` or `"null"`) normalized to `None`. `user.id` is the
signed-in person's own id — not an account or partner id — so its absence is
not an error.

**`ValueError` validation/precondition failures** raised by the service layer
*before* any network call — e.g. an empty config field, a `booking_id` that is
not a `b_…`/`B-…` id, a non-positive-integer `quantity`, a malformed currency,
or a "booking not found". Branch on the message only as a last resort; prefer
guarding inputs to the documented formats below.

```python
from peek_app_utilities import (
    AdminAccountRequiredError,
    PeekGraphQLError,
    PeekHttpError,
    RateLimitError,
)

try:
    await peek.get_booking_service().make_payment(payment)
except RateLimitError:
    ...  # back off and retry later
except AdminAccountRequiredError:
    ...  # this install can't perform admin-only operations
except PeekHttpError as err:
    log.error("%s %s %r", err.status_code, err.url, err.body)  # which config is wrong
except PeekGraphQLError as err:
    log.error("%r", err.graphql_errors)  # raw API errors
except ValueError:
    raise  # validation / precondition failure
```

## Conventions & input formats

These rules are enforced in the service layer (a violation raises `ValueError`
before any request):

- **Booking ids** must be a lowercase db id (`b_abc123`) or an uppercase display
  id (`B-ABC123`); they are normalized internally (lowercased with `-` → `_`),
  so the two forms are equivalent. Order ids follow the same rule with an `o`
  prefix.
- **Quantities** (add-ons, etc.) are **positive-integer strings**: `"1"`, `"2"`.
- **Currency** is a 3-letter uppercase ISO code: `"USD"`, `"EUR"`.
- **Amounts** are numeric strings: `"25.00"`.
- **Payment source ids** are `ps_…`, or one of `cash/cash`, `custom/other`,
  `custom/voucher`. **Payment ids** (refunds) are `pmt_…`.
- **Idempotency keys** are required on `make_payment`, `refund`, and any
  `create(...)` with `mark_as_paid=True`; pass a stable UUID (`str(uuid4())`).
- **`create()` takes pre-resolved ids only** — no free-text matching. Resolve
  `activity_id` + ticket `resource_option_id`s from `get_product_service()` and
  `availability_time_id` from `get_availability_service()`. The one exception is
  `custom_question_answers` (`CustomQuestionAnswerInput(question_id_or_text,
  value)`): the activity's custom questions are fetched and each answer is
  matched by id or lenient text and validated by question type before the
  booking is created.
- **Add-on option ids** are ticket ids on products whose `type` is
  `ADD_ON_PRODUCT_TYPE`.
- **`create()` with `parent_order_id`** (`o_…`/`O-…`) attaches the new booking
  to that **existing** order instead of creating a new one: the returned
  `CreatedBooking.order_id` is the id you passed, and `booking_id` /
  `display_id` / `balance_*` describe the newly added booking (`mark_as_paid`
  charges that booking's own balance, not the order total).
- **`create()` with `promo_code`** applies a discount code to the new booking's
  quote (the API validates and prices it); an empty/whitespace-only value sends
  none. It **cannot** be combined with `parent_order_id` — attaching to an order
  creates no new quote, so `create` raises `ValueError` rather than silently
  dropping the code.
- **Seat assignment ids:** `assign_tickets_to_seats` takes `assignable_id`s
  prefixed `t_` (a ticket's `hashid`) and `block_id`s prefixed `csb_`;
  `delete_seat_assignments` takes `asa_…` ids. Each list must be non-empty.
  `range_start`/`range_end` on the occupancy reads are naive datetimes
  (`YYYY-MM-DDTHH:MM[:SS]`; a timezone or fractional seconds is stripped), sent
  half-open `[start, end)`, and must fall on the same date.

## Recipes

**Find an activity and its add-ons**

```python
from peek_app_utilities import ADD_ON_PRODUCT_TYPE

products = await peek.get_product_service().get_all_products()
activities = [p for p in products if p.type != ADD_ON_PRODUCT_TYPE]
addons = [p for p in products if p.type == ADD_ON_PRODUCT_TYPE]
```

**Create a paid booking end-to-end**

```python
from uuid import uuid4

from peek_app_utilities import (
    AvailabilityTimesQuery,
    CreateBookingGuest,
    CreateBookingInput,
    CreateBookingTicket,
    ResourceOptionQuantity,
)

products = await peek.get_product_service().get_all_products()
activity = next(p for p in products if p.name == "Sunset Kayak Tour")
ticket = activity.tickets[0]

slot, *_ = await peek.get_availability_service().get_availability_times(
    AvailabilityTimesQuery(
        activity_id=activity.product_id,
        date="2026-06-20",
        resource_option_quantities=[
            ResourceOptionQuantity(resource_option_id=ticket.id, quantity=2)
        ],
    )
)

created = await peek.get_booking_service().create(
    CreateBookingInput(
        activity_id=activity.product_id,
        availability_time_id=slot.id,
        tickets=[CreateBookingTicket(resource_option_id=ticket.id, quantity=2)],
        guest=CreateBookingGuest(name="Sam Rivera", email="sam@example.com"),
        mark_as_paid=True,
        idempotency_key=str(uuid4()),
    )
)
print(created.booking_id, created.balance_formatted)
```

**Add an add-on to an existing booking**

```python
from peek_app_utilities import AddAddonInput

result = await peek.get_booking_service().add_addon(
    "b_abc123", AddAddonInput(addon_option_id="io_helmet", quantity="2")
)
addons = result.updated_booking_addons
```

**Look up a booking with guests and balance**

```python
from peek_app_utilities import BookingReadOptions

booking = await peek.get_booking_service().get_by_id(
    "b_abc123", BookingReadOptions(include_guests=True, include_price_breakdown=True)
)
if booking is not None:
    print(booking.display_id, booking.outstanding_balance_display)
```

## CNG and ACME

Two sibling access services sit alongside `PeekAccessService` for the **CNG**
and **ACME** backoffices. They share the same config shape (minus the Peek-only
`gateway_key` / `mode` / `item_options_page_size`), the same auth, the same
`aclose()` / `async with` lifecycle, and the same `Logger`, and are deliberately
minimal today (products only):

```python
from peek_app_utilities import (
    AcmeAccessService,
    AcmeAccessServiceConfig,
    CngAccessService,
    CngAccessServiceConfig,
)

async with CngAccessService(
    CngAccessServiceConfig(install_id=..., jwt_secret=..., issuer=..., api_url=install.api_url)
) as cng:
    activities = await cng.get_product_service().get_all_activities()  # list[Activity]

async with AcmeAccessService(
    AcmeAccessServiceConfig(install_id=..., jwt_secret=..., issuer=..., api_url=install.api_url)
) as acme:
    activities = await acme.get_product_service().get_all_activities()  # list[AcmeActivity]
```

- **CNG** returns `Activity` records (`product_id`/`name`/`color`; `type` is
  always `"ACTIVITY"` and `tickets` is always empty, as the CNG products
  endpoint exposes neither). Only active products are returned. Failures raise
  `CngApiError`, except a missing app permission (HTTP 403), which raises
  `CngPermissionError` — `.permissions` lists the permission names (e.g.
  `["products:read"]`), and it is logged at `warn` because a misconfigured
  install is expected rather than a fault.
- **ACME** returns `AcmeActivity` records (published event templates only;
  `tickets` is always empty). Failures raise `AcmeApiError`.

`AdminAccountRequiredError` and `RateLimitError` apply to all three platforms.
`access_options` is accepted by CNG/ACME for a uniform config shape but is inert
there — they have no PII surface.

### Building the access service from an install

A persisted install carries the two facts needed to reach it: `platform` picks
the access service class, and `api_url` is its endpoint.
`create_access_service_for_install` encodes that mapping:

```python
from peek_app_utilities import InstallAccessConfig, create_access_service_for_install

install = await installs.get(install_id)  # anything with .platform, .api_url, .install_id

service = create_access_service_for_install(
    install,
    InstallAccessConfig(
        jwt_secret=os.environ["PEEK_INTERNAL_SECRET"],
        issuer=os.environ["APP_NAME"],
        # gateway_key=, logger=, http_client=, access_options=, … (per-app, not per-install)
    ),
)
# → PeekAccessService | CngAccessService | AcmeAccessService, wired to install.api_url.
# Narrow by install.platform (or isinstance) to reach a platform-specific surface.
```

It raises `ValueError` when `install.platform` is `None` or unrecognised — an
install with an unknown platform has no service to route to, and silently
defaulting would point it at the wrong platform. Any object with `platform`,
`api_url`, and `install_id` attributes satisfies the `InstallAccessTarget`
protocol, so a parsed `InstallWebhook` or your own install record both work.
For a `"peek"` install the factory sets the required `mode="v2"` for you (a
registry install is always the v2 connection), so `InstallAccessConfig` carries
no `mode`.

## Webhooks

Receiver apps can consume Peek **booking**, **waiver**, and **install** webhooks
without hand-writing the payload handling. The booking and waiver webhooks have a
pure parser (construct nothing — no auth/network) that returns a clean model; the
install webhook delivers a signed token alongside a JSON body, so its helper
**verifies** the token before merging the two. The examples below use FastAPI,
but the parsers only need the raw body (a mapping or a JSON string):

```python
import os

import jwt
from fastapi import FastAPI, Header, Request, Response

from peek_app_utilities import (
    AccessOptions,
    Booking,
    InstallWebhook,
    Waiver,
    parse_booking_webhook,
    parse_install_webhook,
    parse_waiver_webhook,
)

app = FastAPI()


@app.post("/booking-webhook")
async def booking_webhook(request: Request) -> Response:
    booking: Booking = parse_booking_webhook(await request.json())
    return Response(status_code=200)


@app.post("/waiver-webhook")
async def waiver_webhook(request: Request) -> Response:
    # guest_name / file_url are redacted unless you opt into PII:
    waiver: Waiver = parse_waiver_webhook(
        await request.json(), AccessOptions(full_customer_access=True)
    )
    return Response(status_code=200)


@app.post("/install-webhook")
async def install_webhook(request: Request, x_peek_auth: str = Header("")) -> Response:
    try:
        # The token rides in the `x-peek-auth` header (a `Bearer ` prefix is stripped for you):
        event: InstallWebhook = parse_install_webhook(
            x_peek_auth, await request.json(), os.environ["PEEK_INTERNAL_SECRET"]
        )
    except jwt.InvalidTokenError:
        # bad token, or the body names another install / a non-Peek api_url
        # (InstallWebhookError is a jwt.InvalidTokenError too)
        return Response(status_code=401)

    match event.status:
        case "installed":
            await provision(event)
        case "uninstalled":
            await deprovision(event)
        case "update_installed":
            await record_version(event)
        case _:
            # `status` is None when Peek sends one this version doesn't know. Peek
            # doesn't redeliver a 2xx, so fail loudly rather than silently no-op.
            return Response(status_code=500, content=f"unknown status: {event.raw_status}")
    return Response(status_code=200)
```

The booking and waiver parsers tolerate the delivery envelope / a bare node / a
JSON string and never raise on malformed input; **authenticating those deliveries
is the receiver's job**. `parse_waiver_webhook` also takes an optional
`AccessOptions` and redacts the participant `guest_name` (→ `None`) + document
`file_url` (→ `""`) by default — see [Access options / PII](#access-options--pii)
above.

`parse_install_webhook(token, body, secret)` is different: the delivery carries a
signed `app_registry_v2` JWT plus a JSON body. Peek sends the token in the
`x-peek-auth` header — pass that value straight in (`token` accepts it with or
without a `Bearer ` prefix). It validates the HMAC signature, expiry, issuer,
and `"Joken"` audience (the same checks as `verify_peek_auth_token`, raising the
underlying PyJWT `jwt.InvalidTokenError` subclass), then returns one flat,
JSON-safe `InstallWebhook`: `install_id`, `account_id` (**also called the
partner ID**), `account_name`, `platform`, `is_test`, `timezone`, `api_url`,
`status`, `raw_status`, `display_version`, and a **nullable** `user`.
**`install_id` is always the token `sub`**: a body `install_id` that is present
and not equal to it raises `InstallWebhookError`, and so does a token with no
`sub`. A non-empty `api_url` whose host is not a Peek-owned domain (`peek.com` /
`peeklabs.com`, or a subdomain) raises `InstallWebhookError` as well. The **JSON
body is the source of the other event data**; the fields it shares with the
token (`account_id` / `status` / `display_version` / `user`) fall back to the
**verified token** when the body omits them. This webhook is the only source of
`account_id`, `timezone`, and `api_url` in the package, since no API read
returns them — **persist them per install**. `api_url` is the install's **base
API URL**: pass it straight through (don't reconstruct it from `app_id`) as the
access service's `api_url` with `mode="v2"` — or hand the whole install to
`create_access_service_for_install(install, config)`, which picks the service by
`platform`, sets `mode="v2"`, and wires the endpoint for you. Every event is a
**full snapshot** — an `update_installed` carries the same fields as the
original `installed`, so upsert by `install_id` and take the latest `api_url`.
`status` and `platform` are **nullable** — a value this version doesn't
recognise stays `None` (wire value on `raw_status`) instead of being coerced, so
a newer registry can't be mistaken for an older one.

The booking and waiver webhooks differ on registration: a **booking** webhook's
payload shape is set by a GraphQL query configured **once in an external system**
(the App Store `broadcast_to_url` config) — this package documents and
drift-guards the exact query to paste there — whereas the **waiver** and
**install** webhooks have fixed payloads, so you just subscribe to their event
with no query. **The query to register and the full guide:
[`docs/webhooks.md`](docs/webhooks.md) (shipped).**

## Relationship to `@peektravel/app-utilities`

This package tracks the TypeScript package one-to-one: same resources, same
models, same behaviour, same version number. The naming is mechanical —
`camelCase` methods and fields become `snake_case`, class names are unchanged,
`null` becomes `None`, and every I/O method is `async`. Two deliberate
differences:

- The TypeScript package's `@deprecated` compatibility shims (the top-level
  short-form proxies such as `peek.getAllProducts()`, `verifyInstallWebhook`,
  the `AddAddonInput.addonId` alias, and the `BookingAddonMoney` alias of
  `Money`) are **not** carried over — this is a new package with no existing
  consumers. Reach everything through the service accessors and
  `parse_install_webhook`, and use `Money` for every money value.
- The TypeScript package's browser UI components (`/ui`) are not part of the
  Python port.

The same `changelog.md` is also rendered as an interactive page,
[`docs/html/changelog.html`](docs/html/changelog.html) (generated from the
Markdown by `scripts/build-changelog-html.mjs` — never edited by hand), linked
alongside the service/model reference pages from `docs/index.html`.

## Releasing

Releases are automated. Pushing a `v*` git tag (e.g. `v1.3.0`) triggers
`.github/workflows/publish.yml`, which asserts the tag matches the
`pyproject.toml` version, builds the sdist + wheel, and publishes to PyPI via
Trusted Publishing (OIDC) — no API token is stored. The version is bumped in
lockstep with the matching `@peektravel/app-utilities` release.

To cut a release, set `project.version` in `pyproject.toml` (and the
`SDK_VERSION` literal that feeds the outbound `x-peek-sdk: py-<version>` header;
a test guards the two against drifting), rename the `## Unreleased` section of
`changelog.md`, commit, then:

```bash
git tag v1.3.0
git push --follow-tags   # the workflow publishes
```

> One-time setup: register this repository and the publish workflow as a trusted
> publisher for the `peek-app-utilities` project on pypi.org, and create the
> `pypi` environment in the repository settings.

## Development

```bash
uv sync --group dev          # create .venv and install everything
uv run ruff check .          # lint   (ruff check --fix to autofix)
uv run ruff format .         # format
uv run mypy                  # strict type-check (src, tests, scripts)
uv run pytest                # unit tests
uv run pytest --cov          # tests + the 95% coverage gate (lines and branches)
uv build                     # sdist + wheel into dist/
```

CI (`.github/workflows/ci.yml`) runs lint, format check, mypy, the test suite
with the coverage gate, and the build on Python 3.11, 3.12, and 3.13 for every
push to `main` and every pull request.

## Project layout

```
src/peek_app_utilities/        library source (public API barrel: __init__.py)
src/peek_app_utilities/internal/   queries, converters, services, transport (not public)
src/peek_app_utilities/models/     the clean dataclass models (peek/, cng/, acme/)
tests/                         pytest suite (fakes in tests/conftest.py)
scripts/gql_cli/               developer CLI against the live API (not packaged)
docs/webhooks.md               webhook consumer guide (shipped)
docs/external/pricing-api.md   pricing overrides guide
docs/html/                     interactive reference pages + the generated changelog.html
docs/internal/                 maintainer docs (ARCHITECTURE.md, CONVENTIONS.md — not shipped)
scripts/build-changelog-html.mjs   renders changelog.md → docs/html/changelog.html (Node)
llms.txt                       AI-agent quickstart (shipped in the sdist)
```
