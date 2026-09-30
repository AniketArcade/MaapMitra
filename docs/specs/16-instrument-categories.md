# Spec 16 — 33 instrument categories + dynamic field schema (rev 1)

**Status:** Implemented, tested locally. 🛑 **NOT YET APPLIED TO SUPABASE — AND MUST NOT BE, UNTIL
THE USER HAS REVIEWED THE SEEDED CATEGORY CONTENT.** This is the biggest and riskiest migration in
the plan so far: unlike every other "not yet applied" migration on this branch, this one needs a
**content** review (are these 33 categories, their fields, options and units acceptable?), not
just a code review.
**Build order:** Step 16 (post-MVP addition, on top of steps 11/14/13/12)
**Depends on:** Spec 02 rev 1 (`Instrument` model, `core/instrument_lock.py`), Spec 14 rev 1
(the `IDENTITY_LOCKED`/paired-nullable-field precedent this step reuses almost exactly)

## 1. Goal

The backend's instrument model has always had a flat, fixed shape: `instrument_type` (a 7-value
enum), `capacity`+`capacity_unit`, and an optional `accuracy_class`. A separate, earlier frontend
prototype (`MaapMitrafrontend`, a different repo) had already designed a much richer 33-category,
dynamic-field-schema system for the same domain and fully written out all 33 category definitions
as TypeScript fixture data. This step ports that system into the real backend, **additively**:

1. A new `instrument_categories` reference table (33 rows, `id` 1-33) holding each category's
   name, mock validity period, and a JSON `field_schema` describing its category-specific fields
   (selects, unit-numbers, repeaters, toggles, a Qmin/Qt/Qmax range-band, etc.).
2. Two new nullable columns on `instruments` — `category_id` (FK) and `category_values` (the
   filled-in values for that instrument) — that an instrument may optionally carry alongside its
   existing `instrument_type`/`capacity`/`capacity_unit`/`accuracy_class`.
3. `GET /instruments/meta` gains a `categories` entry so a future frontend's dynamic field
   renderer reads the schema from the backend, never a hardcoded list of its own.

**Nothing existing changes.** `InstrumentType`, `CHECKLIST_TEMPLATES`/`MEASUREMENT_TEMPLATES`
(`core/inspection_templates.py`), and every pre-existing instrument row are completely unaffected
— an instrument with no `category_id` works exactly as it did before this migration.

### ⚠️ Non-authoritative content — read before reviewing

The 33 categories below are **ported wholesale, unmodified, from the donor prototype's own mock
fixture data** (`MaapMitrafrontend/src/data/instrumentCategories.ts`). That repo's own
`docs/SPEC.md` §15 already carries this exact disclaimer, reproduced here verbatim because it
applies identically to this port:

> **33 instrument categories are invented-but-realistic**, loosely modeled on Indian Legal
> Metrology (Legal Metrology Act 2009 / General Rules 2011) verification categories, chosen to
> satisfy every hint already embedded in [that repo's] CLAUDE.md §8 (exact category numbers for
> `+Add Weight`, `+Add Nozzle`, `+Add Compartment`, locked units `ct`/`°C`, presets, Qmin/Qt/Qmax
> band, Static/Dynamic selector). The specific class letters, capacity presets, and accuracy
> classes are illustrative, not sourced from an actual regulation — fine for a mock-data
> prototype, not to be cited as real regulatory guidance.

**This means:** none of the category names, field lists, option values, unit choices, or
`validity_months` figures below should be treated as real Legal Metrology Act 2009 / General
Rules 2011 classifications. They are a plausible-looking placeholder taxonomy, good enough to
exercise a dynamic-form backend, not good enough to certify a real instrument against. The task
that produced this migration explicitly requires a human to review this content before it is ever
applied to the production Supabase database — see §9 "Decisions" below and the migration table in
`backend/CLAUDE.md`.

**Out of scope for this step:**
- Deep validation of category_values beyond top-level required-field presence (repeater-row
  contents, range-band Qmin < Qt < Qmax ordering, unit-option membership) — see §7.
- Any mapping/backfill of existing `instrument_type`-only instruments onto one of the 33
  categories. Old and new systems coexist; nothing bridges them automatically.
