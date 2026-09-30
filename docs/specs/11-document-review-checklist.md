# Spec 11 — Document-review checklist and the deficiency loop (rev 1)

**Status:** Implemented, tested locally, **not yet applied to Supabase**
**Build order:** Step 11 (post-MVP addition to the original 10-step build order)
**Depends on:** Spec 03 rev 2 (`ALLOWED_TRANSITIONS`, `transition()`'s evaluation order, the "all
required documents present" gate on `DRAFT → SUBMITTED`, `REJECT_NOTE_MIN`), Spec 06 rev 1 (the
checklist-snapshot pattern: `inspection_checklist_items`, snapshotted at a specific transition,
`PATCH /api/inspections/{id}`'s partial-save shape)

## 1. Goal

The 8-status flow (`DRAFT, SUBMITTED, DOCUMENT_REVIEW, SCHEDULED, INSPECTION, APPROVED, REJECTED,
CERTIFICATE_ISSUED`) had two gaps at `DOCUMENT_REVIEW`:

1. No itemized checklist — the officer's "review" was just a status flip, with nothing recording
   *what* was checked before scheduling.
2. `DOCUMENT_REVIEW → REJECTED` was the only way out of a review that found a problem, and
   `REJECTED` is terminal (root `CLAUDE.md`: "Re-verification means a new application"). A missing
   photo or an illegible document doesn't deserve killing the whole application — it deserves a
   "fix and resubmit" loop.

This step adds both: a checklist snapshotted per application at `DOCUMENT_REVIEW`, and a new
non-terminal status, `DOCUMENTS_DEFICIENT`, that lets the business fix small problems and resubmit
without losing the application.

Demo story: an officer opens a `DOCUMENT_REVIEW` application, works through the 8-item checklist,
notices the previous certificate photo is unreadable, and sends it to `DOCUMENTS_DEFICIENT` with a
note. The business re-uploads a clearer photo and resubmits (`SUBMITTED`). The officer reopens it,
re-checks every item against the resubmission (the checklist resets, it doesn't carry over stale
answers), and once all 8 are checked, schedules the inspection.

**Out of scope:**
- Fee/payment verification. The checklist template deliberately excludes any payment/fee item —
  payments are mocked separately (root `CLAUDE.md`'s open "Payments: mocked in MVP" decision) and
  aren't part of this spec.
- A dedicated "deficient applications" queue distinct from `GET /applications?status=SUBMITTED` /
  `?status=DOCUMENT_REVIEW`. The existing status filter already covers it.
- Any limit on how many times an application can cycle through the deficiency loop. Nothing
  prevents `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT → SUBMITTED` repeating indefinitely; there is no
  "give up" transition beyond the existing `DOCUMENT_REVIEW → REJECTED`.
- Per-instrument-type checklist content (unlike spec 06's inspection checklist). Document review
  checks the submission as a whole — one generic list, not one per `InstrumentType`.

## 2. Access

- Role: `LM_OFFICER` for both the review-checklist PATCH and `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT`
  (unchanged from `DOCUMENT_REVIEW → REJECTED`'s existing role). `BUSINESS` for
  `DOCUMENTS_DEFICIENT → SUBMITTED` (the resubmit action — the same role that owns every other
  business-initiated transition, `DRAFT → SUBMITTED`).
- Scope: `scope_applications`, unchanged. Reaching a `DOCUMENT_REVIEW`/`DOCUMENTS_DEFICIENT`
  application at all already means the caller is an in-jurisdiction official or the owning
  business, same as every status since `SUBMITTED`.
- **No new identity check.** Unlike spec 06's inspection checklist (locked to the one assigned
  officer), the review checklist is open to **any in-scope `LM_OFFICER`** — there's no
  "assignment" concept at document-review time, only at scheduling.
- `PATCH /api/applications/{id}/review-checklist`: `LM_OFFICER` only at the router (mirrors
  `PATCH /api/applications/{id}/inspection`'s `Officer` dependency), and the application must be
  `DOCUMENT_REVIEW` (409 otherwise) — checked in the service, not the router, since it depends on
  the loaded row.

## 3. Data model (migration `0008_document_review_checklist`)

### `application_status` (enum, altered)
Gains `DOCUMENTS_DEFICIENT`. **Not** added to `TERMINAL_STATUSES` — the whole point is that the
business can still act on it.

### `document_review_checklist_items` (new table)
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `application_id` | UUID FK → applications, `ON DELETE CASCADE` | |
| `item_key` | text, not null | from the template, snapshotted |
| `label` | text, not null | snapshotted |
| `checked` | boolean, not null, default `false` | toggled via the PATCH endpoint |
| `created_at`, `updated_at` | timestamptz | `Timestamps` mixin |

Unique `(application_id, item_key)`.

- **Snapshotted when the application enters `DOCUMENT_REVIEW`** (`transition()`, the same timing
  spec 06 used for the inspection checklist: "snapshot at the transition that starts the review
  step," not at application creation — a `DRAFT` or `SUBMITTED` application has no checklist yet).
- **Reset, not recreated, on a second entry.** If the application cycles
  `DOCUMENTS_DEFICIENT → SUBMITTED → DOCUMENT_REVIEW` again, `item_key` is already taken (the
  unique constraint), so the existing rows have `checked` reset to `false` instead of a fresh
  insert. This is a **deliberate decision beyond the literal snapshot-once wording**: it means (a)
  `item_key`/`label` never change after the first pass, even if the live template is edited later
  (mirrors spec 06's non-retroactivity guarantee), and (b) the officer is forced to re-verify every
  item against the resubmission rather than inheriting stale answers from before the deficiency was
  raised. See §9 D3.
- Two migrations' worth of change (enum + table) were written as **one** file, not split, after
  checking the actual precedent: `0005_inspection_checklist.py` already combines
  `ALTER TYPE document_type ADD VALUE` with a `CREATE TABLE` in a single revision, with a comment
  explaining why that's safe (the new value is never used — inserted, defaulted, or compared —
  within the same transaction). `backend/CLAUDE.md`'s migration section does not document a
  separate-migration/autocommit requirement for enum adds, and this migration doesn't reference
  `application_status` from the new table at all, so `0008` mirrors `0005`'s combined pattern for
  consistency rather than inventing a new one. See §9 D5.

## 4. Checklist template (`app/core/document_review_templates.py`)

> **ASSUMPTION:** illustrative demo content for the officer's document-review step, not sourced
> from an actual Legal Metrology inspection manual, OIML recommendation or department SOP — the
> same caveat `core/instrument_types.py`, `core/application_types.py` and
> `core/inspection_templates.py` already carry for their own categories. Fee/payment verification
> is deliberately excluded (§1).

A single generic list (`DOCUMENT_REVIEW_CHECKLIST_TEMPLATE: list[DocumentReviewItemDef]`, 8 items):

```python
DocumentReviewItemDef("form_complete", "Application form complete and signed")
DocumentReviewItemDef(
    "identity_matches_registry",
    "Instrument identity (manufacturer, model, serial number) matches the registry",
)
DocumentReviewItemDef("documents_attached_legible", "All required documents attached and legible")
DocumentReviewItemDef(
    "address_jurisdiction_complete", "Address and jurisdiction details complete and correct"
)
DocumentReviewItemDef(
    "application_type_correct",
    "Application type correctly selected for the instrument's verification history",
)
DocumentReviewItemDef(
    "previous_certificate_referenced",
    "Previous certificate, if any, correctly referenced and consistent",
)
DocumentReviewItemDef(
    "photo_shows_nameplate", "Instrument photo clearly shows the nameplate/marking"
)
DocumentReviewItemDef(
    "no_conflicting_application", "No duplicate or conflicting active application exists"
)
```

`GET /api/applications/meta` returns it as `document_review_checklist: [{key, label}, ...]`,
following the existing `GET /inspections/meta`'s `checklist_templates` pattern — the frontend never
hardcodes the list.

## 5. API

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| `PATCH` | `/api/applications/{id}/status` `{"status": "DOCUMENTS_DEFICIENT"}` | in-scope `LM_OFFICER` | `{note}` (≥10 chars) → `ApplicationDetail` |
| `PATCH` | `/api/applications/{id}/status` `{"status": "SUBMITTED"}` from `DOCUMENTS_DEFICIENT` | owning `BUSINESS` | `{}` → `ApplicationDetail` |
| `PATCH` | `/api/applications/{id}/review-checklist` | in-scope `LM_OFFICER`, `DOCUMENT_REVIEW` only | `{"items": [{"item_key", "checked"}, ...]}` → `ApplicationDetail` |
| `GET` | `/api/applications/meta` | any logged-in | gains `document_review_checklist` |

### Schemas (`app/schemas/application.py`)
```python
class ReviewChecklistItemUpdate(StrictModel):
    item_key: str
    checked: bool


class ReviewChecklistUpdate(StrictModel):
    items: list[ReviewChecklistItemUpdate]


class ReviewChecklistItemOut(BaseModel):
    item_key: str
    label: str
    checked: bool


class ReviewChecklistTemplateItem(BaseModel):
    key: str
    label: str
```
`ApplicationDetail` gains `review_checklist: list[ReviewChecklistItemOut]`. `ApplicationMeta` gains
`document_review_checklist: list[ReviewChecklistTemplateItem]`.

### Behaviour rules
- **`DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT`**: requires `note` ≥ `DEFICIENCY_NOTE_MIN` (10) chars,
  a sibling constant to `REJECT_NOTE_MIN` (same value, kept separate so the two can diverge later
  without an unrelated rename) → 422 otherwise, same shape as the existing `REJECTED` check.
- **`DOCUMENTS_DEFICIENT → SUBMITTED`**: no extra validation beyond role/scope/edge — the same
  "all required documents present" gate that guards `DRAFT → SUBMITTED` applies here too, since
  it's keyed on `target == SUBMITTED`, not on the source status. In practice the documents were
  already present from the first submission; the business typically replaces or adds one.
- **`DOCUMENT_REVIEW → SCHEDULED`** (extended): 409 `"Document review checklist incomplete: …"`
  (naming the unchecked items' labels) unless every `document_review_checklist_items` row for the
  application has `checked = true`. Checked *after* `scheduled_date` validation, so a bad date
  still reports as a date error first (consistent with the existing evaluation order).
- **Entering `DOCUMENT_REVIEW`** (`SUBMITTED → DOCUMENT_REVIEW`, any occurrence): snapshot-or-reset
  the checklist (§3), write `DOCUMENT_REVIEW_STARTED` audit row
  (`details.checklist_item_count`, `details.reset`).
- **`PATCH /api/applications/{id}/review-checklist`**: 409 if the application isn't
  `DOCUMENT_REVIEW`. Unknown `item_key` → 422 (`field="items"`), mirroring
  `PATCH /api/inspections/{id}`'s unknown-key handling. Partial: only the entries present are
  applied. No audit row per call — same precedent as the inspection checklist's own PATCH (only
  start/submit-equivalent events are audited there).

## 6. Backend implementation
```
app/core/document_review_templates.py   DOCUMENT_REVIEW_CHECKLIST_TEMPLATE (ASSUMPTION)
app/core/application_types.py           + ApplicationStatus.DOCUMENTS_DEFICIENT; STATUS_LABELS entry
app/models/document_review_checklist.py DocumentReviewChecklistItem (UUIDPk, Timestamps)
app/models/__init__.py                  registers it for Alembic autogenerate
app/schemas/application.py              ReviewChecklistItemUpdate/Update/Out, ReviewChecklistTemplateItem;
                                         ApplicationDetail.review_checklist; ApplicationMeta.document_review_checklist
app/services/applications.py            ALLOWED_TRANSITIONS: 2 new edges; DEFICIENCY_NOTE_MIN;
                                         transition(): note-length check, SCHEDULED checklist gate,
                                         snapshot-or-reset on entering DOCUMENT_REVIEW;
                                         review_checklist_items(), patch_review_checklist()
app/routers/applications.py             PATCH /{id}/review-checklist; _detail() includes review_checklist
alembic/versions/0008_document_review_checklist.py
```

## 7. Tests (backend)

New file `tests/test_document_review_checklist.py`:
- Snapshot created on `SUBMITTED → DOCUMENT_REVIEW` (item keys match the template, all unchecked,
  one `DOCUMENT_REVIEW_STARTED` audit row); snapshot survives a template change across a
  deficiency-loop re-review (patches the name as looked up in `services/applications.py`, the
  actual call site, not the defining module).
- `PATCH /review-checklist`: partial updates persist, other rows untouched; unknown `item_key` →
  422; only allowed during `DOCUMENT_REVIEW` (409 otherwise); role-rejected for every non-officer
  role; out-of-jurisdiction officer → 404 (org isolation).
- `DOCUMENT_REVIEW → SCHEDULED`: blocked (409) with all-unchecked, blocked with all-but-one
  checked, succeeds once every item is checked.
- `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT`: `None`/empty/too-short note → 422; wrong role → 403;
  valid note → 200, history note recorded.
- `DOCUMENTS_DEFICIENT → SUBMITTED`: officer (wrong role) → 403; owning business → 200.
- Full loop: `DOCUMENT_REVIEW` (all checked) → `DOCUMENTS_DEFICIENT` → `SUBMITTED` →
  `DOCUMENT_REVIEW` again — same row IDs, all reset to unchecked, and the `SCHEDULED` gate applies
  again (not silently satisfied from the first pass).
- `GET /applications/meta` includes `document_review_checklist` matching the template exactly.

Extended existing files for the new gate's ripple effects:
- `tests/conftest.py`: `make_application`'s `S.SCHEDULED`/`INSPECTION`/`APPROVED` branch now checks
  off every review-checklist item before scheduling (otherwise every fixture that reaches
  `SCHEDULED` would 409); a new `S.DOCUMENTS_DEFICIENT` branch.
- `tests/test_scheduling.py`: every test that drives `DOCUMENT_REVIEW → SCHEDULED` directly through
  the API (not via the `make_application` factory) now checks off the checklist first via a new
  `_check_all_review_items` helper.
- `tests/test_applications_rbac.py` / `tests/test_applications_stats.py` /
  `tests/test_instruments_lock.py`: status lists/parametrizations extended for the new enum value.

## 8. Demo seed

No seed changes. The demo drives the loop live: open the seeded `DOCUMENT_REVIEW` application,
check the 8 items (or deliberately leave one unchecked to show the `SCHEDULED` 409), or send it to
`DOCUMENTS_DEFICIENT` with a note and resubmit as the business — the same "drive it live" approach
specs 05–08 used for their own new transitions.

## 9. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Checklist content: one generic list, or per-`InstrumentType` (like spec 06)? | **One generic list.** Document review checks the submission as a whole (form, documents, identity match, jurisdiction), not category-specific technical content — that's the field inspection's job. |
| D2 | Fee/payment as a checklist item? | **Excluded.** Payments are mocked separately (root `CLAUDE.md`'s open decision) and out of scope for this spec. |
| D3 | Re-entering `DOCUMENT_REVIEW` after a deficiency loop: recreate the checklist, or reset it? | **Reset** (`checked = false` on the existing rows), not recreated — the unique `(application_id, item_key)` constraint would reject a naive re-insert, and resetting forces genuine re-verification against the resubmission rather than inheriting stale answers, while keeping `item_key`/`label` snapshotted from the first pass. |
| D4 | Who may decide `DOCUMENTS_DEFICIENT`, and does it need a note? | Same as `REJECTED`: any in-scope `LM_OFFICER`, note ≥ 10 chars — consistency with the existing terminal-rejection path's UX, just non-terminal. |
| D5 | Enum-add migration: combined with the table create, or split into its own revision? | **Combined**, mirroring `0005`'s actual precedent (enum add + table create in one file) rather than the task brief's assumption that `backend/CLAUDE.md` documents a split/autocommit requirement — it doesn't; `0005`'s own comment explains why combining is safe (the new value is never used within the same transaction), and that holds here too. Flagged explicitly rather than silently following an unverified premise. |
| D6 | Does the "all required documents present" gate need a variant for resubmission? | **No.** It's already keyed on `target == SUBMITTED` regardless of source status, so `DOCUMENTS_DEFICIENT → SUBMITTED` reuses it unchanged. |

## 10. Acceptance criteria

- [x] `0008_document_review_checklist` round-trips locally (`downgrade base`, `upgrade head`),
  applies cleanly against `lm_test`. **Not applied to Supabase** — that's an explicit later step.
- [x] `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT` (LM_OFFICER, note ≥10 chars) and
  `DOCUMENTS_DEFICIENT → SUBMITTED` (BUSINESS) are reachable, and `DOCUMENTS_DEFICIENT` is not in
  `TERMINAL_STATUSES`.
- [x] `DOCUMENT_REVIEW → SCHEDULED` is blocked until every review-checklist item is checked, and
  succeeds immediately once they are.
- [x] The checklist snapshot is created on first entry into `DOCUMENT_REVIEW` and reset (not
  duplicated) on a later re-entry via the deficiency loop.
- [x] `PATCH /api/applications/{id}/review-checklist` is LM_OFFICER-only, DOCUMENT_REVIEW-only, and
  org/jurisdiction-scoped (404 out of scope).
- [x] `GET /api/applications/meta` serves the checklist template; nothing hardcodes it client-side.
- [x] `ruff check`/`ruff format --check` clean; full backend test suite green, including the new
  file and every ripple-effect update (§7).
- [x] `backend/CLAUDE.md` updated: migration table (`0008`, explicitly marked not-yet-applied to
  Supabase), status-flow diagram and a new "Document review checklist" subsection, data model
  section, table list, API block.

## 11. Verification record

Backend (`pytest`, local `lm_test` via `TEST_DATABASE_URL`): see the task's own final report for
the exact pass count and `ruff` output — recorded there rather than duplicated here to avoid the
two ever silently drifting apart.

Migration tested with `alembic downgrade base && alembic upgrade head` against `lm_test` only.
**Supabase was never touched** — no command in this step ran against `backend/.env`'s
`DATABASE_URL`; applying `0008` to Supabase is an explicit, separate, later step per the task
brief's safety rule.
