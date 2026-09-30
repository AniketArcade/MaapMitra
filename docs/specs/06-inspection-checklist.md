# Spec 06 — Inspection checklist and measurements (rev 1)

**Status:** Ready for Claude Code (all open decisions resolved, see §12)
**Build order:** Step 6 of 10
**Depends on:** Spec 05 rev 2 (`inspections` table, `ALLOWED_TRANSITIONS`, `transition()`'s evaluation
order, `scope_applications`, the `(assigned_officer_id, scheduled_date)` index, the lock order
"application, then instrument"), Spec 03 rev 2 (documents upload pipeline, `DocumentType`,
`REQUIREMENTS`, `MAX_DOCUMENTS`), Spec 02 rev 2 (`InstrumentType`, `UNIT_FAMILY`,
`capacity`/`capacity_unit`, `accuracy_class`)

## 1. Goal

Root `CLAUDE.md`'s lifecycle is `… Schedule → Field inspection → Approve/Reject …`. Spec 05 built
Schedule and explicitly reserved everything after it (§14): `SCHEDULED → INSPECTION`, the checklist,
the measurements, evidence photos and `POST /api/inspections/{id}/submit`. This step builds "Field
inspection" itself: the assigned officer starts it, works a per-instrument-type checklist and a set
of load-point measurements, attaches evidence photos, records overall remarks, and submits. The
application's status becomes `INSPECTION` when started and **stays** `INSPECTION` through and after
submission — the Approve/Reject decision, and what it does with this checklist, is step 7.

