# Spec 02 — Instrument registration (rev 2)

**Status:** Ready for Claude Code (all decisions resolved, see §12)
**Build order:** Step 2 of 10
**Depends on:** Spec 01 rev 2 (`get_current_user`, `require_roles`, `get_client_ip`, `audit.log`) **plus the amendments in §2**

## 1. Goal
A BUSINESS user registers the instruments their organization owns, then lists, views, edits and deletes them. Each instrument gets a permanent readable `instrument_uid` (`LM-JH-DHN-000123`). Officials can **read** instruments inside their jurisdiction, which prepares the officer dashboard in step 5.

Demo story: ABC Traders registers a weighing scale, serial `XYZ12345`, 500 kg, in Dhanbad, and gets UID `LM-JH-DHN-…`.

**Out of scope:** applications and documents (step 3), verification status or expiry display (steps 8–10), maps and GPS capture (deferred or Good-to-Have), bulk import, transferring an instrument between organizations, serial-number disputes and admin override (see §13), GATC access.

## 2. Amendments to Spec 01 (apply in this step)
1. **Domain errors.** Add `app/core/errors.py`: `NotFound` (404), `Conflict` (409), `Forbidden` (403). Services raise these; **one** exception handler in `main.py` maps them to `{"detail": ...}`. Services never import `HTTPException`.
2. **Audit signature.** `audit.log(db, *, actor, action, entity_type, entity_id, organization_id, details, ip)`. Routers pass `ip=get_client_ip(request)` into every service call that audits. Spec 01 calls are updated to the same signature.
3. **`/auth/me` effective scope.** For BUSINESS and GATC users, `UserOut.state_code` / `district_code` return the **organization's** codes (no schema change). The instrument form prefills from these.
4. **Unknown fields are rejected project-wide** (`extra="forbid"` on every request schema → 422). Spec 01's register test changes accordingly: a `role` field in the body → 422 (it can still never create a non-BUSINESS user). Record this rule in `backend/CLAUDE.md`.
5. **Regions list.** Registration (Spec 01) validates `state_code` / `district_code` against the static list in §4, not just the regex.

## 3. Access rules
| Action | BUSINESS | LM_OFFICER / DISTRICT_ADMIN | STATE_ADMIN | SUPER_ADMIN | GATC |
|---|---|---|---|---|---|
| Create | own org | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 |
| List / get | own org only | instruments in their state **and** district | their state | all | ✗ 403 |
| Update | own org | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 |
| Delete | own org (see §6) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 |

- **Org isolation:** a business asking for another org's instrument gets **404**, never 403. Same for PATCH and DELETE.
- **Jurisdiction:** out-of-scope instruments return 404 for officials too. Scope comes from the **instrument's** `state_code`/`district_code`, not the owner org's.
- **One helper:** `services/scoping.py: scope_instruments(stmt, user)` applies the rule. Every read goes through it. Step 3 adds `scope_applications` beside it.
- **Fails closed:** an unknown role, or an official missing the codes their role requires, gets an empty list and 404 on get.
- Officials' UI hides Edit/Delete (the backend already returns 403).

> **ASSUMPTION:** officials' jurisdiction follows the instrument's location. Product assumption; the real Legal Metrology jurisdiction rules are unverified.

## 4. Enumerations and regions
> **ASSUMPTION (all lists below):** MVP product categories, **not** the legal classification in the Legal Metrology Act 2009 or its rules. Region codes are project conventions, not official codes. Verify with a domain expert before production.

