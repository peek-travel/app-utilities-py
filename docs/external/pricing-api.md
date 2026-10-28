# Pricing overrides & engines

A guide for adjusting ticket prices in Peek Pro from your own app using
`peek-app-utilities`. It assumes you have **never seen this API before** and
walks you from zero to a working price override, then covers how to manage
overrides afterward.

Everything here goes through `PeekAccessService.get_pricing_service()`. Every
call is `async`.

---

## 1. The mental model (read this first)

Peek Pro applies price adjustments at checkout through a **pricing engine**. You
don't edit product prices directly — instead you:

1. Create a **pricing engine** once. It's just a named container. Peek gives you
   back an **engine id** — save it; you reuse it forever.
2. Push **overrides** onto that engine for a **date range** and an **activity**.
   An override says "for this activity, on these dates, adjust these tickets'
   prices — optionally only when N spots are already taken and/or within a
   start-time window."

```
Pricing engine  (created once, identified by engine_id)
└── Overrides, upserted per (date range × activity)
    └── one or more override entries, each:
        ├── resource_options[]  ← which tickets, and the fixed/percentage adjustment
        └── filters[]           ← optional: spots_taken and/or start_time_range gates
```

Three things are **your job**, not the API's — this wrapper is deliberately a
thin, faithful pass-through (it does **not** know about your templates,
calendars, or business rules):

- **Deciding what the overrides are** — which tickets, what price, what dates.
- **Ordering** the override entries (`order` field — see §5).
- **Computing `spots_taken` bounds** from ticket counts (the off-by-one — see §6).

The service validates your input and faithfully sends it. That's the deal.

---

## 2. What you need before you start

| You need | How to get it |
| --- | --- |
| A configured `PeekAccessService` | See the package README / `llms.txt` "Entry point". |
| The **activity id** you want to adjust | `get_product_service().get_all_activities()` → `product.product_id` |
| The **ticket (resource option) ids** under it | the same product's `tickets[].id` |
| The activity's **currency** (for fixed prices) | the same product's `currency` (e.g. `"USD"`) |

```python
from peek_app_utilities import PeekAccessService, PeekAccessServiceConfig

async with PeekAccessService(PeekAccessServiceConfig(...)) as peek:  # install_id, jwt_secret, issuer, api_url
    activities = await peek.get_product_service().get_all_activities()
    activity = activities[0]
    # activity.product_id → the activity_id
    # activity.tickets    → [ProductTicket(id, name, min_price, max_price), ...]  (resource options)
    # activity.currency   → "USD"  (use this for fixed-price overrides)
```

Each ticket also carries its current price range as `min_price` / `max_price`
(a `PricingMoney`, or `None` when Peek reports no range) — handy for seeding a
fixed-price override or showing "from $X". Every `PricingMoney` read back from
Peek includes a `display_price` string (e.g. `"$50.00"`) alongside the raw
`amount`/`currency`; it is display-only, so you never set it when *building* an
override.

> **Money and percentages are strings, not numbers.** `"80.00"`, `"-25"` — never
> `80` or `-25`. The API rejects floats, and strings avoid precision loss.

### The model classes

The input shapes are frozen, keyword-only dataclasses, all exported from the
package root:

```python
from peek_app_utilities import (
    ActivityOverrides,
    ClearOverridesInput,
    CreateEngineInput,
    PricingMoney,
    PricingOverride,
    UpdateEngineInput,
    UpsertOverridesInput,
    FixedResourceOptionOverride,       # mode "fixed":      id + price (PricingMoney)
    PercentageResourceOptionOverride,  # mode "percentage": id + percentage_adjustment
    SpotsTakenBounds,                  # min_spots / max_spots (both optional)
    SpotsTakenFilter,                  # spots_taken=SpotsTakenBounds(...)
    StartTimeRangeFilter,              # start_time_range="[HH:MM:SS,HH:MM:SS]"
)
```

`ResourceOptionOverride` (= `FixedResourceOptionOverride |
PercentageResourceOptionOverride`) and `PricingOverrideFilter`
(= `SpotsTakenFilter | StartTimeRangeFilter`) are the exported union aliases; the
variants are discriminated by their `mode` field (set automatically) or by their
class.

---

## 3. Order of operations (the whole lifecycle)

```
① create_engine ──> save engine_id
        │
        ▼
② build UpsertOverridesInput  (you decide the overrides)
        │
        ▼
③ upsert_overrides(input)  ──> Peek stores them, echoes the resolved state
        │
        ▼
   … time passes; guests book; you change your mind …
        │
        ├──> ③ upsert_overrides(...)   re-send to CHANGE overrides (full replace per date+activity)
        ├──> ④ clear_overrides(...)    remove overrides for a date range
        ├──> ⑤ update_engine(...)      rename or re-scope the engine
        └──> ⑥ delete_engine(id)       tear the whole engine down (idempotent)
```