Demo story: `officer.dhn@lm.demo` opens the seeded ABC Traders application once it reaches
`SCHEDULED` (spec 05's demo), starts the inspection, works through the weighing-scale checklist,
records readings at 25/50/75/100% of the scale's 30 kg capacity, attaches a photo, adds a remark,
and submits. The application now reads "Inspection submitted, awaiting decision" and is ready for
step 7.

**Out of scope:**
- Approve/Reject and certificate issuance (step 7/8) — this step ends at a submitted, locked
  checklist; the application status stays `INSPECTION`.
- Reassigning an in-progress inspection to a different officer or to GATC (consistent with spec 05
  D2 and §14).
- Editing after submit — there is no "unsubmit" in this step.
- A dedicated "My inspections" list or page: the existing
  `GET /applications?status=INSPECTION&sort=scheduled_asc` (spec 05) already covers it.
- Offline/PWA support and GPS capture at inspection time (root `CLAUDE.md` defers PostGIS/Leaflet
  generally; capturing coordinates here would need one of them).

## 2. Amendments to Spec 03 (documents) — apply in this step

| # | Problem | Fix |
|---|---|---|
| A1 | Upload/delete are BUSINESS-only and DRAFT-only, but *implicitly*: `documents.upload()` calls `applications_service.load(db, user, application_id)` with no explicit role check — it only works because `scope_applications` already hides DRAFT rows from officials, so only the owning business can ever load one. Evidence photos need the opposite actor (the assigned LM_OFFICER) and the opposite status (`INSPECTION`, never `DRAFT`) — scoping alone can't restrict it to *the assigned* officer, since any in-jurisdiction officer can already read an `INSPECTION`-status application. | `upload()`/`delete()` branch on `document_type`. For `DocumentType.INSPECTION_EVIDENCE`: require `application.status == INSPECTION`, `application.inspection.assigned_officer_id == user.id` (explicit identity check, §3), and — for delete — `application.inspection.submitted_at is None`. Every other `document_type` keeps the unchanged BUSINESS/DRAFT behaviour. |
| A2 | One shared `MAX_DOCUMENTS = 10` (`core/application_types.py`) counts every row for an application (`documents.py`'s `_count()`). Evidence photos would compete with the business's own document slots, in either direction. | Count separately: `_count()` gains a `document_type` filter. The existing cap applies to `document_type != INSPECTION_EVIDENCE`; a new `MAX_EVIDENCE_PHOTOS = 10` (ASSUMPTION) applies to `document_type == INSPECTION_EVIDENCE` only. |
| A3 | `ApplicationDetail.requirements` (`schemas/application.py`) iterates `for t in DocumentType`, so adding `INSPECTION_EVIDENCE` to the enum would add a spurious "Inspection evidence — not required" row to the business-facing requirements checklist. | A new `BUSINESS_DOCUMENT_TYPES` frozenset (`core/application_types.py`) excludes `INSPECTION_EVIDENCE`; `requirements` iterates that set instead of the full enum. |

## 3. Access

- Reads go through `scope_applications` exactly as spec 05 §3 — an inspection, its checklist, its
  measurements and its evidence are all reached through the application. A new `scope_inspections`
  helper (`services/scoping.py`) joins `Inspection → Application` and applies the same predicate, so
  `GET/PATCH /api/inspections/{id}` follow the one-scoped-query rule (backend/CLAUDE.md) without
  duplicating `scope_applications`'s logic.
- New beyond role and scope: an **identity** check. `inspections.assigned_officer_id` gates:
  1. starting the inspection (`SCHEDULED → INSPECTION`),
  2. `PATCH /api/inspections/{id}` (checklist/measurement/remarks edits),
  3. uploading or deleting an `INSPECTION_EVIDENCE` document,
  4. `POST /api/inspections/{id}/submit`.

  An in-scope `LM_OFFICER` who is *not* the assigned officer gets **403**
  `"Only the assigned officer can do this"` — distinct from the out-of-jurisdiction/wrong-org
  **404** `scope_applications`/`scope_inspections` already produce. `BUSINESS`,
  `DISTRICT_ADMIN`/`STATE_ADMIN`/`SUPER_ADMIN` and `GATC` keep the existing role-based 403/404: only
  the assigned officer touches an inspection's contents in this step (§12 D1).
- `ALLOWED_TRANSITIONS` (`services/applications.py`) flips:
  ```python
  (S.SCHEDULED, S.INSPECTION): Edge(frozenset({Role.LM_OFFICER}), enabled=True),  # step 6
  ```
  `Edge(roles, enabled)` alone expresses role and enablement, not "this specific officer" — the same
  gap spec 05 hit for `SCHEDULED`'s required date and `REJECTED`'s required note. `transition()`
  needs one more edge-specific check, inserted right after the existing `not edge.enabled` check
  (`app/services/applications.py`):
  ```python
  if target == S.INSPECTION and application.inspection.assigned_officer_id != user.id:
      raise Forbidden("Only the assigned officer can do this")
  ```

## 4. Checklist and measurement templates (`app/core/inspection_templates.py`)

> **ASSUMPTION:** the checklist items and measurement points below are illustrative demo content,
> not sourced from an actual Legal Metrology inspection manual or an OIML recommendation. Verify
> with a domain expert before any non-demo use — the same caveat `core/instrument_types.py` and
> `core/application_types.py` already carry for their own categories.

- `CHECKLIST_TEMPLATES: dict[InstrumentType, list[ChecklistItemDef]]` — one literal list per of the
  7 `InstrumentType` values, each item `{key: str, label: str}`. Only `WEIGHING_SCALE` is seeded and
  demoable; write it out in full:
  ```python
  CHECKLIST_TEMPLATES[InstrumentType.WEIGHING_SCALE] = [
      ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
      ChecklistItemDef("no_damage", "No visible damage or corrosion"),
      ChecklistItemDef("platform_level", "Platform/pan level and stable"),
      ChecklistItemDef("zero_setting", "Zero-setting functions correctly"),
      ChecklistItemDef("display_legible", "Display legible and accurate"),
      ChecklistItemDef("tare_function", "Tare function works correctly"),
      ChecklistItemDef("repeatability", "Repeat readings are consistent (repeatability check)"),
  ]
  ```
  The remaining 6 lists (`WEIGHBRIDGE`, `WEIGHT`, `FUEL_DISPENSER`, `MEASURE_LENGTH`,
  `MEASURE_VOLUME`, `OTHER`) follow the same shape (5–8 items each) and are drafted at
  implementation time. Every `key` must be unique within its own list — it becomes
  `inspection_checklist_items.item_key`.
- `MEASUREMENT_TEMPLATES: dict[InstrumentType, list[float]]` — **fractions of the instrument's own
  `capacity`**, never fixed numbers:
  ```python
  MEASUREMENT_TEMPLATES = {
      InstrumentType.WEIGHING_SCALE: [0.25, 0.5, 0.75, 1.0],
      InstrumentType.WEIGHBRIDGE: [0.25, 0.5, 0.75, 1.0],
      InstrumentType.FUEL_DISPENSER: [0.25, 0.5, 0.75, 1.0],
      InstrumentType.MEASURE_VOLUME: [0.25, 0.5, 0.75, 1.0],
      InstrumentType.MEASURE_LENGTH: [0.25, 0.5, 0.75, 1.0],
      InstrumentType.WEIGHT: [1.0],   # a reference standard, not a ranged device: one point
      InstrumentType.OTHER: [1.0],
  }
  ```
  At start time, for each fraction `f`: `label = f"{int(f * 100)}% of capacity"`,
  `expected_value = instrument.capacity * f`, `unit = instrument.capacity_unit` — computed once and
  snapshotted (§5), never recomputed from a live template later.

  > **ASSUMPTION:** multi-point load testing at fractions of rated capacity approximates real
  > verification procedure (e.g. OIML R76 for weighing instruments); exact legal tolerance formulas
  > are not encoded anywhere. The officer judges pass/fail by eye, recorded per checklist item as
  > `result`, using the instrument's own `accuracy_class` — `observed_value` is recorded for the
  > record, not used to auto-compute a verdict.

- `GET /api/inspections/meta` returns both templates by label (never resolved per-instrument
  values) plus `max_evidence_photos`, following the existing `GET /instruments/meta` /
  `GET /applications/meta` pattern: the frontend never hardcodes checklist or measurement content.

## 5. Data model (migration `0005_inspection_checklist`)

### `inspections` (altered)
| column | type | notes |
|---|---|---|
| `overall_remarks` | text, null | free text, filled at or before submit |
| `submitted_at` | timestamptz, null | **the** lock: non-null means the checklist can no longer be edited |
| `submitted_by` | UUID FK → users, `ON DELETE RESTRICT`, null | always `assigned_officer_id` in this step — no delegated submission |

### `inspection_checklist_items`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `inspection_id` | UUID FK → inspections, `ON DELETE CASCADE` | |
| `item_key` | text, not null | from the template, snapshotted |
| `label` | text, not null | snapshotted — a later template edit never changes an in-progress or already-submitted inspection |
| `result` | enum `checklist_result` (`PASS`, `FAIL`, `NA`), null | null until the officer answers it |
| `remarks` | text, null | |
| `created_at`, `updated_at` | timestamptz | `Timestamps` mixin |

Unique `(inspection_id, item_key)`.

### `inspection_measurements`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `inspection_id` | UUID FK → inspections, `ON DELETE CASCADE` | |
| `label` | text, not null | snapshotted, e.g. `"50% of capacity"` |
| `unit` | text, not null | snapshotted `capacity_unit` at start time |
| `expected_value` | `numeric(12,3)`, not null | snapshotted `capacity * fraction` |
| `observed_value` | `numeric(12,3)`, null | filled by the officer |
| `created_at`, `updated_at` | timestamptz | |

Unique `(inspection_id, label)`.

- Both child tables are populated **inside the same transaction** as the `SCHEDULED → INSPECTION`
  status change, from `CHECKLIST_TEMPLATES[instrument.instrument_type]` /
  `MEASUREMENT_TEMPLATES[instrument.instrument_type]` (one insert per item/point). This needs the
  instrument row (`capacity`, `capacity_unit`, `instrument_type`), so it reuses spec 05's lock
  order — **application, then instrument** — with a bare `SELECT ... FOR UPDATE` (not
  `instruments_service.get()`; same reason backend/CLAUDE.md's Scheduling section already documents:
  a joinedload-eager service helper's `populate_existing=True` would re-hydrate the just-mutated
  `Application` row from its stale pre-commit value).
- Migration hand-review: new enum `checklist_result` (autogenerate misses its `downgrade` drop, as
  it did for spec 02/03's enums); two new child-table FKs' cascade behavior; round-trip
  (`upgrade head` → `downgrade -1` → `upgrade head`) and `alembic check`.
- **Corrects backend/CLAUDE.md's Data model table**, which currently lists a single
  `inspection_checklist` table (a placeholder from before this spec existed) — replace it with
  `inspection_checklist_items`, `inspection_measurements`, and the 3 new `inspections` columns
  (§13 acceptance criteria).

## 6. API

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| `GET` | `/api/inspections/meta` | any logged-in | → `InspectionMeta` |
| `PATCH` | `/api/applications/{id}/status` `{"status": "INSPECTION"}` | assigned officer | → `ApplicationDetail` (starts it; creates the snapshot rows) |
| `GET` | `/api/inspections/{id}` | scope + Reader | → `InspectionDetail` |
| `PATCH` | `/api/inspections/{id}` | assigned officer, not yet submitted | `InspectionUpdate` → `InspectionDetail` |
| `POST` | `/api/documents` (`document_type=INSPECTION_EVIDENCE`) | assigned officer, status INSPECTION, not submitted | existing multipart shape → `DocumentOut` |
| `DELETE` | `/api/documents/{id}` (evidence) | assigned officer, not submitted | → 204 |
| `POST` | `/api/inspections/{id}/submit` | assigned officer, not yet submitted | `{}` → `InspectionDetail` |

### Schemas (`app/schemas/inspection.py`)
```python
class ChecklistResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"

class ChecklistItemUpdate(StrictModel):
    item_key: str
    result: ChecklistResult | None = None
    remarks: Notes | None = None

class MeasurementUpdate(StrictModel):
    label: str
    observed_value: condecimal(max_digits=12, decimal_places=3) | None = None

class InspectionUpdate(StrictModel):
    """Partial: only the list entries present are applied; other rows are untouched."""
    checklist_items: list[ChecklistItemUpdate] | None = None
    measurements: list[MeasurementUpdate] | None = None
    overall_remarks: Notes | None = None

class ChecklistItemOut(BaseModel):
    item_key: str
    label: str
    result: ChecklistResult | None
    remarks: str | None

class MeasurementOut(BaseModel):
    label: str
    unit: str
    expected_value: float
    observed_value: float | None

class InspectionDetail(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    scheduled_date: date
    assigned_officer_name: str
    checklist_items: list[ChecklistItemOut]
    measurements: list[MeasurementOut]
    evidence: list[DocumentOut]
    overall_remarks: str | None
    submitted_at: datetime | None
    can_edit: bool   # caller is the assigned officer and submitted_at is None

class InspectionMeta(BaseModel):
    checklist_templates: dict[InstrumentType, list[LabelledValue]]  # key -> label
    measurement_fractions: dict[InstrumentType, list[float]]
    max_evidence_photos: int
```
`InspectionOut` (on `ApplicationDetail`, `schemas/application.py`) gains `id: uuid.UUID` — it's the
only place the frontend learns the inspection id to call the endpoints above.

### Behaviour rules
- **Starting** (`PATCH /applications/{id}/status {"status": "INSPECTION"}`): reuses spec 03 §3's
  evaluation order unchanged (scope → edge exists → role → enabled → edge rules → apply), with the
  assigned-officer check from §3 as one more edge rule. On success, in the same transaction: lock
  the instrument row (bare `FOR UPDATE`, §5), bulk-insert the checklist/measurement snapshot rows,
  write the history row (`"Inspection started"`), and audit `INSPECTION_STARTED`
  (`application_id`, `checklist_item_count`, `measurement_count`).
- **`GET /api/inspections/{id}`**: `scope_inspections`; 404 if out of scope, otherwise any Reader
  role that can already see the application.
- **`PATCH /api/inspections/{id}`**: 409 `"This inspection has already been submitted"` once
  `submitted_at` is set. An `item_key`/`label` that doesn't match an existing row for this
  inspection → 422 (`field="checklist_items"` / `"measurements"`, message naming the bad key/label —
  `StrictModel`'s `extra="forbid"` still rejects unrelated fields). `result` must be one of
  `PASS`/`FAIL`/`NA` (plain enum validation → 422). Repeated partial saves are allowed — each call
  only touches the rows named in that request, so the officer can save progress screen by screen
  (frontend/CLAUDE.md's "keep draft progress" rule is satisfied by re-fetching on each screen, not
  by relying on client memory across a session).
- **Evidence upload/delete**: identical sniffing/size/storage-path pipeline to spec 03
  (`applications/{application_id}/{document_id}.{ext}`, unchanged) with the actor/precondition/cap
  branch from §2 (A1, A2).
- **`POST /api/inspections/{id}/submit`**: 422 if any `checklist_items[*].result` or
  `measurements[*].observed_value` is still null, naming which keys/labels are incomplete. On
  success, in one transaction: set `submitted_at = now()`, `submitted_by = user.id`; write
  `INSPECTION_SUBMITTED` audit row with `details.checklist_summary` = counts of
  `PASS`/`FAIL`/`NA` (so step 7 doesn't have to re-derive it). **Application `status` is unchanged**
  by submit — it stays `INSPECTION`. Submitting twice → 409 (same message as the PATCH lock), not a
  second audit row.

## 7. Backend implementation
```
app/core/inspection_templates.py     CHECKLIST_TEMPLATES, MEASUREMENT_TEMPLATES per InstrumentType
app/core/application_types.py        + DocumentType.INSPECTION_EVIDENCE; + BUSINESS_DOCUMENT_TYPES;
                                      + MAX_EVIDENCE_PHOTOS
app/models/inspection.py             + overall_remarks, submitted_at, submitted_by
app/models/inspection_checklist.py   InspectionChecklistItem, InspectionMeasurement (UUIDPk, Timestamps)
app/schemas/inspection.py            ChecklistResult, *Update, *Out, InspectionDetail, InspectionMeta
app/schemas/application.py           InspectionOut.id
app/services/scoping.py              + scope_inspections (joins Inspection -> Application)
app/services/applications.py         enable SCHEDULED->INSPECTION edge; assigned-officer check;
                                      snapshot-row creation on start (transition())
app/services/inspections.py          new: get(), patch(), submit(), completeness check
app/services/documents.py            evidence actor/status/cap branch in upload()/delete(); _count()
                                      gains a document_type filter
app/routers/inspections.py           new: GET /meta, GET/PATCH /{id}, POST /{id}/submit
app/main.py                          register inspections router
alembic/versions/0005_inspection_checklist.py
```

## 8. Frontend implementation

| Route | Who | Content |
|---|---|---|
| `app/applications/[id]/page.tsx` (existing, extended) | LM_OFFICER (assigned) | "Start inspection" button when `allowed_actions` includes `INSPECTION`; navigates to `/inspections/{inspection.id}` |
| `app/inspections/[id]/page.tsx` (new) | LM_OFFICER (assigned), mobile-first | Instrument details → Checklist → Measurements → Photos → Remarks → Submit |

- The mobile flow matches frontend/CLAUDE.md's existing "Officer field inspection" section, minus
  Approve/Reject (that stays step 7 — update that section's flow line to end at **Submit**, and add
  a one-line note that Approve/Reject is a separate step-7 screen reached from the application page
  afterward).
- One step per screen, sticky bottom action button, large tap targets. Photo upload reuses the
  `onFile`/`uploadDocument` pattern from `app/applications/[id]/page.tsx`
  (`<input type="file" accept="image/*" capture="environment">`, `FormData`, per-item
  uploading/error state), just pointed at `document_type=INSPECTION_EVIDENCE`.
- Confirm dialog before **Submit** (irreversible in this step, per frontend/CLAUDE.md's existing
  rule for Approve/Reject — Submit is this step's equivalent irreversible action).
- Plain `useState` per screen + `FormField`/`SelectField` for checklist rows, matching the codebase's
  existing form pattern (no react-hook-form/zod); `ApiError.fieldErrors` surfaces the 422s from §6.
- `lib/api.ts` / `lib/types.ts`: `getInspectionMeta()`, `getInspection()`, `patchInspection()`,
  `submitInspection()`; `InspectionDetail`, `ChecklistItemOut`, `MeasurementOut` types.
- Dashboard: the existing "Needs your attention" rules array (spec 05 §8) gains one row —
  `{status: INSPECTION, hint: "Continue inspection"}` — pointing at `/applications/{id}` (which then
  shows "Resume inspection" linking to `/inspections/{id}`). No new list endpoint: "my inspections"
  is `GET /applications?status=INSPECTION&sort=scheduled_asc`, already built in spec 05.

## 9. Tests (backend)

**Starting** (`tests/test_inspection_start.py`)
- Success: assigned officer, `SCHEDULED` → `INSPECTION`; exactly one checklist item row per
  `CHECKLIST_TEMPLATES[instrument_type]` entry and one measurement row per
  `MEASUREMENT_TEMPLATES[instrument_type]` fraction, with correctly computed `expected_value`/`unit`.
- A different in-scope officer → 403 `"Only the assigned officer can do this"`; out-of-jurisdiction
  officer → 404; BUSINESS/admins/GATC → 403.
- Wrong current status (e.g. `DOCUMENT_REVIEW`) → 409 `"Invalid status change"` (edge doesn't exist).
- Changing `CHECKLIST_TEMPLATES` after an inspection has started doesn't retroactively alter its
  already-created rows (snapshot, not a live reference).

**Checklist/measurement PATCH** (`tests/test_inspection_checklist.py`)
- Partial updates persist per-row; unrelated rows untouched. Unknown `item_key`/`label` → 422.
  Invalid `result` value → 422. After `submitted_at` is set → 409 for any further PATCH.
  Role/identity checks mirror Starting's.

**Evidence** (`tests/test_inspection_evidence.py`)
- Assigned officer uploads while `INSPECTION` and not submitted → 201. BUSINESS cannot upload
  `INSPECTION_EVIDENCE` even on their own application. A different in-scope officer → 403.
  After submit → 409/blocked. Evidence count and business-document count are independent: uploading
  `MAX_EVIDENCE_PHOTOS` evidence photos doesn't block a business document upload and vice versa.
  Delete mirrors upload's rule; `ApplicationDetail.requirements` never lists `INSPECTION_EVIDENCE`
  (A3).

**Submit** (`tests/test_inspection_submit.py`)
- Incomplete (any null `result`/`observed_value`) → 422 naming the missing keys/labels. Complete →
  sets `submitted_at`/`submitted_by`, writes one `INSPECTION_SUBMITTED` audit row with a correct
  `checklist_summary`; application `status` is unchanged (`INSPECTION`). Submitting twice → 409, no
  second audit row (idempotency).

**Org isolation / RBAC** — parametrized the same way as spec 05 §11 for every new endpoint:
BUSINESS, an admin role, GATC, an out-of-jurisdiction officer, and a same-jurisdiction
non-assigned officer, each getting the expected 403/404.

## 10. Demo seed

No seed changes. The seeded `WEIGHING_SCALE` application already reaches `SCHEDULED` live in
spec 05's demo; this step's demo drives Start → checklist → measurements → photo → Submit live, the
same approach spec 05 took for scheduling. To repeat the demo, re-seed.

## 11. Deferred and recorded for later steps

- **Step 7:** Approve/Reject consuming `submitted_at` and the checklist/measurement data
  (`checklist_summary` from the submit audit row is a ready-made starting point).
- Reassigning an in-progress inspection to another officer or to GATC.
- Editing after submit / an "unsubmit" action.
- A richer "My inspections" view (overdue/today labels, grouping) beyond the existing
  `sort=scheduled_asc` filter.
- Offline queueing of evidence uploads for poor field connectivity.
- GPS capture at inspection time (needs a mapping decision root `CLAUDE.md` currently defers).

## 12. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Who may start and work an inspection? | **The assigned officer only** (`inspections.assigned_officer_id`), no jurisdiction-wide override. Consistent with spec 05 D2's self-assign model. |
| D2 | Checklist content: one generic list, or per-instrument-type? | **Per-`InstrumentType` templates** (7 lists), each marked `ASSUMPTION`. Only `WEIGHING_SCALE`'s is demoable against seed data. |
| D3 | Checklist/measurement storage: JSONB blob, or relational rows? | **Relational**: `inspection_checklist_items` and `inspection_measurements`, one row per item/point, snapshotted from the template at start time. Supersedes the singular `inspection_checklist` table backend/CLAUDE.md previously anticipated. |
| D4 | Evidence photos: reuse `documents`, or a new table? | **Reuse `documents`** with a new `DocumentType.INSPECTION_EVIDENCE`, amending the step-3 upload rules (§2) rather than duplicating the upload/storage/signed-URL pipeline. |
| D5 | Measurement points | **Fractions of the instrument's own `capacity`** (ASSUMPTION), snapshotted as `expected_value`/`unit` at start time — never a live formula. |
| D6 | Tolerance/pass-fail computation | **Not automated.** The officer records `observed_value` and separately judges `result` per checklist item against the instrument's `accuracy_class` (ASSUMPTION — no OIML tolerance tables encoded). |
| D7 | Does starting or submitting change `application.status` beyond `INSPECTION`? | **No.** Starting sets it to `INSPECTION`; submitting leaves it there. Only step 7's Approve/Reject moves it further. |

## 13. Acceptance criteria

- [x] `0005_inspection_checklist` round-trips locally (`upgrade`, `downgrade -1`, `upgrade`),
  `alembic check` clean, and applies to Supabase.
- [x] As the assigned officer (`officer.dhn@lm.demo`): "Start inspection" moves the seeded
  application to `INSPECTION` and creates the correct checklist/measurement rows for
  `WEIGHING_SCALE`.
- [x] A different in-scope officer gets 403 on start, PATCH, evidence upload and submit; an
  out-of-jurisdiction officer gets 404; BUSINESS/admins/GATC get 403.
- [x] Checklist and measurement PATCH persist partial progress across screens and lock (409) once
  submitted.
- [x] Evidence photo upload/delete works under the new actor/status rules without breaking the
  step-3 business-document cap or its DRAFT-only rule, and never appears in `requirements`.
- [x] Submit is all-or-nothing (422 on incomplete) and idempotent (409 on a second call); the
  application's `status` stays `INSPECTION` after submit.
- [x] The mobile inspection flow (`/inspections/{id}`) works end-to-end in Chrome as
  `officer.dhn@lm.demo` against the seeded application: Instrument details → Checklist →
  Measurements → Photos → Remarks → Submit, with a confirmation before Submit.
- [x] `ruff`, `eslint`, `tsc` and the build are clean.
- [x] `backend/CLAUDE.md` updated: the Data model table's `inspection_checklist` line replaced with
  `inspection_checklist_items`/`inspection_measurements` and the 3 new `inspections` columns; the
  API block's reserved `POST /api/inspections`/`.../submit` lines replaced with the real routes
  above; new audit actions (`INSPECTION_STARTED`, `INSPECTION_SUBMITTED`); the documents-upload
  amendment (§2). `frontend/CLAUDE.md` updated: the "Officer field inspection" flow line split at
  Submit, with Approve/Reject named as step 7. Root `CLAUDE.md` step 6 marked ✅ linking to this
  spec.

## 14. Verification record

Backend (`pytest`, local `lm_dev`/`lm_test`): full suite green — 4 new test files
(`test_inspection_start.py`, `test_inspection_checklist.py`, `test_inspection_evidence.py`,
`test_inspection_submit.py`, ~30 tests covering success, snapshot correctness, template-change
non-retroactivity, assigned-officer/role/scope rejections, partial PATCH, unknown-key 422,
post-submit lock, evidence actor/status rules and independent caps, incomplete/complete/double
submit) plus `test_applications_transitions.py`'s repointed "not yet enabled" test (now
`INSPECTION → APPROVED`, step 7) and `test_applications_rbac.py`'s `test_owner_only_endpoints`
updated for the router now admitting `LM_OFFICER` (404, not 403, on a DRAFT application it can't
see). 360 tests pass; `ruff check`/`ruff format --check` clean. Migration round-trips locally and
applied cleanly to Supabase (`alembic check` clean after).

Two real bugs were found and fixed during implementation, not anticipated by this spec:
1. `documents.upload()`'s locked re-check query lacked `joinedload(Application.inspection)`, so
   the evidence-actor check raised `lazy="raise"` under the row lock even though the pre-lock copy
   had it loaded (`populate_existing` doesn't preserve relationships outside the new query).
2. That same re-check's `with_for_update()` (and `delete()`'s) needed `of=Application`: Postgres
   refuses `FOR UPDATE` across the nullable side of the `LEFT JOIN inspections` the eager-load adds.

Frontend (`tsc --noEmit`, `eslint`, `next build`): clean, after fixing
`react-hooks/set-state-in-effect` on the new page's load effect (suppressed with a comment — the
same load-on-mount pattern used in `app/applications/[id]/page.tsx` doesn't trigger it, and
bisection didn't find a real synchronous setState to fix).

Manual, in Chrome against local dev servers (`lm_dev`, `STORAGE_BACKEND=memory`): as
`officer.dhn@lm.demo`, scheduled a live `DOCUMENT_REVIEW` application, clicked **Start
inspection**, filled all 7 `WEIGHING_SCALE` checklist items and all 4 measurements (expected
values correctly shown as 25/50/75/100% of the instrument's own capacity), skipped the photo step,
added an overall remark, and **Submit** — the confirmation dialog appeared, the application
returned to `/applications/{id}` still showing status `INSPECTION` with "Inspection started" in
the timeline, and re-opening the inspection showed "This inspection has been submitted and is
read-only."