- Any frontend work. This is a backend-only port; a future step wires a `DynamicFieldRenderer` to
  `GET /instruments/meta`'s new `categories` entry.
- GATC category-eligibility routing (the donor prototype's `GATC.eligibleCategoryIds`) — not
  ported; this backend's GATC role remains minimal (root `CLAUDE.md`'s open decision).

## 2. Access

No new role or endpoint. `category_id`/`category_values` ride the existing `POST`/`PATCH
/instruments` request/response schemas exactly like spec 14's `transportable` — `BUSINESS`
(owner) sets them, subject to the same `IDENTITY_LOCKED` lock (§5). `GET /instruments/meta`'s new
`categories` entry is read-only, available to the same "any logged-in user" audience the rest of
that endpoint already serves.

## 3. Data model (migration `0012_instrument_categories`)

### `instrument_categories` (new table)

| column | type | notes |
|---|---|---|
| `id` | smallint PK | **1-33, not the codebase's usual `UUIDPk`** — see §9 D1 |
| `name` | text, not null | |
| `validity_months` | integer, not null | mock; never used to compute real legal validity |
| `field_schema` | JSONB, not null | array of field definitions, see §4 |
| `created_at`/`updated_at` | timestamptz | standard `Timestamps` mixin |

Seeded with exactly 33 rows in this same migration (`op.bulk_insert`) — see §9 D2 for why the seed
lives in the migration itself rather than `app/seed.py`/`database/seed/`.

### `instruments.category_id` / `instruments.category_values` (new columns)

| column | type | notes |
|---|---|---|
| `category_id` | smallint, nullable, FK -> `instrument_categories.id`, `ON DELETE SET NULL` | never cascades a delete onto the instrument |
| `category_values` | JSONB, nullable | filled-in values keyed by each field's `key` |

Both nullable, **no backfill**: every instrument that existed before `0012` gets
`category_id = NULL`/`category_values = NULL` and continues to work entirely off
`instrument_type`/`capacity`/`capacity_unit`/`accuracy_class`, exactly as before this migration.

## 4. Field schema shape (`app/schemas/instrument_category.py: CategoryFieldSchema`)

Same shape as the donor's `CategoryField` TypeScript interface, translated to **snake_case JSON
keys** (this backend's own convention everywhere else — see §9 D3):

```
key                str            # opaque field identifier, e.g. "weightClass" — NOT renamed
label              str
type               str            # "text" | "number" | "select" | "multiselect" | "unit-number"
                                   # | "range-band" | "repeater" | "toggle" | "date" | "file"
required           bool = False
unit               str | None     # fixed unit, e.g. "ct", "°C"
unit_options       list[str] | None   # selectable unit toggle, e.g. ["L", "mL"]
options            list[{value, label}] | None
presets            list[{value, label}] | None
repeater_label     str | None     # e.g. "+ Add Weight", "+ Add Nozzle", "+ Add Compartment"
repeater_fields    list[CategoryFieldSchema] | None   # recursive
min                float | None
max                float | None
help_text          str | None
```

**Only the wrapping dict's keys were renamed to snake_case** (`unitOptions` -> `unit_options`,
`repeaterLabel` -> `repeater_label`, `repeaterFields` -> `repeater_fields`, `helpText` ->
`help_text`). Field **values** — including each field's own `key` (e.g. `"weightClass"`,
`"nominalValue"`) — are preserved byte-for-byte from the donor; those are opaque
identifiers/labels, not structural JSON keys, and renaming them was never asked for and would
break faithful porting.

## 5. The 33 categories, as seeded

Ported mechanically from `MaapMitrafrontend/src/data/instrumentCategories.ts` — every field,
`required`/`unit`/`unit_options`/`options`/`presets`/`repeater_label`/`repeater_fields`/`min`/
`max`/`help_text` preserved exactly, special-case behaviors called out below preserved verbatim:

1. Standard Weights
2. Carat / Jewellery Weights
3. Retail / Counter Scale
4. Platform / Bench Scale
5. Spring Balance
6. Bullion / Precision Jewellery Scale
7. Measuring Tape (Length)
8. Volumetric Capacity Measure
9. Metre Rod / Yardstick
10. Road Weighbridge (Non-Automatic)
11. Rail Weighbridge (Automatic)
12. Electricity (Energy) Meter
13. Domestic Gas Meter (Diaphragm)
14. Belt Conveyor Weigher (Automatic)
15. Taximeter
16. Auto-rickshaw Fare Meter
17. Water Meter
18. Petrol / Diesel Dispensing Unit
19. Sphygmomanometer (BP Monitor)
20. Clinical Thermometer
21. Tyre Pressure Gauge
22. Milk Analyzer / Milko-tester
23. Grain Moisture Meter
24. Hydrometer / Densimeter
25. LPG / CNG Dispensing Unit
26. Industrial Gas Meter (Turbine/Rotary)
27. Automatic Checkweigher (Packaged Goods Line)
28. Hopper / Tank Weighing System
29. Portable Axle-Load Weighbridge
30. Bulk Liquid Flow Meter (Oil/Milk)
31. Speed Measuring Device (Radar/Laser Gun)
32. Road Tanker / Bowser (Multi-Compartment)
33. Ring & Plug Gauge Set (Length Standards, Calibration Lab)

