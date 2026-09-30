# Spec 14 — Transportability + verification mode (rev 1)

**Status:** Implemented, tested locally, **not yet applied to Supabase**
**Build order:** Step 14 (post-MVP addition, after step 11's document-review checklist)
**Depends on:** Spec 02 rev 1 (`Instrument` model, `core/instrument_lock.py`), Spec 03 rev 2
(`services/applications.py: create()`'s `state_code`/`district_code` snapshot pattern)

## 1. Goal

The system had no concept of whether an instrument can be transported to a test centre or must be
verified where it sits — every inspection was just "scheduled" with a date, no mode distinction.
This step adds:

1. `instruments.transportable` — "Can the instrument be transported?", a plain boolean on the
   instrument.
2. A `VerificationMode` enum (`OFFICE_TEST_CENTRE`, `ON_SITE`) and `applications.verification_mode`
   — a **snapshot** of `transportable` taken once, when the application is created, exactly
   mirroring how `state_code`/`district_code` already snapshot the instrument's location onto the
   application at the same moment (spec 03). The reasoning is identical: the instrument's
   transportability could change later, but the application should freeze whatever was true when
   it was filed.

Mapping: `transportable=True → OFFICE_TEST_CENTRE`, `transportable=False → ON_SITE`.

**Out of scope:**
- Any new endpoint. `transportable` rides the existing `POST/PATCH /instruments` request/response
  schemas; `verification_mode` rides the existing `ApplicationDetail`/`ApplicationOut`.
- Actually changing how scheduling or the field-inspection flow behaves for `ON_SITE` vs.
  `OFFICE_TEST_CENTRE` (e.g. a different checklist, a different assignment rule). This step only
  adds the field and its snapshot; using it to branch inspection behavior is a future step.
- Backfilling `verification_mode` on applications that existed before this migration — see §3 and
  §9 D2.

## 2. Access

No new role or endpoint. `transportable` is read/write exactly like every other
`IDENTITY_LOCKED` instrument field (§3): `BUSINESS` (owner) sets it on create/PATCH, subject to
the same lock. `verification_mode` is read-only, computed once by the service — no request body
ever sets it directly (`ApplicationCreate` does not accept it).

## 3. Data model (migration `0009_transportability`)

### `instruments.transportable` (new column)
| column | type | notes |
|---|---|---|
| `transportable` | boolean | added nullable + `server_default(true)`, backfilled, then set `NOT NULL` |

- **Backfill approach (decision, see §9 D1):** the migration adds the column nullable with
  `server_default(true())`, runs an explicit `UPDATE instruments SET transportable = true WHERE
  transportable IS NULL`, then `ALTER COLUMN ... SET NOT NULL` — the standard three-step sequence
  for safely adding a required column to an existing table. In Postgres 11+, `ADD COLUMN ...
  DEFAULT true` alone is already a metadata-only change (no table rewrite; pre-existing rows read
  the default via the catalog's "missing value" optimization), so the explicit `UPDATE` is
  technically redundant here — kept anyway for auditability and so correctness doesn't depend on
  that optimization.
- Every existing instrument ends up `transportable = true` (office/test-centre eligible) — the
  same "assume nothing has changed" default every additive boolean backfill in this codebase uses
  (mirrors `users.is_active`'s own `server_default(true())`).

### `verification_mode` (new enum type) / `applications.verification_mode` (new column)
| column | type | notes |
|---|---|---|
| `verification_mode` | enum (`OFFICE_TEST_CENTRE`, `ON_SITE`) | nullable, no backfill |

- **No backfill (decision, see §9 D2):** unlike `transportable` above, this column is a
  *snapshot* — its entire purpose is to reflect `instrument.transportable` at the exact moment
  each application was created. That value can't be reconstructed for applications that already
  existed before this migration (the instrument's current `transportable` is not necessarily what
  it was back then). Pre-migration applications keep `verification_mode = NULL` permanently;
  every application created from `services/applications.py: create()` onward always gets one.
- **New enum type, added via `ADD COLUMN` on an existing table** — a combination not previously
  used in this codebase. `0001`-`0003` created brand-new enum types, but always as part of
  `CREATE TABLE` (SQLAlchemy auto-issues `CREATE TYPE` as a DDL event attached to `Table.create()`
  in that case). `0005`/`0008` added a *value* to an *existing* type (`ALTER TYPE ... ADD VALUE`,
  which has its own transactional caveats, worked around with `IF NOT EXISTS`). This migration
  does neither: it's a brand-new type added outside a `CREATE TABLE`, so `CREATE TYPE` must be
  issued explicitly (`VERIFICATION_MODE.create(op.get_bind(), checkfirst=True)`) before the `ADD
  COLUMN`. No transactional gotcha, though: `CREATE TYPE` (unlike `ALTER TYPE ... ADD VALUE`) is
  fully transactional in Postgres, so the whole migration — both columns — stays one migration,
  one transaction, consistent with `backend/CLAUDE.md`'s existing round-trip expectations.

## 4. Enum placement (`app/core/verification_types.py`)

**Decision (see §9 D3):** a new sibling module, not an addition to `core/instrument_types.py` or
`core/application_types.py`. `instrument_types.py` groups the instrument's own closely-related
physical/product categories (`InstrumentType`, `CapacityUnit`, `AccuracyClass`) — one file per
domain area, mirrored by `application_types.py` for the application/document lifecycle.
Verification mode doesn't fit either: it's a routing/logistics concept *computed from* an
instrument property (`transportable`) but *stored on* the Application, not the Instrument. Adding
it to `instrument_types.py` would misrepresent it as an instrument-owned category; adding it to
`application_types.py` would bury a two-value routing enum alongside `ApplicationStatus`/
`DocumentType`'s much larger, unrelated vocabularies. A small sibling module keeps the "one file
per closely-related group" convention intact.

```python
class VerificationMode(StrEnum):
    OFFICE_TEST_CENTRE = "OFFICE_TEST_CENTRE"
    ON_SITE = "ON_SITE"

VERIFICATION_MODE_LABELS: dict[VerificationMode, str] = {
    VerificationMode.OFFICE_TEST_CENTRE: "Office / test centre",
    VerificationMode.ON_SITE: "On-site (in-situ)",
}

def verification_mode_for(transportable: bool) -> VerificationMode:
    return VerificationMode.OFFICE_TEST_CENTRE if transportable else VerificationMode.ON_SITE
```

## 5. Locking (`core/instrument_lock.py`)

**Decision (see §9 D4):** `transportable` joins `IDENTITY_LOCKED` — locked for the same duration
as `manufacturer`/`model`/`serial_number`/`capacity`/`capacity_unit`/`accuracy_class`/
`state_code`/`district_code`, i.e. while any non-terminal application exists (lifts at `REJECTED`
or `CERTIFICATE_ISSUED`). Reasoning: it is snapshotted onto the Application at creation, exactly
like `state_code`/`district_code` — and those two fields are *themselves* `IDENTITY_LOCKED` for
that very reason. Leaving `transportable` editable mid-application would let the instrument's live
value drift out of sync with the application's frozen `verification_mode` snapshot (confusing on
any screen that shows both), and would let a business change the office/on-site classification
after submission — even though it can no longer retroactively change the *current* application's
already-frozen `verification_mode`, it could still be read as an attempt to influence how the
application is perceived mid-review. Locking it removes the ambiguity entirely, at zero cost
(the field is never needed mid-application; a business who genuinely needs to correct it can
delete the draft, like every other identity field).

Not treated as a `LOCATION_FIELDS` field: it doesn't describe where the instrument is, and its
lock timing (from the moment *any* non-terminal application exists, `DRAFT` included) matches
`IDENTITY_LOCKED`, not `LOCATION_FIELDS`'s narrower `SCHEDULED`/`INSPECTION`/`APPROVED` window.

## 6. Schemas

- `InstrumentCreate.transportable: bool = True` — defaults to `true` (office/test-centre) when
  the caller omits it, matching the DB's own `server_default(true())`.
- `InstrumentUpdate.transportable: bool | None = None` — `None` (unset) means "don't touch";
  an explicit `null` is rejected (`reject_null_for_required`, same as every other non-nullable
  instrument field) since `transportable` is not in `NULLABLE_FIELDS`.
- `InstrumentOut.transportable: bool` — always present.
- `ApplicationOut.verification_mode: VerificationMode | None` — the **raw enum**, not a label,
  matching how `status`/`application_type` are already serialized on this schema (labels are
  served separately, only via meta — see below). `None` only for applications created before
  migration `0009`.
- `ApplicationMeta.verification_modes: list[LabelledValue]` — `[{value, label}, ...]`, built the
  same way `statuses`/`application_types` already are. The frontend must never hardcode
  `VERIFICATION_MODE_LABELS`.

## 7. Backend implementation

```
app/core/verification_types.py     VerificationMode, VERIFICATION_MODE_LABELS, verification_mode_for()
app/core/instrument_lock.py        + "transportable" in IDENTITY_LOCKED
app/models/instrument.py           + transportable: Mapped[bool] (NOT NULL, server_default(true()))
app/models/application.py          + verification_mode: Mapped[VerificationMode | None]
app/schemas/instrument.py          InstrumentCreate/Update/Out gain transportable
app/schemas/application.py         ApplicationOut gains verification_mode; ApplicationMeta gains verification_modes
app/services/applications.py       create(): snapshot verification_mode via verification_mode_for();
                                    APPLICATION_CREATED audit detail gains verification_mode
alembic/versions/0009_transportability.py
```

No changes to `app/routers/instruments.py` / `app/routers/applications.py` — both fields ride
existing endpoints/schemas.

## 8. Tests (backend)

New file `tests/test_transportability.py`:
- Instrument creation: `transportable` defaults `true` when omitted; explicit `true`/`false` both
  round-trip.
- Application creation snapshots `verification_mode` correctly from the instrument's
  `transportable` at that moment (`OFFICE_TEST_CENTRE` for `true`, `ON_SITE` for `false`).
- **The snapshot property, explicitly proven:** create an instrument `transportable=true`, create
  and reject an application from it (`verification_mode == OFFICE_TEST_CENTRE`), then flip the
  instrument to `transportable=false` (now unlocked, `REJECTED` is terminal) — the *existing*
  application's `verification_mode` is unchanged; a *new* application created afterward gets
  `ON_SITE`.
- `GET /applications/meta` includes `verification_modes` matching
  `VERIFICATION_MODE_LABELS` exactly.
- `locked_fields`: `transportable` is in `IDENTITY_LOCKED`; locked while a non-terminal
  application exists (`SUBMITTED`), unlocked with none and after `REJECTED`. End-to-end: `PATCH
  /instruments/{id}` with `{"transportable": false}` → 409 while an application is in progress,
  → 200 once it's rejected.
- `InstrumentUpdate.transportable` rejects an explicit `null` (422), same as every other
  non-nullable instrument field.

## 9. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | `instruments.transportable`: add `NOT NULL` directly, or nullable-then-backfill-then-`NOT NULL`? | **Nullable → backfill → `NOT NULL`** (three steps in one migration). Postgres 11+ makes a direct `NOT NULL DEFAULT true` add just as safe (metadata-only, no rewrite) for this specific case, but the three-step sequence is the more defensive, broadly-correct pattern for adding a required column to an existing table and doesn't rely on callers knowing that optimization applies here. |
| D2 | Backfill `applications.verification_mode` for pre-existing rows (e.g. from the current instrument's `transportable`)? | **No backfill; left `NULL`.** The column is a snapshot of a specific past moment; deriving it from the instrument's *current* `transportable` would fabricate a value with no guarantee it matches what was true when that application was actually filed — worse than an honest `NULL`. |
| D3 | Enum home: `core/instrument_types.py`, `core/application_types.py`, or a new sibling module? | **New sibling module** (`core/verification_types.py`). It's computed from an instrument property but stored on the Application — doesn't cleanly belong to either existing per-domain-area file (§4). |
| D4 | Does `transportable` join `IDENTITY_LOCKED`, or stay freely editable post-creation? | **Joins `IDENTITY_LOCKED`.** It's snapshotted onto the Application exactly like `state_code`/`district_code`, which are themselves locked for that reason; consistency and anti-drift outweigh the (minimal) inconvenience of locking it (§5). |
| D5 | `OFFICE_TEST_CENTRE`/`ON_SITE` label wording? | "Office / test centre" and "On-site (in-situ)" — plain, non-technical phrasing consistent with this codebase's other `*_LABELS` dicts (e.g. `STATUS_LABELS`), no legal/regulatory terminology implied (ASSUMPTION, same caveat every `*_types.py` module already carries). |

## 10. Acceptance criteria

- [x] `0009_transportability` round-trips locally (`downgrade base`, `upgrade head`), `alembic
  check` reports no drift. **Not applied to Supabase** — an explicit later step.
- [x] `instruments.transportable` defaults `true`, is settable on create, and joins
  `IDENTITY_LOCKED` (locked/unlocked exactly like the other identity fields).
- [x] `applications.verification_mode` is snapshotted once, at creation, from the instrument's
  `transportable` at that moment, and is provably frozen thereafter (explicit test).
- [x] `GET /api/applications/meta` serves `verification_modes`; nothing hardcodes the labels
  client-side.
- [x] `ruff check`/`ruff format --check` clean; full backend test suite green (420, up from 409),
  including the new file.
- [x] `backend/CLAUDE.md` updated: migration table (`0009`, explicitly marked not-yet-applied to
  Supabase), a new "Transportability and verification mode" subsection, data model section
  updates for both `Instrument` and `Application`, API block.

## 11. Verification record

Backend (`pytest`, local `lm_test` via `TEST_DATABASE_URL`): 420 passed (409 pre-existing + 11 new
in `tests/test_transportability.py`). `ruff check .` and `ruff format --check .` both clean.

Migration tested with `alembic downgrade base && alembic upgrade head` (full chain, not just
`-1`) against `lm_test`, plus `alembic check` (no drift) and a `downgrade -1`/`upgrade head`
round-trip specifically around `0009`. **Supabase was never touched** — no command in this step
ran against `backend/.env`'s `DATABASE_URL`; applying `0009` to Supabase is an explicit, separate,
later step per the task brief's safety rule.