You create the engine **once** (step ①) and then live in steps ③–⑥.

---

## 4. Create your first override (end to end)

### Step 1 — Create the engine (once)

```python
pricing = peek.get_pricing_service()

created = await pricing.create_engine(
    CreateEngineInput(
        name="Summer promo schedule",
        # optional: activity_ids=["act-xyz"]  ← scope the engine to specific activities
    )
)
engine_id = created.id
# → Persist engine_id in your own storage. You'll reuse it for every upsert.
```

Do this **lazily** — only when you're about to push your first override — and
store the returned `engine_id` against whatever your app calls a "schedule". If
you omit `activity_ids`, the engine can carry overrides for any activity.

### Step 2 — Build the override input

Here's a complete, realistic example: activity `act-xyz`, on July 4th, with a
tiered discount on the adult ticket — **$100 normally, but $80 once 4 spots are
taken** — only for the 9–11am window.

```python
morning = StartTimeRangeFilter(start_time_range="[09:00:00,11:00:00]")

input = UpsertOverridesInput(
    engine_id=engine_id,
    date_range="[2025-07-04,2025-07-04]",  # single day: both ends equal (see §7)
    activities=[
        ActivityOverrides(
            activity_id="act-xyz",
            overrides=[
                PricingOverride(
                    order=0,  # evaluated first — the higher-spots, deeper-discount tier
                    resource_options=[
                        FixedResourceOptionOverride(
                            id="ticket-adult",
                            price=PricingMoney(amount="80.00", currency="USD"),
                        ),
                    ],
                    filters=[
                        SpotsTakenFilter(spots_taken=SpotsTakenBounds(min_spots=4)),  # "once 4 spots are taken" (§6)
                        morning,  # only the morning window
                    ],
                ),
                PricingOverride(
                    order=1,  # the base tier
                    resource_options=[
                        FixedResourceOptionOverride(
                            id="ticket-adult",
                            price=PricingMoney(amount="100.00", currency="USD"),
                        ),
                    ],
                    filters=[morning],
                ),
            ],
        ),
    ],
)
```

Prefer a **percentage** adjustment instead of a fixed price? Swap the
`resource_options` entry:

```python
PercentageResourceOptionOverride(id="ticket-adult", percentage_adjustment="-25")  # 25% off; must be > -100
```

### Step 3 — Send it

```python
result = await pricing.upsert_overrides(input)
# result.activity_contexts → the fully resolved state Peek stored (good to log/persist as an audit trail)
```

That's it — the override is live. `upsert_overrides` returns the resolved
`activity_contexts` echoed by Peek (`PricingActivityContext`: date, activity,
engine, and every override with its resolved prices and filters). Store it if
you want an audit record of exactly what Peek accepted.

---

## 5. `order` — how override entries are ranked

Within one activity you often have **tiers** (base price, then a deeper discount
once the group is larger). Peek evaluates entries by their `order` integer,
**lowest first**. So the most specific / deepest-discount tier gets the lowest
number.

Convention (and what the sibling `pricing-schedules` app does): sort your entries
**descending by `min_spots`**, then assign `order = 0, 1, 2, …`. The "5+ tickets"
tier (`min_spots=4`) sorts before the "1+ tickets" base tier, so it gets
`order=0`.

You assign `order` yourself — the service does not reorder for you.

---

## 6. `spots_taken` — mind the off-by-one

`spots_taken` filters an override by **how many spots are already taken**, which
is **zero-indexed** — it is *not* the ticket-count. Convert your ticket-count
ranges like this:

| You mean | `SpotsTakenBounds(...)` |
| --- | --- |
| Any group size (1+) | *omit the filter entirely* |
| 1–4 tickets | `SpotsTakenBounds(max_spots=4)` |
| 5–9 tickets | `SpotsTakenBounds(min_spots=4, max_spots=9)` |
| 10+ tickets | `SpotsTakenBounds(min_spots=9)` |

Rule: for a half-open ticket range `[L, U)` → `min_spots = L - 1` (clamped to 0,
omit when 0), `max_spots = U - 1` (omit when unbounded). "Applies from the 5th
ticket onward" is `min_spots=4`.

The **`start_time_range`** filter is simpler — a Postgres-style inclusive range
string `"[HH:MM:SS,HH:MM:SS]"`. Omit it for all-day overrides. An entry can carry
zero, one, or both filters (the `filters` field defaults to an empty tuple).

---

