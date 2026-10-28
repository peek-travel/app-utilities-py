# Project Guidelines

`peek-app-utilities` (import name `peek_app_utilities`) is a small,
dependency-light **async Python library** that wraps the Peek "backoffice" API
plus the CNG and ACME backoffice APIs. It is the **Python port of
`@peektravel/app-utilities`** (repo `peek-travel/app-utilities`): same
resources, same models, same behaviour, same version number. Callers only ever
touch `PeekAccessService` (or `CngAccessService` / `AcmeAccessService`), the
per-resource services it hands out, and the clean dataclass models — never raw
GraphQL.

> **⚠️ Never bump the package version on your own.** Do not change `version` in
> `pyproject.toml` (or any file that mirrors it) as part of doing the work. When
> you are about to open a PR, **ask the user** whether they want to bump the
> version and, if so, to which new version — then apply exactly that. See
> **Versioning** below.

- If anything about a request is unclear or ambiguous, ask for clarification
  before starting any work. Don't guess at intent or proceed on assumptions.
- Before making any changes, review `docs/internal/ARCHITECTURE.md` and
  `docs/internal/CONVENTIONS.md` (the TypeScript → Python mapping).
- **This package tracks the TypeScript package.** When a change lands in
  `@peektravel/app-utilities` (a new method, model field, option, or behaviour),
  port it here following `docs/internal/CONVENTIONS.md`, and vice versa. Do not
  invent Python-only surface without flagging it to the user first. The two
  packages share a version: a release of one is a release of the other.
- Once you've made all the code changes, update `docs/internal/ARCHITECTURE.md`
  to reflect major changes (new resources, new triads, changed public surface).
- **Keep the external guides in sync.** If you change the pricing surface
  (`PricingService`, the `models/peek/pricing.py` models, or the products
  `currency` field), update `docs/external/pricing-api.md`. Likewise
  `docs/webhooks.md` for the webhook surface and `llms.txt` for any change to the
  public entry points.
- **Keep the interactive HTML reference in sync.** `docs/html/peek.html`,
  `docs/html/cng.html`, and `docs/html/acme.html` are self-contained, interactive
  reference docs (left-nav, filter, light/dark toggle) for the top-level service
  classes and the data models each returns. Whenever you add, remove, rename, or
  change a **service class**, a **public service method** (its name, parameters,
  return type, PII gating, validation, or error behavior), or a **data model**
  (any field, its type, or nullability) in the matching domain, you MUST update
  the corresponding HTML file in the same change. The content lives in the
  `render({ … })` data object near the bottom of each file — edit the `services`
  and `models` arrays; service- and model-name references in signatures/types
  auto-link, so use the exact exported type names. Do not log these doc updates
  in `changelog.md`. The three files MUST stay structurally identical: same
  `<head>`, CSS, and `render()` renderer — **only** the data object differs. The
  load-bearing conventions:
  - **Ordering is automatic — do not hand-order the arrays.** The root
    `*AccessService` is pinned first; every other service and every model sorts
    alphabetically at runtime.
  - **Only the root access service shows a `Constructor`.** Per-resource
    services document an `obtain` field naming the accessor (e.g.
    `PeekAccessService.get_booking_service()`), not a `ctor`.
  - Keep the root access-service card lean — no free-form "Behavior" notes block
    on it; put per-method detail on the methods themselves.
  - **Model inheritance is expressed with `extends`, never by copying fields**
    (e.g. `PeekAccessServiceConfig extends BaseAccessServiceConfig`).
  - **No dangling type references — if a type is referenced, document it.**
    Shared types like `AccessOptions` and `Logger` must be documented in all
    three files. Literal aliases use a `kind:"type"` entry with a `def` string.
  - **Keep transport/implementation detail out of the copy.** Document the
    caller-facing surface, not how the package talks to the API. The one
    deliberate exception is a single low-key `GraphQLClient` reference in the
    `PeekAccessService` description.
- Ensure test coverage stays above 95% (the `pytest --cov` gate enforces
  `fail_under = 95` on lines and branches).
- **Keep the `scripts/gql_cli` test harness in sync with the service surface.**
  `scripts/gql_cli/cli.py` drives the real resource services against the live
  API (outside `src/`, never packaged). Whenever you add, remove, rename, or
  change the signature of a **public service method**, update its entry in the
  harness `REGISTRY` (name, group, description, params with the right
  `ParamKind`, the `pii` flag for PII-gated calls, and a `run` callable), wire
  any new service or constructor option into `build_context`, and keep its
  client construction matching how the `*AccessService` builds `GraphQLClient`.
  It must stay importable (`python -m py_compile scripts/gql_cli/cli.py`; mypy
  covers it). Internal tool — do not log harness updates in `changelog.md`.
- Unless told otherwise, after everything is done, run the linter and fix any
  errors.
