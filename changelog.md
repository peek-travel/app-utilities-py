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