## 7. `date_range` format

Both `upsert_overrides` and `clear_overrides` take `date_range` as a **PostgreSQL
inclusive range string**:

- Single day: `"[2025-07-04,2025-07-04]"` — both ends the same.
- A span: `"[2025-07-04,2025-07-06]"` — applies to the 4th, 5th, and 6th.

---

## 8. Managing overrides afterward

### Change an override → just upsert again

`upsert_overrides` is a **full replace for that `(date_range, activity)`**. To
change prices, rebuild the input and send it again — you don't diff or patch.
Whatever you send becomes the complete set of overrides for those dates.

### Remove overrides → `clear_overrides` (never "send nothing")

To take a date back to normal pricing, send `clear_overrides`. Under the hood this
is an upsert with **empty** overrides for each activity — which is the **only**
correct way to clear:

```python
await pricing.clear_overrides(
    ClearOverridesInput(
        engine_id=engine_id,
        date_range="[2025-07-04,2025-07-04]",
        activity_ids=["act-xyz"],  # every activity you previously wrote on these dates
    )
)
```

> ⚠️ **You must name the activities to clear.** Clearing works by sending
> `overrides=[]` *for each activity id*. Sending an empty `activities` list
> clears **nothing**. Recover the activity ids from whatever you upserted before
> (e.g. the `activity_contexts` you persisted, or your own records of what you
> pushed onto those dates).

### Rename or re-scope the engine → `update_engine`

```python
await pricing.update_engine(
    UpdateEngineInput(
        engine_id=engine_id,
        name="Renamed schedule",
        activity_ids=["act-xyz", "act-abc"],  # set the engine's activity scope…
        # …or omit / pass [] to CLEAR the scope (engine applies to all activities)
    )
)
```

### Tear it all down → `delete_engine`

```python
await pricing.delete_engine(engine_id)  # idempotent
```

`delete_engine` is **idempotent**: if the engine is already gone it still
resolves, so it's safe to call more than once. After deleting, discard the stored
`engine_id` and create a fresh engine next time you need one.

---

## 9. Method reference

| Method | Does | Returns |
| --- | --- | --- |
| `create_engine(CreateEngineInput(name, activity_ids=None))` | Create an engine (once). | `CreatedPricingEngine(id)` — store it |
| `update_engine(UpdateEngineInput(engine_id, name, activity_ids=None))` | Rename / re-scope. Empty `activity_ids` clears the scope. | `PricingEngine(id, name)` |
| `delete_engine(engine_id)` | Delete the engine. Idempotent. | `None` |
| `upsert_overrides(UpsertOverridesInput)` | Set (full-replace) overrides for a date range. | `UpsertOverridesResult(activity_contexts)` |
| `clear_overrides(ClearOverridesInput(engine_id, date_range, activity_ids))` | Clear overrides for the named activities. | `UpsertOverridesResult(activity_contexts)` |

---

## 10. Errors

- **Validation errors** (raised *before* any network call, as `ValueError`):
  missing `engine_id` / `date_range` / `name` / `activity_id` / ticket id, a
  `currency` that isn't 3 uppercase letters, a non-numeric price amount, a
  non-numeric `percentage_adjustment`, or `percentage_adjustment <= -100`.
- **Peek rejections**: an `InvalidDataError` from Peek (e.g. overlapping tiers)
  surfaces as a `ValueError` carrying Peek's message. A `NotFoundError` on
  `update_engine` raises; on `delete_engine` it's swallowed (idempotent).
- **Transport errors**: HTTP 418 → `AdminAccountRequiredError`, 429 (after
  retries) → `RateLimitError`, GraphQL errors → `PeekGraphQLError`, any other
  non-2xx → `PeekHttpError`. All importable; branch with `except`.

---

## 11. Common pitfalls (the greatest hits)

- **Forgetting to create the engine first.** The `engine_id` must exist before any
  upsert. Create it lazily and persist the id.
- **Clearing with `activities=[]`.** That clears nothing. Use `clear_overrides`
  with the actual `activity_ids`.
- **Numbers instead of strings.** `price.amount` and `percentage_adjustment` are
  strings (`"80.00"`, `"-25"`).
- **`spots_taken` off-by-one.** `[5,10)` tickets → `SpotsTakenBounds(min_spots=4,
  max_spots=9)`. `min_spots` counts spots already taken, not ticket lower bound.
- **Expecting a partial update.** Upsert is a full replace for that
  `(date_range, activity)`. Send the complete desired set every time.
- **Mixing fixed and percentage in one template.** The API may accept it, but
  keeping one mode per schedule is far easier to reason about — pick fixed *or*
  percentage per set of overrides.
