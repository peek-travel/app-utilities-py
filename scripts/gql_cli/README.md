# gql_cli — Peek access-service test harness

A developer CLI for hitting the real Peek API with the package's own resource
services + converters. **Not** part of the published package — it lives outside
`src/` and is never packaged. It is the Python port of the TypeScript
`scripts/gql-cli` harness in `@peektravel/app-utilities`.

## How auth works

The API only checks two headers: `pk-api-key` (the gateway key) and
`X-Peek-Auth: Bearer <token>`. All of it lives in a gitignored `.env`:

- `PEEK_GATEWAY_KEY`, `PEEK_APP_ID`, `PEEK_BASE_URL` — static.
- `PEEK_AUTH_TOKEN` — the bearer token. It **expires**; paste a fresh one when it
  does. **Leave it blank to be prompted** (hidden input) at call time instead.

`PeekAccessService` normally *mints* that token from a JWT secret. This harness
skips all of that: because you supply a ready token, it builds the internal
`GraphQLClient` directly (`get_token` just returns your token) and wires the
real services onto it — exactly the way `PeekAccessService` does — so it
exercises the exact same service + converter code a consumer would.

## Setup

```bash
cd <repo root>
uv sync --group dev                   # creates .venv with the package installed (editable)
cd scripts/gql_cli
cp .env.example .env                  # fill in PEEK_GATEWAY_KEY + PEEK_APP_ID (+ PEEK_AUTH_TOKEN)
chmod +x run.sh                       # once
```

`.env` is gitignored. `run.sh` runs the CLI with the repo's `.venv/bin/python`
(`python -m scripts.gql_cli.cli`), so there is nothing to compile or install
beyond the normal dev setup.

## Usage

```bash
./run.sh <function_name> [param1] [param2] ...
./run.sh help                    # list every function
./run.sh help <function_name>    # show one function's params
```

The token comes from `PEEK_AUTH_TOKEN`; if it's unset you're prompted for it
(hidden) before the call runs. `help` never asks for a token. You can also pipe
it: `echo "$TOKEN" | ./run.sh get_all_activities`.

Function names are the snake_case service method names (plus a resource
prefix where the TypeScript harness has one), e.g. `getAllActivities` →
`get_all_activities`, `getBookingById` → `get_booking_by_id`.

### Examples

```bash
# List activities (token from .env, or prompted)
./run.sh get_all_activities

# Custom questions for an activity
./run.sh get_custom_questions 87cdf37f-1872-42cb-b0bd-518312624fc1

# Reviews, page size 5, offset 10 (numbers coerced)
./run.sh get_reviews prod_123 5 10

# A booking with read options (object param = one JSON string)
./run.sh get_booking_by_id b_abc '{"include_guests":true}'

# JSON keys may be camelCase too, so the TypeScript README examples work verbatim
./run.sh get_booking_by_id b_abc '{"includeGuests":true}'

# A PII-gated call for this one invocation
./run.sh --pii get_booking_payments_on_file b_abc
```

Results are printed to stdout as JSON (dataclasses are serialized with
`dataclasses.asdict`; non-JSON values such as datetimes become strings).
Errors are printed to stderr as a JSON object (`name`, `message`, plus
`operation` / `status_code` / `url` / `body` / `graphql_errors` when present)
and the exit code is `1`.

## Parameter types

`help <fn>` lists each param's kind:

- **string** — passed through as-is.
- **number** — coerced; `int` when integral, `float` otherwise; must parse.
- **boolean** — `true|false|1|0|yes|no`.
- **json** — a single JSON string (object inputs like `create_booking`,
  `make_booking_payment`, pricing upserts). The object is turned into the
  matching input dataclass; keys may be `snake_case` (`include_guests`) or
  `camelCase` (`includeGuests`), and nested objects/arrays (tickets, guests,
  overrides, filters) are converted recursively. Mind your shell quoting.

Calls marked **[PII]** (payments, add-on mutations, payments-on-file) raise
`PiiAccessDisabledError` unless `PEEK_FULL_CUSTOMER_ACCESS=1` is set in `.env`
or the call is run with the `--pii` flag.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `PEEK_AUTH_TOKEN` | `X-Peek-Auth` bearer token. Blank → prompted (hidden) at call time. |
| `PEEK_GATEWAY_KEY` | `pk-api-key` header. Required unless `PEEK_API_URL` is set. |
| `PEEK_APP_ID` | App id — the URL path segment in v1 mode (`<base_url>/<app_id>/sales`). Required unless `PEEK_API_URL` is set. |
| `PEEK_BASE_URL` | Optional v1 base URL. Defaults to `https://apps.peekapis.com/backoffice-gql`. |
| `PEEK_API_URL` | Optional install app-endpoint URL. When set it is the sole request URL (routed through the registry slug) and `PEEK_APP_ID` / `PEEK_GATEWAY_KEY` are ignored. |
| `PEEK_FULL_CUSTOMER_ACCESS` | `1`/`true`/`yes` enables PII-gated calls and PII fields on reads. Same effect as `--pii`. |
| `PEEK_INTEGRATOR` | Optional integrator id scoping `get_meta_data` results (defaults to `PEEK_APP_ID`). |
| `PEEK_DEBUG` | `1` prints request diagnostics to stderr (stdout stays pure JSON). |

Real environment variables take precedence over `.env` values.

## Keeping it in sync

Whenever a public service method is added, removed, renamed, or changes its
signature, update its entry in the `REGISTRY` in `cli.py` (name, group,
description, params with the right `ParamKind`, the `pii` flag for PII-gated
calls, and the `run` callable), and keep `build_context` matching how
`PeekAccessService` constructs `GraphQLClient` and wires the services. Check it
with:

```bash
.venv/bin/ruff check scripts && .venv/bin/ruff format scripts && .venv/bin/mypy scripts
.venv/bin/python -m py_compile scripts/gql_cli/cli.py
./scripts/gql_cli/run.sh help
```
