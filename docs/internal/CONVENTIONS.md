# Port conventions — `peek-app-utilities` ↔ `@peektravel/app-utilities`

This package is the Python port of the TypeScript `@peektravel/app-utilities`
(repo `peek-travel/app-utilities`). The two ship **the same version number**,
the same resources, the same models, and the same behaviour. This document is
the mapping from the TypeScript source to Python so the port stays mechanical
and consistent across contributors.

## Package layout

| TypeScript | Python |
| --- | --- |
| `src/index.ts` | `src/peek_app_utilities/__init__.py` (public barrel) |
| `src/<name>.ts` | `src/peek_app_utilities/<name>.py` (snake_case) |
| `src/internal/peek/<resource>/<resource>-queries.ts` | `src/peek_app_utilities/internal/peek/<resource>/<resource>_queries.py` |
| `…-converter.ts` | `…_converter.py` |
| `…-service.ts` | `…_service.py` |
| `src/models/peek/<model>.ts` | `src/peek_app_utilities/models/peek/<model>.py` |
| `test/peek/<resource>/x.test.ts` | `tests/peek/<resource>/test_x.py` |
| `scripts/gql-cli/cli.ts` | `scripts/gql_cli/cli.py` |

Directory names use underscores (`account_users`, `resource_pools`,
`daily_notes`, `promo_codes`). The three-file triad per resource is preserved
exactly (queries = raw GraphQL strings + raw TypedDicts + variable builders;
converter = pure functions; service = async class with the business logic).

## Naming

| TypeScript | Python |
| --- | --- |
| `getAllProducts()` | `get_all_products()` |
| `getById(id)` | `get_by_id(id)` |
| `BookingService` (class) | `BookingService` (unchanged — classes keep PascalCase) |
| `booking.customerName` (model field) | `booking.customer_name` |
| `ACTIVITY_PRODUCT_TYPE` | `ACTIVITY_PRODUCT_TYPE` (constants unchanged) |
| `PeekAccessService.getBookingService(integrator?)` | `get_booking_service(integrator=None)` |
| `fullCustomerAccess` | `full_customer_access` |
| `x-peek-sdk: js-<v>` | `x-peek-sdk: py-<v>` |

GraphQL **wire** keys (query text, variables, raw response nodes) stay exactly
as the gateway spells them (`camelCase` / `snake_case` as the API dictates).
Only the clean Python surface is snake_case. The converter is where the rename
happens.

## Types

| TypeScript | Python |
| --- | --- |
| `interface Foo { … }` (output model) | `@dataclass(frozen=True, slots=True, kw_only=True) class Foo` — every field required, converters fill all of them |
| `interface FooInput { a: string; b?: number }` (caller input) | same dataclass decorator; optional fields default to `None` |
| `string \| null` | `str \| None` |
| `string[]` | `list[str]` (output) / `Sequence[str]` (input params) |
| `number` meaning cents/count/integer id | `int` |
| `number` meaning rating/percentage/decimal | `float` |
| `Decimal` kept as string in TS | `str` (no float loss) |
| `Date \| null` (parsed timestamp) | `datetime \| None` via `datetime.fromisoformat`; an unparseable string degrades to `None` (TS yields `Invalid Date`) |
| ISO date/time **string** fields | stay `str` (the TS keeps them as strings too) |
| `"a" \| "b"` union alias | `Literal["a", "b"]` alias **plus** a `Final` tuple constant when runtime code checks membership (see `PEEK_PLATFORMS`) |
| discriminated union (`kind: "x"` variants) | one dataclass per variant with `kind: Literal["x"]`, and a `Union` alias |
| `Record<string, unknown>` / `unknown` payload | `Mapping[str, Any]` / `Any` |
| raw GraphQL node interface (internal) | `class FooNode(TypedDict, total=False)` in `*_queries.py` |
| `interface Logger` | `Logger` Protocol in `logger.py` |
| `export const X = "…"` | `X: Final = "…"` |
| `Error` subclass | subclass of `AppUtilitiesError` in `errors.py` |
| `undefined`/`null` input | `None` |

Converters accept raw nodes as `Mapping[str, Any]`/TypedDict and must be
**pure**: no I/O, no logging, no clock, no `random`. Read raw fields with
`.get()` and degrade (`""`, `None`, `[]`, `False`) the way the TS converter
does — never raise on a missing field unless the TS code does.

## Async

Everything that performs I/O is `async def`. Services take the shared
`GraphQLClient` (Peek) or `RestClient` (CNG/ACME) in their constructor. Use
`asyncio.gather` where the TS code uses `Promise.all`; keep cursor pagination
sequential. Never `time.sleep`.

## Validation and errors

- Input validation stays in the service layer, before any network call, and
  raises `ValueError` where TS throws a plain `Error` (keep the message text).
- Typed package errors are the classes in `errors.py`; PII gating raises
  `PiiAccessDisabledError(operation)` with the **snake_case** method name.
- JWT verification failures are PyJWT's `jwt.InvalidTokenError` subclasses
  (`ExpiredSignatureError`, `InvalidSignatureError`, `InvalidIssuerError`,
  `InvalidAudienceError`, `DecodeError`, …) — the Python analogue of
  `JsonWebTokenError` / `TokenExpiredError` / `NotBeforeError`.
- No static strings inline in logic: hoist them to module `Final` constants
  (error messages, status values, GraphQL operation names), as the TS code does.

## Deprecated TypeScript surface — **not ported**

This is a new package with no existing consumers, so the `@deprecated`
compatibility shims in the TypeScript package are **omitted** rather than
carried over:

- the top-level short-form proxies on the access services (`peek.getAllProducts()`
  etc.) — callers use `peek.get_product_service().get_all_products()`;
- `verifyInstallWebhook` (superseded by `parse_install_webhook`);
- the `AddAddonInput.addonId` alias (use `addon_option_id`).

The deprecated-but-functional config fields `app_id` / `base_url` / `mode`
**are** ported, because they still select the legacy v1 gateway route.

## Tests

- `pytest` + `pytest-asyncio` (`asyncio_mode = auto`): write `async def test_…`
  freely, no decorator needed.
- Service tests use `FakeGraphQLClient` from `tests/conftest.py` (`gql`
  fixture): `gql.queue({...data...})`, then assert on `gql.calls[n].variables`
  and on the substrings present in `gql.calls[n].query` (e.g. that a PII field
  is or is not selected).
- Transport tests use `mock_http_client(handler)` (an `httpx.MockTransport`).
- Port every TS `describe`/`it` case; keep the same assertions, including the
  drift-guard snapshot tests (e.g. the webhook registration query).
- Coverage gate: 95% lines **and** branches (`pytest --cov`).

## Tooling

```bash
uv sync                       # or: uv pip install -e . --group dev
ruff check . && ruff format --check .
mypy
pytest --cov
uv build
```