- **Keep `changelog.md` up to date.** It is the consumer-facing changelog —
  only changes a **caller** can observe or act on, grouped by version. Anything
  potentially breaking for an existing consumer MUST be recorded under the
  `## Unreleased` header with (a) what changed, (b) why, and (c) the concrete
  caller action. Caller-visible fixes and new capabilities may be logged too,
  tagged `[fix]` / `[additive]`. **Do not** log internal-only work.

# Architecture conventions

Preserve the structure described in `docs/internal/ARCHITECTURE.md`. The
load-bearing rules:

- **Three-file triad per resource** under `src/peek_app_utilities/internal/peek/<resource>/`:
  - `*_queries.py` — raw GraphQL strings, matching raw `TypedDict` response
    shapes, and small variable-builder/normalizer helpers. **Internal only —
    never re-exported from `__init__.py`.**
  - `*_converter.py` — **pure, I/O-free** functions mapping raw nodes → clean
    dataclass models. No network, no logging, no clock.
  - `*_service.py` — the public `async` class with the business logic; calls
    the shared `GraphQLClient`, then runs the converter.
- A resource may split into more than one triad when it carries a distinct
  sub-domain (e.g. `bookings` has `booking_*` plus `addon_*` and `metadata_*`).
- **An access service exposes only its resource-service accessors.** The root
  `*AccessService` hands out the per-resource services via `get_…_service()`
  (plus genuine access-level concerns like `verify_peek_auth_token`, `aclose()`
  and the async context manager), and nothing else. Do **not** add top-level
  "short-form" proxy methods that delegate to a resource-service method. (The
  TypeScript package carries deprecated short-forms for backwards
  compatibility; this port deliberately omits them.)
- **Public surface = `src/peek_app_utilities/__init__.py`**: the access
  services + configs, the factory, the resource service classes and the
  option/result types callers need, the data-model dataclasses, `Logger` /
  `noop_logger` / `logging_adapter`, the webhook parsers, and the typed error
  classes. Query strings, raw `TypedDict`s, and internal detail models stay
  internal — add a model to `__init__.py` only if a consumer genuinely needs it.
- **Stay dependency-light.** `httpx` and `PyJWT` are the only runtime
  dependencies. Prefer the standard library (`uuid`, `base64`, `json`,
  `asyncio`) over adding a package; flag it for the user before introducing a
  new runtime dependency.
- **Models are `@dataclass(frozen=True, slots=True, kw_only=True)`.** Output
  models have every field required (converters fill them all); input models
  default optional fields to `None`. `null` → `None`. Literal unions are
  `typing.Literal` aliases, plus a `Final` tuple when runtime code checks
  membership. Discriminated unions are one dataclass per variant with a
  `kind`/`mode` Literal field and a `Union` alias.
- **Async only.** Every I/O method is `async def`; use `asyncio.gather` for
  independent work; cursor pagination stays sequential.

# `full_customer_access` (the PII switch)

This is the single most consequential option in the package — getting it wrong
either leaks customer PII into an app that isn't entitled to it, or silently
returns `None` where a caller expected a guest name. Treat it as load-bearing.

## What it is

`AccessOptions` (`access_options.py`) is a cross-cutting options object passed
**once**, at access-service construction, via the `access_options` config
field. Today it carries a single flag:

```python
PeekAccessService(
    PeekAccessServiceConfig(..., access_options=AccessOptions(full_customer_access=True))
)
```

- **Default is `False`** — PII off. Omitting `access_options`, passing
  `AccessOptions()`, or passing `None` all resolve to
  `ResolvedAccessOptions(full_customer_access=False)` via
  `resolve_access_options()`. Always resolve through that helper.
- It is an **object, not a bare boolean**, so future cross-cutting flags slot in
  without changing any downstream signature. Keep it that way.
- It is **per access service, not per call**. There is deliberately no
  per-method override. Do not add a call-level parameter for it.
- Only `PeekAccessService` actually consumes it today: it resolves once in the
  constructor and threads the *resolved* value into `BookingService` and
  `ReviewService`. `CngAccessService` / `AcmeAccessService` accept the same
  config shape but have no PII surface, so the flag is inert there.
- `parse_waiver_webhook(body, options=None)` takes the same `AccessOptions`
  directly — webhook parsers are pure and have no access service to inherit from.

## What `False` (the default) does

**1. PII is never requested — filtered at the query-builder layer, not in
converters.** The query *builders* omit the fields, so the API never returns
them and the pure converters map the absent fields to `None`/empty. Converters
stay PII-agnostic; do not add PII branching to a converter.

- **Bookings** (`booking_queries.py`): drops the primary-guest block
  (`customer_name`/`email`/`phone`/`postal_code`/`is_gdpr`/opt-ins), the guest
  identity fields, the booking- and ticket-level custom `question_answers`, and
  the customer `booking_portal_url`. Operator-facing fields always stay.
- **Reviews** (`build_reviews_query`): drops the reviewer `name`/`email`.
- **Waivers** (`parse_waiver_webhook`): the webhook payload is fixed, so this is
  the **one** place filtering happens at parse time: participant `guest_name`
  becomes `None` and the signed-document `file_url` becomes `""`.

