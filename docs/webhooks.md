# Webhooks

A guide for wiring a receiver app up to Peek "backoffice" webhooks using
`peek-app-utilities`. Three webhook types are supported today — **booking**,
**waiver**, and **install** — and each has a helper that turns the delivered
payload into a clean data model. They differ in one important way: a booking
webhook is configured with a GraphQL query (so the package documents the exact
query to register), a waiver webhook has a fixed payload (so there's nothing to
register beyond subscribing to the event), and an install webhook delivers a
**signed token alongside a JSON body** (so the helper *verifies* the token before
merging the two).

| Webhook | Register | Handle the delivery |
| --- | --- | --- |
| Booking | paste a GraphQL query into the external config (below) | `parse_booking_webhook(body)` → `Booking` |
| Waiver | subscribe to the event — **no query needed** | `parse_waiver_webhook(body)` → `Waiver` |
| Install | subscribe to the event — **no query needed** | `parse_install_webhook(token, body, secret)` → `InstallWebhook` |

The booking and waiver parsers are pure transforms — no auth, no network,
construct nothing; **authenticating those deliveries is the receiver's job**. The
install webhook is different: it carries a signed JWT, so `parse_install_webhook`
checks the signature for you before returning the merged event.

**The install webhook delivers two payloads at once.** A signed
`app_registry_v2` JWT authenticates the notification; a plain JSON body alongside
it carries the **event data** — the full account block (name, platform,
timezone, test flag), the per-install `api.url`, the acting user, and the install
id / status / version. `parse_install_webhook` verifies the token and reads the
event from the body — falling back to the token for the fields it also carries —
merging both into one flat `InstallWebhook`, so you make a single call.

All three parsers are plain synchronous functions (no `await`) that accept the
raw request body as a mapping or a JSON string. The examples below use FastAPI
for the receiver, but nothing in the package depends on a framework.

# Booking webhooks

## The problem this solves

A Peek booking webhook is unusual: its payload shape is **not fixed**. The
webhook is configured with a GraphQL field selection (`output_fields_gql_query`);
each time it fires, Peek runs that selection against the booking and POSTs the
result to your receiver. So two things must agree — the registered selection and
the code that parses the payload.

That registration is done **once, in an external system** (the Peek App Store
`broadcast_to_url` config / your app's `app.json`), not from your application
code. So the two halves split cleanly:

| Half | Where it lives | This package provides |
| --- | --- | --- |
| Register the query | external config, set once | the canonical query string to paste (below) |
| Parse the delivery | your receiver's code | `parse_booking_webhook(body)` → a clean `Booking` |

The query string below and the parser are derived from the **same** field
selection this package uses for booking reads, and a test pins the string, so the
two can't silently drift. It is byte-for-byte the same selection the TypeScript
`@peektravel/app-utilities` documents — one registration serves a receiver
written in either language.

## Step 1 — register this query (external, one-time)

Paste the following into the webhook's `output_fields_gql_query` field (with
`output_format: "gql"`). It is the **maximal** selection — it includes guests and
the full price breakdown, so one registration captures everything; the parser
auto-detects whatever a given payload carries.

```
{ displayId id primaryGuest { name email phone optinMarketing optinSms isGdpr postalCode } activitySnapshot { type name id } ticketQuantities { quantity resourceOptionSnapshot { name id } } reservationStatus checkinStatus returnStatus fulfillmentStatusOverride { status } timeSnapshot { id legacyId } purchasedAt purchasedAtUtc startsAt startsAtUtc endsAt endsAtUtc availabilityTimeId bookingPortalUrl operatorNotes operatorStatus value { convenienceFee { amount formatted } deposit { amount formatted } discount { amount formatted } discountedPrice { amount formatted } fees { amount formatted } flatPartnerFee { amount formatted } price { amount formatted } retailPrice { amount formatted } taxes { amount formatted } tips { amount formatted } total { formatted amount } } balance { total { amount formatted } } tips { price { amount formatted } } order { displayId id promoCodes { code } channelSnapshot { id name agent { name } } initialQuote { source { actor { app name } } } } questionAnswers { answer questionText questionLocationSnapshot { latitude longitude } } tickets { questionAnswers { answer questionText } } resourcePoolAssignments { quantity resourcePool { name shortName resources { name } } resourceAssignments { resource { id name } } } bookingGuests { id name country dateOfBirth email isGdpr isParticipant optinSms optinMarketing phone postalCode fieldResponses { id text fieldLocation { field { name } } } } primaryGuest { id name country dateOfBirth email isGdpr isParticipant optinSms optinMarketing phone postalCode fieldResponses { id text fieldLocation { field { name } } } } }
```