**Special-case behaviors preserved verbatim** (per the task brief, cross-referencing the donor's
own CLAUDE.md §8): `+ Add Weight` repeater (#1), `+ Add Nozzle` repeater (#18, #25),
`+ Add Compartment` repeater (#32), locked units `ct` (#2) / `°C` (#20), presets (#4, #6, #10),
Qmin→Qt→Qmax range-band (#17, #26), Static/Dynamic toggle (#11, #14).

Full field-by-field detail lives only in the seed data itself
(`backend/alembic/versions/0012_instrument_categories.py: SEED_CATEGORIES`) and the live
`GET /instruments/meta` response once applied — this doc intentionally doesn't duplicate all ~100
individual field definitions inline; use the migration file or the donor's own
`docs/SPEC.md §10` for the itemized field list per category.

## 6. Schemas

- `InstrumentCreate`/`InstrumentUpdate` gain `category_id: int | None = None` and
  `category_values: dict[str, Any] | None = None`. **Paired**: a `model_validator` rejects one
  being set (non-`None`) without the other — see §7 D-pairing. Both are added to
  `NULLABLE_FIELDS`, so an explicit `null` on either is accepted (clears the category assignment
  entirely; still must be paired — `InstrumentUpdate` additionally requires both be *sent* in the
  same PATCH, not just one).
- `InstrumentOut.category_id: int | None` / `.category_values: dict[str, Any] | None` — always
  present, `null` for every instrument with no category assigned.
- `InstrumentMeta.categories: list[InstrumentCategoryOut]` (`{id, name, validity_months,
  field_schema}`) — built from a live DB query in the router (`GET /instruments/meta`), not a
  Python constant, unlike `types`/`accuracy_classes`/`regions` on the same response (see §9 D2 for
  why this one specifically needs to be DB-backed).

## 7. Validation scope — a deliberate simplification

`services/instruments.py: _validate_category()` implements **top-level required-field-presence
checking only**: every `field_schema` entry with `required: true` must have a corresponding
non-null key in `category_values`. This runs on `create()` (whenever `category_id` is set) and on
`update()` (whenever `category_id`/`category_values` are among the changed fields).

**Explicitly OUT OF SCOPE** (per the task brief's own instruction to scope this down rather than
silently leave it half-done):
- Repeater-row contents (e.g. category 1's `denominations` repeater having at least one row, or
  each row itself satisfying its own `repeater_fields`' `required` flags).
- Range-band ordering (categories 17/26's `Qmin < Qt < Qmax` constraint).
- Unit-option membership (rejecting a `unit` value not present in a field's own `unit_options`).

A future step can add a recursive/deep validator if the product needs it; this step's scope is
deliberately the simplest thing that satisfies "an instrument claiming a category has at least
attempted to fill in that category's required fields," matching this codebase's own "pick the
simplest thing that works for the MVP" value (root `CLAUDE.md` §"Instructions for Claude").

If `category_id` is omitted, `category_values` must also be omitted/null — enforced at the schema
layer (§6), before any DB-dependent check runs.

## 8. Backend implementation

```
app/models/instrument_category.py     InstrumentCategory (id smallint PK, name, validity_months, field_schema JSONB)
app/models/instrument.py              + category_id (FK, SET NULL) / category_values (JSONB)
app/models/__init__.py                registers InstrumentCategory
app/schemas/instrument_category.py    CategoryFieldOption, CategoryFieldSchema (recursive), InstrumentCategoryOut
app/schemas/instrument.py             InstrumentCreate/Update/Out gain category_id/category_values (paired);
                                       InstrumentMeta.categories + InstrumentMeta.build(categories)
app/core/instrument_lock.py           + "category_id"/"category_values" in IDENTITY_LOCKED
app/services/instruments.py           _validate_category(); wired into create()/update()
app/routers/instruments.py            meta() now takes `db`, queries InstrumentCategory, passes to InstrumentMeta.build()
alembic/versions/0012_instrument_categories.py
```

No changes to `core/instrument_types.py`, `core/inspection_templates.py`,
`services/applications.py`, or any application/inspection/certificate code — this step is scoped
entirely to the `Instrument` model and its own schemas/services/router.

## 9. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | `instrument_categories.id`: `UUIDPk` (this codebase's usual convention) or a small fixed integer? | **Smallint PK, 1-33, not a UUID.** These are a small, fixed, numbered reference set — not user-generated rows — and the donor prototype's own CLAUDE.md §8 already references categories by these exact numbers for special-case behaviors (`+ Add Weight` = #1, `+ Add Nozzle` = #18/#25, etc.). A UUID would obscure that stable numbering for no benefit. |
| D2 (seed location) | Seed the 33 categories via the migration itself, or via `app/seed.py`/`database/seed/` (the existing demo-data mechanism)? | **Via the migration itself** (`op.bulk_insert` inside `0012_instrument_categories.upgrade()`). `app/seed.py` explicitly refuses to run when `ENV=production` unless `--force-demo` — appropriate for demo accounts, wrong for reference/taxonomy data the app needs to function in every environment (production included). `instrument_categories` is closer in spirit to `app/core/regions.py`'s `REGIONS` dict (always-present reference data) than to `app/seed.py`'s demo users/instruments/applications — the only difference is it needs a real table (for JSON per-row content and for `GET /instruments/meta` to read it live, enabling future content edits without a code deploy) rather than an in-memory Python dict. |
| D3 (JSON key casing) | snake_case or camelCase for `field_schema`'s JSON keys? | **snake_case** — this backend's own Python/Pydantic convention everywhere else (every other schema, every other JSONB column's documented shape). The donor TypeScript repo's camelCase (`unitOptions`, `repeaterLabel`, etc.) does not carry over; only the wrapping keys are renamed, not each field's own `key`/`label`/`type`/option values (§4). |
| D4 (validation scope) | Deep validation (repeater rows, range-band ordering, unit-option membership) or top-level required-field-presence only? | **Top-level required-field-presence only** (§7) — an explicit, documented MVP simplification per the task brief's own instruction, not an oversight. Building a full nested validator for the donor's richest field types is a lot of surface area for a step whose primary purpose is porting the schema/data, not exhaustively validating every possible category shape. |
| D5 (pairing) | Can `category_id` be set without `category_values` (or vice versa)? | **No — rejected at the schema layer.** Providing a category without its values (or values with no category to interpret them against) is meaningless; both `InstrumentCreate` and `InstrumentUpdate` require them together (`_category_pair_valid`/`category_fields_sent_together`), mirroring how `latitude`/`longitude` are already required as an explicit pair on this same schema. |
| D6 (locking) | Do `category_id`/`category_values` join `IDENTITY_LOCKED`? | **Yes** — same reasoning as `transportable` (spec 14 D4): an in-progress application's understanding of "what kind of instrument is this" shouldn't have the underlying instrument's category (or its filled-in values) change while a non-terminal application exists. Locked/unlocked as a pair, never independently. |
| D7 (`ON DELETE` behavior) | `category_id`'s FK: `CASCADE`, `RESTRICT`, or `SET NULL`? | **`SET NULL`** — a category row being removed (hypothetically, in a future admin tool; nothing in this step deletes categories) must never cascade-delete or block deleting the instruments that reference it. The instrument simply loses its category classification, the same honest-NULL posture spec 14's own `verification_mode` non-backfill already uses. |

## 10. Tests (backend)

New file `tests/test_instrument_categories.py` (19 tests):
- **(a)** `GET /instruments/meta` returns all 33 categories (`test_meta_includes_all_33_categories`)
  with structural correctness (not just `len == 33`) asserted for several special-case categories:
  #1's weight repeater (`unit_options`, `repeater_label`), #2's locked `ct` unit, #11's
  Static/Dynamic toggle, #17's Qmin/Qt/Qmax range-band, #18's "+ Add Nozzle" repeater, #32's
  "+ Add Compartment" repeater, #20's locked `°C` unit.
- **(b)** Creating an instrument with a valid `category_id` + `category_values` satisfying all
  required fields succeeds (`test_create_instrument_with_valid_category_values`, category 15).
- **(c)** `category_id` set but a required field missing from `category_values` -> 422
  (`test_create_instrument_missing_required_category_field_is_422`); an unknown `category_id` also
  -> 422 (`test_create_instrument_unknown_category_id_is_422`).
- **(d)** `category_id` without `category_values` (create and PATCH), and `category_values`
  without `category_id` (create), are both rejected with 422.
- **(e)** An instrument created the OLD way (no `category_id`, just `instrument_type`) is
  completely unaffected (`test_create_instrument_without_category_is_unaffected`) — the key
  additivity regression test.
- **(f)** `category_id`/`category_values` lock exactly like `transportable`: in `IDENTITY_LOCKED`
  (`test_category_fields_are_identity_locked`), 409 while a non-terminal application exists
  (`test_category_locked_while_application_in_progress`), unlocked again after `REJECTED`
  (`test_category_lock_lifts_after_rejection`).
- **(g)** The full pre-existing suite (448 tests as of spec 12) passes completely unmodified,
  proving `CHECKLIST_TEMPLATES`/`MEASUREMENT_TEMPLATES`-driven inspection tests and everything
  else are untouched by this step.

## 11. Acceptance criteria

- [x] `0012_instrument_categories` round-trips locally (`downgrade base`, `upgrade head`, and a
  `downgrade -1`/`upgrade head` round-trip specifically around `0012`), `alembic check` reports no
  drift. **NOT applied to Supabase** — requires explicit user content review first (see the
  prominent warning at the top of this doc and in `backend/CLAUDE.md`'s migration table).
- [x] All 33 categories seeded with correct `name`/`validity_months`/`field_schema`, verified
  structurally (not just a row count) for the special-case categories named in the task brief.
- [x] `GET /instruments/meta` serves `categories` read live from the DB table.
- [x] An instrument can be created/updated with a valid `category_id`+`category_values` pair;
  missing required fields are rejected (422); an unpaired `category_id`/`category_values` is
  rejected (422); an instrument with no category at all is completely unaffected.
- [x] `category_id`/`category_values` join `IDENTITY_LOCKED` and lock/unlock exactly like
  `transportable`.
- [x] `ruff check`/`ruff format --check` clean; full backend test suite green (467, up from 448:
  448 pre-existing + 19 new in `tests/test_instrument_categories.py`).
- [x] `backend/CLAUDE.md` updated: migration table (`0012`, marked with the elevated "content
  review required" warning, more prominent than the standard not-yet-applied note), a new
  "Instrument categories" subsection, data model updates for both `Instrument` and the new table,
  API block.

## 12. Verification record

Backend (`pytest`, local `lm_test` via `TEST_DATABASE_URL`): 467 passed (448 pre-existing + 19 new
in `tests/test_instrument_categories.py`). `ruff check .` and `ruff format --check .` both clean.

Migration tested with `alembic downgrade base && alembic upgrade head` (full 12-revision chain),
plus `alembic check` (no drift) and a `downgrade -1`/`upgrade head` round-trip specifically around
`0012`. **Supabase was never touched** — every command ran with `TEST_DATABASE_URL` explicitly
overridden to the local `lm_test` database; `backend/.env` was never read or modified. Applying
`0012` to Supabase requires an explicit, separate, later step **and** the user's review of the
seeded category content — not just the usual "apply when ready" that every other pending migration
on this branch carries.