- `instrument_type`: `WEIGHING_SCALE`, `WEIGHBRIDGE`, `WEIGHT`, `FUEL_DISPENSER`, `MEASURE_LENGTH`, `MEASURE_VOLUME`, `OTHER`
- `capacity_unit`: `mg`, `g`, `kg`, `t`, `mL`, `L`, `kL`, `mm`, `cm`, `m`
- `accuracy_class`: `I`, `II`, `III`, `IIII` (OIML weighing classes; applicability per type unverified, so optional)
- **Unit families:** `WEIGHING_SCALE`, `WEIGHBRIDGE`, `WEIGHT` take mass units (`mg g kg t`). `FUEL_DISPENSER`, `MEASURE_VOLUME` take volume units (`mL L kL`). `MEASURE_LENGTH` takes length units (`mm cm m`). `OTHER` takes any.
- **Regions (demo subset, `app/core/regions.py`):**

| State | Districts (code: name) |
|---|---|
| `JH` Jharkhand | `DHN` Dhanbad, `RNC` Ranchi, `BKR` Bokaro |
| `BR` Bihar | `PAT` Patna |

**Single source of truth:** the backend owns all of the above. The frontend never hard-codes them (see `GET /instruments/meta`, §6).

## 5. Data model (migration `0002_instruments`)

### `instruments`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `instrument_uid` | text, **unique**, not null | `LM-{state}-{district}-{seq:06d}`, assigned by the server, never editable |
| `organization_id` | UUID FK → organizations, not null, indexed | from the caller, never the body |
| `instrument_type` | enum `instrument_type` | |
| `manufacturer` | text, not null | trimmed, internal whitespace collapsed |
| `model` | text, not null | same |
| `serial_number` | text, not null | trimmed, whitespace collapsed, stored **uppercased** |
| `capacity` | numeric(12,3), not null, `> 0` | |
| `capacity_unit` | enum `capacity_unit` | |
| `accuracy_class` | enum `accuracy_class`, nullable | |
| `address` | text, not null | |
| `state_code` | text, not null | must exist in §4 regions |
| `district_code` | text, not null | must exist under that state |
| `latitude` | numeric(9,6), nullable, −90..90 | plain column, no PostGIS |
| `longitude` | numeric(9,6), nullable, −180..180 | both set or both null (check constraint) |
| `created_by` | UUID FK → users, not null | |
| `created_at`, `updated_at` | timestamptz | |

- **Uniqueness:** unique index `ix_instruments_mfr_serial` on `(lower(manufacturer), serial_number)` across **all** orgs (D1).
- **UID numbering:** Postgres sequence `instrument_uid_seq`, global, so numbers within a district have gaps (D2).
- **Indexes:** `(organization_id, created_at desc)` and `(state_code, district_code)`.
- **Migration is hand-written where autogenerate can't help:** the sequence, the functional unique index, the check constraints. `downgrade` must drop the table, the 3 enums **and** the sequence.

## 6. API
Base `/api`. All endpoints need a login. Errors use `{"detail": ...}`.

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| GET | `/instruments/meta` | any logged-in user | → `InstrumentMeta` |
| POST | `/instruments` | BUSINESS | `InstrumentCreate` → `201 InstrumentOut` |
| GET | `/instruments` | BUSINESS, LM_OFFICER, DISTRICT_ADMIN, STATE_ADMIN, SUPER_ADMIN | query → `Page[InstrumentOut]` |
| GET | `/instruments/{id}` | same | → `InstrumentOut` |
| PATCH | `/instruments/{id}` | BUSINESS | `InstrumentUpdate` → `InstrumentOut` |
| DELETE | `/instruments/{id}` | BUSINESS | → `204` |

Register `/instruments/meta` **before** `/instruments/{id}` so the path isn't captured as an id.

**`InstrumentMeta`:** `{ types: [{value, label, units: [str]}], accuracy_classes: [str], regions: [{state_code, state_name, districts: [{code, name}]}] }`. The form builds every dropdown from it.