**2. Payment / booking-modification operations are disabled.** `BookingService`
gates `get_payments_on_file`, `make_payment`, `refund`, `create_invoice_link`,
`add_addon`, `remove_addon` — raising the exported `PiiAccessDisabledError`
(carrying `.operation`, the snake_case method name) **before any network call**.

## Rules when changing code

- **Adding a field that could identify or contact a customer** → gate it in the
  query builder behind `full_customer_access`, make the model field `| None`,
  and add builder tests for both branches. When in doubt, gate it.
- **Adding a booking operation that reads or moves money** → route it through
  the existing `_assert_pii_access` guard in `BookingService`.
- **Never** filter PII in a converter, in the service after the response lands,
  or by post-processing a model.
- The booking **webhook registration query** (`BOOKING_WEBHOOK_GQL_QUERY`) is
  deliberately unaffected: it is the maximal selection, pinned by the
  drift-guard test. If you reorder fields in a builder, that test will fail.
- Any change here must be reflected in **all four** docs: `README.md` ("Access
  options / PII"), `llms.txt`, `docs/webhooks.md`, and
  `docs/internal/ARCHITECTURE.md` §4b.

# Coding Standards

- Except for log messages, do not put static strings directly in the code.
  Declare them as module-level `Final` constants (e.g. the `ERROR_*` and status
  constants at the top of the booking service) and share them where useful.
- Look for opportunities to simplify by extracting helper functions instead of
  duplicating logic; review new code for obvious duplication once complete.
- Don't `await` inside a loop for independent work — use `asyncio.gather()`.
  Genuinely sequential work is the exception: cursor pagination must await each
  page to get the next cursor.
- Keep converters pure so they can be unit-tested without a client. Tests use
  the `FakeGraphQLClient` (`gql` fixture) or an `httpx.MockTransport` from
  `tests/conftest.py` — never hit the real network.
- Input validation lives in the service layer (id prefixes, currency format,
  positive-integer quantities, etc.) and raises `ValueError`;
  `normalize_booking_id` lowercases and converts `-` → `_`.
- Type hints everywhere; `mypy --strict` must pass on `src/`.

# Versioning

**Never bump the `version` on your own.** The package versions **in lockstep
with `@peektravel/app-utilities`**: the Python release carries the same version
number as the TypeScript release it mirrors. The maintainer decides when and
how far to bump.

**When you are preparing a PR, ask the user** whether they want to bump the
version and, if so, to exactly which new version. If they decline, leave every
version literal untouched and keep new changelog entries under `## Unreleased`.

To help the user decide, you may suggest a level based on the most significant
change in the PR (but still wait for their answer before applying it):

- **major** — a breaking change (removed/renamed public export, changed method
  signature or return shape, altered default).
- **minor** — new caller-visible capability with no break.
- **patch** — a caller-visible fix with no new surface, or internal-only work.

Only **when the user has asked for a specific bump**: set the version once, and
move everything that names the version together in that same commit:

- `pyproject.toml` `project.version`
- `SDK_VERSION` in `src/peek_app_utilities/internal/sdk_headers.py`, which
  feeds the outbound `x-peek-sdk: py-<version>` header.
  `tests/test_sdk_headers.py` is a drift guard that fails if it does not equal
  the `pyproject.toml` version.
- `changelog.md` — rename the `## Unreleased` heading to the new version.
- A `v<version>` git tag triggers the PyPI publish workflow
  (`.github/workflows/publish.yml`), which refuses a tag that does not match
  `pyproject.toml`.

# Build / test commands

```bash
uv sync --group dev          # create .venv and install everything
uv run ruff check .          # lint   (ruff check --fix to autofix)
uv run ruff format .         # format
uv run mypy                  # strict type-check (src, tests, scripts)
uv run pytest                # tests
uv run pytest --cov          # tests + the 95% coverage gate
uv build                     # sdist + wheel into dist/
```

Sandbox quirks: if `uv sync` is unavailable, `uv venv .venv && uv pip install
--python .venv/bin/python -e . pytest pytest-asyncio pytest-cov respx mypy ruff`
and invoke `.venv/bin/<tool>` directly.

# Review Checklist

## Once complete
- Review the new code for obvious duplication; simplify with helper functions.
- Run the linter, the type checker, and the unit tests (with coverage).
- Update `docs/internal/ARCHITECTURE.md` if the public surface, resources, or
  build changed; `docs/internal/CONVENTIONS.md` if a new TS→Python mapping rule
  was needed.
- Update `docs/external/pricing-api.md` if the pricing surface changed, and
  `llms.txt` if the public entry points changed.
- Update the matching `docs/html/*.html` reference if any service class, public
  method, or data model in that domain changed.
- Record any caller-visible change in `changelog.md` under `## Unreleased`.
- Confirm the change exists (or is planned) in `@peektravel/app-utilities` too,
  so the two packages do not drift.
- Before opening the PR, **ask the user whether to bump the version** (and to
  which new version). Never bump on your own.