> This package owns this string internally and snapshots it in
> `tests/peek/bookings/test_booking_webhook.py`. If the booking fields ever
> change, the test fails here first — update the test snapshot, this doc, and the
> external config together.

## Step 2 — parse the delivered webhook into a `Booking`

This is the only part that lives in your code. Hand the raw request body to
`parse_booking_webhook`; it returns the same clean
[`Booking`](../README.md#resources) model the read services return.

```python
from fastapi import FastAPI, Request, Response

from peek_app_utilities import Booking, parse_booking_webhook

app = FastAPI()


@app.post("/booking-webhook")
async def booking_webhook(request: Request) -> Response:
    booking: Booking = parse_booking_webhook(await request.json())
    # booking.booking_id, booking.customer_name, booking.starts_at, booking.is_canceled, …
    return Response(status_code=200)
```

`parse_booking_webhook`:

- **Needs no auth, network, or `PeekAccessService`** — it is a pure transform.
  Construct nothing; just call it. (This is why it's a standalone function, not a
  method on the access service, and why the receiver needs no API credentials to
  parse.)
- **Tolerates the delivery envelope.** It accepts the `{"booking": …}` wrapper
  the webhook sends, a bare booking node, or a JSON string body.
- **Auto-detects** guests and the price breakdown from the payload, so there is
  nothing to keep in sync with the registered query — `booking.guests` and
  `booking.taxes`/`booking.fees`/… populate when present.
- **Never raises on malformed input** — a missing/garbled body yields a `Booking`
  with empty fields rather than an exception, so a bad delivery can't crash your
  handler.

## Notes

- The webhook fires on booking **create** and **update**; both deliver the same
  booking payload, and `parse_booking_webhook` handles them identically. It does
  not currently surface which event fired.
- Authenticating the delivery (verifying it really came from Peek) is the
  receiver's responsibility and out of scope for this parser.
- A booking webhook carries whatever its registered selection includes;
  `parse_booking_webhook` applies no PII redaction (there is no access service to
  inherit `full_customer_access` from). Register a narrower selection if the
  receiver must not see guest identity.

# Waiver webhooks

A waiver webhook fires when a participant signs a liability agreement. Unlike the
booking webhook, its payload is **fixed** — Peek delivers a predefined shape (the
`waiver_webhook_data` output format), so there is **no GraphQL query to
register**.

## Step 1 — subscribe to the event (external, one-time)

Register the webhook for the `agreement_signature_created` event in the external
config. Leave `output_fields_gql_query` null; the `output_format` is
`waiver_webhook_data`. There is nothing query-shaped to paste.

## Step 2 — parse the delivered webhook into a `Waiver`

```python
from fastapi import FastAPI, Request, Response

from peek_app_utilities import AccessOptions, Waiver, parse_waiver_webhook

app = FastAPI()


@app.post("/waiver-webhook")
async def waiver_webhook(request: Request) -> Response:
    # PII (guest_name, file_url) is redacted unless you opt in:
    waiver: Waiver = parse_waiver_webhook(
        await request.json(), AccessOptions(full_customer_access=True)
    )
    # waiver.booking_id, waiver.template_id, waiver.file_url, waiver.signed_at,
    # waiver.guest_name, waiver.is_signed_by_guardian, …
    return Response(status_code=200)
```

`parse_waiver_webhook` mirrors the booking parser: a pure transform (no
auth/network/`PeekAccessService`), it tolerates the `{"waiver": …}` envelope / a
bare node / a JSON string, maps the raw `snake_case` payload to the clean
[`Waiver`](#waiver-webhooks) model, and never raises on malformed input (missing
fields become `""` / `None` / `False`).

**PII:** `parse_waiver_webhook(body, options=None)` takes the same
`AccessOptions` as the access services. By **default** (`full_customer_access`
unset/`False`) the participant `guest_name` is redacted to `None` and the
signed-document `file_url` to `""`; pass `AccessOptions(full_customer_access=True)`
to keep them. The booking parser `parse_booking_webhook(body)` is unaffected — a
booking webhook carries whatever its registered selection includes.

The resulting `Waiver` is flat:

| Field | Type | From |
| --- | --- | --- |
| `template_id` | `str` | `agreement_template_id` |
| `booking_id` | `str` | `booking_id` |
| `file_url` | `str` | `file_url` (`""` unless `full_customer_access`) |
| `signed_at` | `str` | `signed_at` (ISO) |
| `is_signed_by_guardian` | `bool` | `signed_by_guardian` |
| `guest_name` | `str \| None` | `waiver_data.participant_name` (`None` unless `full_customer_access`) |
| `is_optin_marketing` | `bool` | `waiver_data.participant_optin_marketing` |
| `is_optin_sms` | `bool` | `waiver_data.participant_optin_sms` |

Authenticating the delivery is the receiver's responsibility, as with bookings.

# Install webhooks

## The problem this solves

Peek's app registry notifies your app of install lifecycle changes — installed,
uninstalled, updated — with a single POST that carries **two payloads at once**:
a **signed `app_registry_v2` JWT** and a plain **JSON body**.

- The **JWT** is the security boundary. Verifying its signature proves the
  notification really came from Peek before your app acts on it (for example,
  de-provisioning an uninstall) — it authenticates the whole delivery, body
  included.
- The **JSON body** is the event payload. It carries the full account block
  (name, platform, timezone, test flag), the per-install `api.url`, the acting
  user, and the install id / status / version.

This webhook is also where an app first learns **who the install belongs to** —
and the only place it ever learns it: no API read returns the account id, so
whatever you persist from this delivery is all you will ever have.

`parse_install_webhook(token, body, secret)` verifies the token (issuer, audience,
expiry, HMAC — the security-critical boilerplate you'd otherwise hand-roll) and
reads the event from the body, **falling back to the token** for the fields it
also carries (`install_id`, `account_id`, `status`, `display_version`, `user`),
returning one flat, JSON-safe `InstallWebhook` you store as a unit.

## Step 1 — subscribe to the event (external, one-time)

Nothing to register in code: subscribe your endpoint to the install event in the
App Store config. There is no GraphQL selection to paste.

## Step 2 — verify and parse the delivery

Peek delivers the signed token in the **`x-peek-auth` request header**. Pass that
header value as-is, along with the JSON body and your app's signing secret (the
same `jwt_secret` you construct `PeekAccessService` with — conventionally
`PEEK_INTERNAL_SECRET`), to `parse_install_webhook`. You do **not** need to strip a
`Bearer ` prefix: `parse_install_webhook` tolerates the header value with or
without it.

```python
import os

import jwt
from fastapi import FastAPI, Header, Request, Response

from peek_app_utilities import InstallWebhook, parse_install_webhook

app = FastAPI()


@app.post("/webhooks/install")
async def install_webhook(request: Request, x_peek_auth: str = Header("")) -> Response:
    try:
        # `x-peek-auth` carries the token (a `Bearer ` prefix, if any, is stripped for you):
        event: InstallWebhook = parse_install_webhook(
            x_peek_auth, await request.json(), os.environ["PEEK_INTERNAL_SECRET"]
        )
    except jwt.InvalidTokenError:
        return Response(status_code=401)  # signature/issuer/audience/expiry failed

    match event.status:
        case "installed":
            await provision(event)
        case "uninstalled":
            await deprovision(event)
        case "update_installed":
            await record_version(event)
        case _:
            # Peek sent a status this package version does not know. Fail loudly —
            # a 2xx here is a silently dropped lifecycle transition.
            return Response(status_code=500, content=f"unknown status: {event.raw_status}")

    return Response(status_code=200)
```

`parse_install_webhook` validates the HMAC signature, the token expiry, the
`"app_registry_v2"` issuer, and the `"Joken"` audience — the same checks as
[`PeekAccessService.verify_peek_auth_token`](../README.md#errors). It raises the
underlying PyJWT error — a `jwt.InvalidTokenError` subclass such as
`ExpiredSignatureError`, `InvalidSignatureError`, `InvalidIssuerError`,
`InvalidAudienceError`, or `DecodeError` — on any verification failure, so a
single `except jwt.InvalidTokenError` → `401` covers every bad-token case. The
signature checks are strict (they are the security boundary); claim *extraction*
is defensive, so a validly-signed token or a missing/garbled body yields empty
fields rather than raising.

The resulting `InstallWebhook` is flat:

| Field | Type | Source | From | Notes |
| --- | --- | --- | --- | --- |
| `install_id` | `str` | body → token | `install_id` / `sub` | Peek-assigned install UUID |
| `account_id` | `str` | body → token | `account.id` | **also called the partner ID** |
| `account_name` | `str` | body | `account.name` | partner display name; `""` when absent |
| `platform` | `PeekPlatform \| None` | body | `account.platform` | **persist per install** — see below; `None` when unrecognised |
| `is_test` | `bool` | body | `account.is_test` | defaults to `False` |
| `timezone` | `str` | body | `account.timezone` | IANA zone (e.g. `America/New_York`); **persist per install**; `""` when absent |
| `api_url` | `str` | body | `api.url` | per-install backoffice API base URL; **persist per install**; `""` when absent |
| `status` | `InstallStatus \| None` | body → token | `status` | `None` when unrecognised — see below |
| `raw_status` | `str` | body → token | `status` | always the wire value, for logging |
| `display_version` | `str` | body → token | `display_version` | `""` when absent |
| `user` | `PeekAuthTokenUser \| None` | body → token | `modified_by` / `user` | `None` for system-initiated events |

The **JSON body is the source of the event data**; the fields it shares with the
token (`install_id`, `account_id`, `status`, `display_version`, `user`) fall back
to the **verified token** when the body omits them. The token authenticates the
whole delivery — only Peek can mint a valid one — so the body is trusted within a
verified request. `user` is nullable here — as it is on `verify_peek_auth_token`
— because install lifecycle events are often system-initiated (no acting user),
so the parser tolerates a missing `modified_by`/`user`, and every field inside a
present `user` is itself nullable (a sentinel `""`/`"null"` id becomes `None`).

> **Coming from the TypeScript package?** Its deprecated `verifyInstallWebhook`
> (token only, no account name/platform/test flag) was not ported;
> `parse_install_webhook(token, body, secret)` is the only entry point here, and
> the return is flat — read `event.account_id` directly.

## Persist `platform` per install

`event.platform` is not cosmetic. It decides which APIs the install is served by,
and therefore which access service you construct for it:

| `platform` | Access service | Backoffice |
| --- | --- | --- |
| `"peek"` | `PeekAccessService` | Peek |
| `"cng"` | `CngAccessService` | CNG |
| `"acme"` | `AcmeAccessService` | ACME |

Two installs of the same app can sit on different platforms, so this cannot be
inferred from app-level config — it is per install, it has no source other than
this event, and it must be stored alongside `install_id` and `account_id`.

## Also persist `timezone` and `api_url` per install

Like `platform`, these are per-install facts with **no source other than this
event**, so persist them alongside `install_id`/`account_id`:

- **`timezone`** — the account's IANA zone (e.g. `America/New_York`). Downstream
  date/time handling for the install (scheduling, day boundaries, display) needs
  the account's own zone, not the server's.
- **`api_url`** — the **base API URL** the registry serves this install from.
  Store it and pass it straight through as the access service's **`api_url`**: do
  not decompose it or append your own app id. Each service class appends its own
  backoffice slug (e.g. `peek_backoffice_api-v1`) when it makes a call, so a Peek
  call goes to `<base>/peek_backoffice_api-v1` and a CNG/ACME call to
  `<base>/<slug>/<path>`. If the URL you pass already carries this platform's
  slug (dashes or underscores) it is stripped back to the base; a URL carrying a
  *different* platform's slug makes the constructor raise `ValueError`. If the
  registry tags traffic with an app id in the path, that is the registry's
  concern and opaque to you. Or hand the whole install to
  `create_access_service_for_install` (below), which wires it for you.

Both default to `""` when a delivery omits them, so treat empty as "not
reported" and keep any value you previously stored.

## Every install event is a full snapshot — upsert by `install_id`

An install webhook is not just a one-time "who is this install" signal. **Every
event carries the complete, current record**, and an `update_installed` event
delivers the *same fields* as the original `installed` event. So the registry
uses the webhook to push changes: a new `api_url`, a renamed account, a new
`display_version`, a platform move.

Treat each delivery as an **upsert keyed by `install_id`** and overwrite your
stored fields with the incoming ones:

```python
event = parse_install_webhook(token, body, secret)
await installs.upsert(
    event.install_id,
    {
        "account_id": event.account_id,
        "account_name": event.account_name,
        "platform": event.platform,
        "is_test": event.is_test,
        "timezone": event.timezone,
        "api_url": event.api_url,  # may change between events — always take the latest
        "display_version": event.display_version,
    },
)
```

`InstallWebhook` is a frozen dataclass, so `dataclasses.asdict(event)` gives you
the whole record as a JSON-safe dict if you prefer to store it as a unit.

A consumer that reads only the first `installed` event and ignores later
`update_installed` deliveries will keep stale data — most importantly a stale
`api_url`, which would send its API calls to the wrong endpoint.

## Build the install's access service from `platform` + `api_url`

A persisted install carries the two facts needed to reach it: `platform` picks
the access service class, and `api_url` is its endpoint.
`create_access_service_for_install` encodes that mapping, so you go from a stored
install to the right client in one call — no `match` on platform, no URL wiring:

```python
import os

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

The `install` argument is anything satisfying the `InstallAccessTarget` protocol
(`platform`, `api_url`, `install_id` attributes) — the `InstallWebhook` itself or
your own persisted record.

It raises `ValueError` if `install.platform` is `None` or unrecognised — an
install with an unknown platform has no service to route to, and silently
defaulting would point it at the wrong backoffice.

Prefer this (or the config's `api_url` field) over `base_url`/`app_id`, which are
deprecated: they reconstruct the URL with a hardcoded default that cannot be
correct for every install. **The hardcoded base-URL fallbacks will be removed and
a URL will become required in a future release** — source it from the install
webhook's `api_url` now.

## Why `status` and `platform` can be `None`

`parse_install_webhook` never raises on the *body* (only token verification can
raise). The sender is first-party and the payload contract is Peek's own, so a
malformed body is not the failure worth designing for. The failure that *is* real
is the contract **growing** — a new status, or a fourth platform.

Both are therefore reported as `None` rather than coerced into a known value,
with the wire value preserved on `raw_status`. Coercing would be actively
dangerous: Peek treats any 2xx as delivered and does not redeliver, so quietly
mapping an unknown status onto a no-op loses a lifecycle transition permanently,
and defaulting an unknown platform would point that install at the wrong
backoffice. Give both a fall-through branch that fails loudly. The known values
are exported as `INSTALL_STATUSES` and `PEEK_PLATFORMS` (tuples) alongside the
`InstallStatus` / `PeekPlatform` `Literal` aliases.