**List query:** `q` (max 100 chars; matches serial, UID, manufacturer or model, case-insensitive substring; escape `%`, `_`, `\` before `ILIKE`), `instrument_type`, `state_code`, `district_code` (the last two only narrow inside the caller's scope), `page` (default 1), `page_size` (default 20, max 100). Sorted by `created_at desc, id`, so paging is stable on ties.

**`Page[T]`:** `{ "items": [...], "total": int, "page": int, "page_size": int }`. Reused by every later list.

### Schemas
```python
class InstrumentCreate(BaseModel):          # extra="forbid"
    instrument_type: InstrumentType
    manufacturer: str                       # 1..100, trimmed, whitespace collapsed
    model: str                              # 1..100, same
    serial_number: str                      # 1..50, trimmed, collapsed, uppercased,
                                            # ^[A-Z0-9][A-Z0-9\-/._]*$
    capacity: condecimal(max_digits=12, decimal_places=3, gt=0)
    capacity_unit: CapacityUnit
    accuracy_class: AccuracyClass | None = None
    address: str                            # 1..500
    state_code: str | None = None           # default: caller's org
    district_code: str | None = None        # default: caller's org
    latitude: Decimal | None = None         # both or neither
    longitude: Decimal | None = None

class InstrumentUpdate(BaseModel):          # extra="forbid"; all optional; PATCH semantics
    manufacturer, model, serial_number, capacity, capacity_unit,
    accuracy_class, address, state_code, district_code, latitude, longitude
    # instrument_type is NOT editable (delete and re-register)

class InstrumentOut(BaseModel):
    id: UUID; instrument_uid: str
    organization_id: UUID; organization_name: str
    instrument_type: InstrumentType; manufacturer: str; model: str; serial_number: str
    capacity: float; capacity_unit: CapacityUnit; accuracy_class: AccuracyClass | None
    address: str; state_code: str; district_code: str
    latitude: float | None; longitude: float | None
    created_at: datetime; updated_at: datetime
```
`organization_id`, `instrument_uid`, `created_by` in a body → 422 (forbid).

### Behaviour rules
- **Create:**
  - `organization_id` and `created_by` come from the caller.
  - Missing `state_code`/`district_code` default to the org's; the pair must exist in §4 regions.
  - The UID is built from the instrument's own location plus `nextval('instrument_uid_seq')`, in the same transaction as the insert.
  - **Duplicate check is the unique index, not a pre-select:** INSERT, catch `IntegrityError` on `ix_instruments_mfr_serial` → `409 "An instrument with this manufacturer and serial number is already registered. Contact your district office if you believe this is an error."` The message never names the owning org.
  - Writes `INSTRUMENT_CREATED` (with `organization_id`, `entity_type="instrument"`).
- **Update (PATCH):**
  - Take the sent fields with `model_dump(exclude_unset=True)`.
  - Non-nullable fields sent as `null` → 422. Nullable (`accuracy_class`, `latitude`, `longitude`) may be cleared with `null`.
  - **Validate the merged state**, not single fields: unit ↔ existing type family, lat/lng both-or-neither, state/district exist in §4.
  - The UID never changes, even if the location changes (D3).
  - Writes `INSTRUMENT_UPDATED` with `details.changes = {field: [old, new]}`.
  - An empty diff → 200, **no** audit row, `updated_at` unchanged.
  - Duplicate on the new manufacturer/serial → 409 as above.
- **Edit lock (D4, activates in step 3):** once an application exists on the instrument in a **non-terminal** status, the identity fields (`manufacturer`, `model`, `serial_number`, `capacity`, `capacity_unit`, `accuracy_class`) **and** `state_code`/`district_code` are read-only → `409`. Terminal statuses: `CERTIFICATE_ISSUED`, `REJECTED`. Step 2 has no applications, so nothing is locked yet; **step 3 adds the check and its test** (no empty stub in this step).
- **Delete:** hard delete. Writes `INSTRUMENT_DELETED` with the UID and serial in `details` (the row is gone). In step 3 the FK is `ON DELETE RESTRICT` and the service returns 409 while any application exists (D5).
- **Reads:** `get` runs one scoped query (row missing **or** out of scope → `NotFound`). It never loads the row first and checks ownership afterwards. Use `joinedload(Instrument.organization)` for `organization_name` (no N+1).

## 7. Requirements recorded for Step 3
- `applications.instrument_id` FK is `ON DELETE RESTRICT`; catch `IntegrityError` → 409.
- PATCH instrument and "create application" both `SELECT … FOR UPDATE` the instrument row, so the lock check can't race.
- Add `scope_applications` beside `scope_instruments`.
- Fill in the edit lock from §6 and add its tests.

## 8. Backend implementation
```
app/core/errors.py               NotFound, Conflict, Forbidden + handler
app/core/regions.py              static regions (JH, BR demo subset)
app/core/instrument_types.py     InstrumentType, CapacityUnit, AccuracyClass, UNIT_FAMILY
app/models/instrument.py         Instrument model (+ relationship to Organization)
app/schemas/common.py            Page[T], PageParams dependency
app/schemas/instrument.py        InstrumentCreate / InstrumentUpdate / InstrumentOut / InstrumentMeta
app/services/scoping.py          scope_instruments(stmt, user)   # org isolation + jurisdiction, fails closed
app/services/instruments.py      create, list, get, update, delete (all reads via scope_instruments)
app/routers/instruments.py       thin handlers, pass get_client_ip
alembic/versions/0002_instruments.py
```
Decimal fields are returned as JSON numbers.

## 9. Frontend implementation
| Route | Who | Content |
|---|---|---|
| `/instruments` | Business, officials | list: cards on mobile, table on desktop; search box; empty state "No instruments yet → Register one" (business only) |
| `/instruments/new` | Business | form: type → unit dropdown filtered to that type's units; **state and district dropdowns** from meta, prefilled from `user.state_code` / `district_code` (shows names, sends codes); optional lat/lng |
| `/instruments/[id]` | Business, officials | detail; business also sees Edit and Delete (confirmation dialog); officials see read-only |

- Load `GET /instruments/meta` once (cache in memory); never hard-code types, units or regions in TypeScript.
- Business dashboard card links to `/instruments` with a count. Officer placeholder card links to `/instruments` (read-only).
- Every view handles loading, empty, error, 403 and 404. A 404 shows "Instrument not found" for both missing and out-of-scope.
- Types in `lib/types.ts`; calls only through `lib/api.ts`.
- New shadcn components: `select`, `dialog`, `table`, `badge`.
- **No map and no "use my location" button.**

## 10. Tests (backend)
Concurrency tests need committed sessions (not the rollback-per-test fixture) plus explicit cleanup.

**Org isolation (priority 1)**
- Business A's list never includes B's instruments.
- GET, PATCH, DELETE of B's instrument by A → 404, and B's row is unchanged.
- `organization_id` in a create body → 422.

**RBAC**
- Create, update, delete parameterized over all 6 roles: only BUSINESS succeeds, others 403.
- GATC can't list or get (403).
- `GET /instruments/meta` works for any logged-in role and is 401 when anonymous.

**Jurisdiction**
- LM_OFFICER JH/DHN sees JH/DHN instruments; JH/RNC and BR/PAT → 404.
- STATE_ADMIN JH sees JH/DHN and JH/RNC, not BR/PAT.
- SUPER_ADMIN sees all.
- An official with missing codes (bad data) sees nothing.

**Validation**
- Bad unit for the type → 422. `capacity ≤ 0` or more than 3 decimals → 422.
- Only one of lat/lng, or out of range → 422.
- Unknown state, or a district not under that state → 422.
- Serial and manufacturer are trimmed and whitespace-collapsed; serial uppercased, so `xyz12345`, `XYZ12345` and `xyz  12345`-style variants collide.
- Serial with `.` or `_` is accepted; with a space or `#` → 422.
- Unknown field in a body → 422.

**PATCH merge rules**
- PATCH only `latitude` when `longitude` exists → 200. Same when both are null → 422.
- PATCH `capacity_unit` to a unit outside the existing type's family → 422.
- `{"manufacturer": null}` → 422. `{"accuracy_class": null}` clears it.
- PATCH `instrument_type` → 422.
- Empty diff → 200, no audit row, `updated_at` unchanged.

**UID**
- Format `^LM-[A-Z]{2}-[A-Z]{2,4}-\d{6,}$`, built from the instrument's location.
- 10 concurrent creates give 10 distinct UIDs.
- Changing the location via PATCH doesn't change the UID.

**Duplicates**
- Same manufacturer (different case) plus same serial → 409, across orgs too, and the message doesn't mention the other org.
- Two concurrent creates with the same manufacturer/serial → one 201, one 409.

**Delete**
- Delete → 204, then GET → 404, with an `INSTRUMENT_DELETED` audit row containing the UID.

**Audit**
- Create, update, delete each write one row with the instrument's `organization_id` and the right details.

**Pagination and search**
- `page_size` above 100 → 422. `total` is correct. Order is stable across pages.
- `q` matches UID and serial. `q=%` matches nothing extra (escaped). `q` over 100 chars → 422.

## 11. Demo seed (⚠️ seed changes need approval)
- **Do not** seed `XYZ12345`; ABC Traders registers it live.
- Seed **one** instrument for Other Traders (JH/DHN): weighing scale, serial `OTH-0001`, 30 kg, to show org isolation.
- Reset `instrument_uid_seq` before the demo, or accept a number like `…-000047`. A UID is never a credential (it is guessable); `scope_instruments` is the gate.

## 12. Decisions (resolved)
| # | Decision | Resolution |
|---|---|---|
| D1 | Serial uniqueness | **Global** unique on (manufacturer ignoring case, serial). Risk: a rival can pre-register a serial and block it; no dispute path yet (§13). The 409 text points to the district office |
| D2 | UID numbering | **One global Postgres sequence**; gaps accepted; regex allows 6+ digits |
| D3 | UID after a location change | **Permanent** |
| D4 | Edit lock | **Identity fields and location** locked while a non-terminal application exists (from step 3) |
| D5 | Delete | **Hard delete** until the first application (then 409 via RESTRICT) |
| D6 | Seed | Add `OTH-0001` for Other Traders only |
| D7 | Type, unit, accuracy lists | §4 lists, marked ASSUMPTION |
| D8 | Officials' read access in step 2 | **Yes**, jurisdiction-scoped |
| D9 | Source of enums, units and regions | **Backend only**, via `GET /instruments/meta` |
| D10 | Business chooses the instrument's state and district | **Allowed** (defaults to the org's), validated against the static regions list. Marked ASSUMPTION |

## 13. Deferred
- Serial-number dispute and admin override; instrument transfer between organizations.
- Archiving instead of hard delete.
- Full official region and district list.

## 14. Acceptance criteria
- [ ] `0002_instruments` round-trips locally (`upgrade`, `downgrade -1`, `upgrade`; sequence and 3 enums dropped on downgrade) and applies to Supabase. Recorded in the `backend/CLAUDE.md` migrations table.
- [ ] Spec 01 amendments (§2) applied and Spec 01 tests updated and passing.
- [ ] Logged in as `owner@abctraders.demo`, register `XYZ12345` (500 kg, Dhanbad) and get a `LM-JH-DHN-…` UID.
- [ ] ABC Traders can't see `OTH-0001`, in the list or by URL (404).
- [ ] `officer.dhn@lm.demo` sees both instruments read-only, without Edit/Delete buttons.
- [ ] All §10 tests pass; `ruff`, eslint, `tsc` and the build are clean.
- [ ] `backend/CLAUDE.md` updated: `instruments` table, `scoping.py` rule, `Page[T]`, `errors.py`, `extra="forbid"` rule, `/instruments` API incl. `/meta`. `frontend/CLAUDE.md` updated: instrument routes, "no hard-coded enums" rule.