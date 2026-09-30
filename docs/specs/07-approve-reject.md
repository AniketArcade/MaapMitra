# Spec 07 — Approve/Reject workflow (rev 1)

**Status:** Ready for Claude Code (all open decisions resolved, see §10)
**Build order:** Step 7 of 10
**Depends on:** Spec 06 rev 1 (`inspections.submitted_at` as the checklist lock, the
`checklist_summary` shape first computed for the `INSPECTION_SUBMITTED` audit row, `scope_inspections`),
Spec 05 rev 2 (`ALLOWED_TRANSITIONS`, `transition()`'s evaluation order, instrument
`LOCATION_LOCK_STATUSES`), Spec 03 rev 2 (the `REJECTED` note-length rule, `transition()`'s scope →
edge → role → enabled → edge-rules → apply order)

## 1. Goal

Root `CLAUDE.md`'s lifecycle is `… Field inspection → Approve/Reject → Certificate + QR …`. Spec 06
built Field inspection and left the application's status at `INSPECTION` even after the checklist is
submitted — "the Approve/Reject decision, and what it does with this checklist, is step 7" (spec 06
§1). This step builds that decision: an in-scope officer reviews the submitted checklist's
PASS/FAIL/NA summary and either **approves** (status → `APPROVED`, ready for step 8's certificate) or
**rejects** (status → `REJECTED`, terminal — re-verification means a new application, per root
`CLAUDE.md`). Nothing about the checklist itself changes; it stays exactly as spec 06 left it, frozen
by `submitted_at`.

Demo story: continuing spec 06's demo, once `officer.dhn@lm.demo` (or another in-jurisdiction officer)
opens the seeded ABC Traders application after its inspection was submitted, `/applications/[id]` now
shows "Checklist: 7 passed, 0 failed, 0 n/a" and an **Approve** button. Approving moves the application
to `APPROVED` — the demo's next stop is step 8, where `CERT-2026-000123` gets issued.

**Out of scope:**
- Certificate PDF/QR generation (step 8). `APPROVED → CERTIFICATE_ISSUED` stays a disabled, system-only
  edge (`Edge(frozenset(), enabled=False)`) — it happens inside certificate creation, never via this
  step's `PATCH /applications/{id}/status`.
- Any UI for the certificate (step 8/9).
- Re-verification after `REJECTED`. Root `CLAUDE.md`: "REJECTED is terminal. Re-verification means a
  new application." No "resubmit" or "appeal" flow exists.
- A dedicated "pending decisions" queue. The existing `GET /applications?status=INSPECTION` (spec 05)
  already lists every application awaiting either checklist work or a decision; splitting "not yet
  submitted" from "awaiting decision" client-side is enough for the MVP (§6).
- Reassigning or re-running the checklist after rejection (there is no "undo" of a submitted checklist,
  spec 06 §11).

## 2. Access

- Role: `LM_OFFICER` (unchanged — `ALLOWED_TRANSITIONS` already keys both edges to
  `frozenset({Role.LM_OFFICER})`). Scope: `scope_applications`, unchanged — reaching an `INSPECTION`
  application at all already means the caller is an in-jurisdiction officer, same as every other status
  since `SUBMITTED`.
- **No new identity check.** Unlike spec 06 §3 (`inspections.assigned_officer_id` gates every action
  that touches the checklist's *contents*), Approve/Reject is deliberately open to **any** in-scope
  `LM_OFFICER`, not just the one who ran the inspection (§10 D1). This is safe precisely because the
  checklist is already frozen by `submitted_at` — a second officer deciding is reading immutable data,
  never editing it. `PATCH /inspections/{id}` and the evidence endpoints keep their existing
  assigned-officer lock untouched; only the decision itself is open.
- New rule, not an identity check: the checklist must actually be **submitted** first (§3).

## 3. Data and rules

No migration. `inspections.submitted_at` already exists (spec 06); no new columns, no new tables, no
new enum values.

- `ALLOWED_TRANSITIONS` (`app/services/applications.py`) flips the two edges spec 06 reserved:
  ```python
  (S.INSPECTION, S.APPROVED): Edge(frozenset({Role.LM_OFFICER}), enabled=True),  # step 7
  (S.INSPECTION, S.REJECTED): Edge(frozenset({Role.LM_OFFICER}), enabled=True),  # step 7
  ```
  (drop the `# step 7` comments once implemented).
- **New edge rule in `transition()`**, inserted at the same spot as spec 06's assigned-officer check
  (right after the existing `not edge.enabled` check, before the `REJECTED` note-length check so a
  premature Reject attempt gets the more specific message):
  ```python
  if (
      current == S.INSPECTION
      and target in (S.APPROVED, S.REJECTED)
      and application.inspection.submitted_at is None
  ):
      raise Conflict("The inspection checklist must be submitted before approving or rejecting")
  ```
- `REJECT_NOTE_MIN = 10` is reused **unchanged** — the existing check (`target == S.REJECTED and
  len(note) < REJECT_NOTE_MIN` → 422) already applies to any `REJECTED` target, so
  `INSPECTION → REJECTED` inherits it automatically. `APPROVED` has no note requirement (§10 D4); the
  existing `else: history_note = note` branch already handles an optional/`None` note correctly.
- **`allowed_actions()` gains the same gate**, so the UI never offers a button the backend would 409:
  ```python
  def allowed_actions(application: Application, user: User) -> list[ApplicationStatus]:
      actions = [
          to
          for (frm, to), edge in ALLOWED_TRANSITIONS.items()
          if frm == application.status and edge.enabled and user.role in edge.roles
      ]
      if application.status == S.INSPECTION and (
          application.inspection is None or application.inspection.submitted_at is None
      ):
          actions = [a for a in actions if a not in (S.APPROVED, S.REJECTED)]
      return actions
  ```
  `transition()`'s own check (above) stays as the real enforcement — `allowed_actions()` is a
  convenience for the frontend, not a substitute, same client-hint/server-enforcement pairing as
  Submit/`requirementsMet` (spec 03) and the checklist's `can_edit` (spec 06).
- **Instrument location lock is unchanged.** `core/instrument_lock.py`'s `LOCATION_LOCK_STATUSES =
  {SCHEDULED, INSPECTION, APPROVED}` already keeps the instrument's address locked through `APPROVED`
  — Approve does **not** unlock it (a certificate is about to reference that exact location in step 8).
  Reject already falls outside `LOCATION_LOCK_STATUSES`, so it already unlocks the instrument and frees
  it for a new application via `ux_applications_active_instrument`'s partial index. Nothing in
  `instrument_lock.py` changes in this step — called out here so it isn't "fixed" by mistake.
- **Audit:** reuse the existing generic `APPLICATION_STATUS_CHANGED` action (`transition()` already
  writes one for every status change) — no new audit action name. When `current == S.INSPECTION` and
  `target` is `APPROVED`/`REJECTED`, its `details` dict gains `checklist_summary` (same shape as
  `INSPECTION_SUBMITTED`'s), so the decision's audit trail carries the numbers the officer saw:
  ```python
  details = {"from": current.value, "to": target.value, "note": note}
  if current == S.INSPECTION and target in (S.APPROVED, S.REJECTED):
      details["checklist_summary"] = checklist_summary_counts(application.inspection.checklist_items)
  ```

## 4. API

No new routes. The existing endpoint gains behaviour:

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| `PATCH` | `/api/applications/{id}/status` `{"status": "APPROVED"}` | in-scope `LM_OFFICER`, checklist submitted | `{note?}` → `ApplicationDetail` |
| `PATCH` | `/api/applications/{id}/status` `{"status": "REJECTED"}` | in-scope `LM_OFFICER`, checklist submitted | `{note}` (≥10 chars) → `ApplicationDetail` |

`StatusChange` (`app/schemas/application.py`) needs no change — `note` is already `Notes | None`.

### Schema additions (`app/schemas/application.py`)
```python
class ChecklistSummary(BaseModel):
    passed: int
    failed: int
    na: int

class InspectionOut(BaseModel):
    id: uuid.UUID
    scheduled_date: date
    assigned_officer_name: str
    submitted_at: datetime | None
    checklist_summary: ChecklistSummary | None   # present once submitted, else null
```
Built from the already-loaded `a.inspection.checklist_items` relationship — pure data shaping, no extra
db call, the same way `assigned_officer_name` already reads a loaded relationship. The counting logic
(`Counter` over `.result`) moves into a small shared helper, `checklist_summary_counts(items) ->
dict[str, int]` in `app/core/inspection_templates.py` (pure, no db dependency — the natural home next to
`CHECKLIST_TEMPLATES`/`measurement_label`), reused by both this schema builder and
`app/services/inspections.py: submit()` (replacing its inline `Counter(...)` at line 146) so the exact
same PASS/FAIL/NA shape isn't computed two different ways in two layers.

### Behaviour rules
- Evaluation order is unchanged from spec 03 §3 (scope 404 → edge exists 409 → role 403 → enabled 409 →
  edge rules 409/422 → apply); the new submitted-checklist check and the existing note-length check are
  both "edge rules," evaluated in the order listed in §3.
- `application.status == INSPECTION and inspection.submitted_at is None` → attempting `APPROVED` or
  `REJECTED` → **409** `"The inspection checklist must be submitted before approving or rejecting"`.
- `REJECTED` with `note` missing or `< 10` chars → **422** (`field="note"`), unchanged message.
- `APPROVED` with or without `note` → succeeds; `note` (if given) is stored on the
  `ApplicationStatusHistory` row same as any other transition.
- On success: one `ApplicationStatusHistory` row (unchanged shape), one `APPLICATION_STATUS_CHANGED`
  audit row (now carrying `checklist_summary` for this pair, §3), `application.status` set, single
  transaction, existing row lock (`load(..., for_update=True)`) — no new lock, no second table touched.

## 5. Backend implementation
```
app/services/applications.py       ALLOWED_TRANSITIONS: flip both step-7 edges to enabled=True;
                                    transition(): submitted-checklist edge rule + checklist_summary
                                    in audit details; allowed_actions(): submitted-checklist gate;
                                    load()'s `detail=True` branch gains
                                    selectinload(Application.inspection).selectinload(Inspection.checklist_items)
app/core/inspection_templates.py   + checklist_summary_counts(items) -> dict[str, int]
app/services/inspections.py        submit() calls checklist_summary_counts() instead of its inline Counter
app/schemas/application.py         + ChecklistSummary; InspectionOut + submitted_at, checklist_summary
```
No new router, no new migration, no new audit action name.

## 6. Frontend implementation

| Route | Who | Content |
|---|---|---|
| `app/applications/[id]/page.tsx` (existing, extended) | in-scope `LM_OFFICER` | Approve button (new, optional-note confirm dialog) alongside the existing Reject button (unchanged — already generic to any `allowed_actions` entry named `REJECTED`); inspection section gains a checklist-summary line and a link to the frozen checklist |

- **Approve button:** rendered when `app.allowed_actions.includes("APPROVED")`, exactly like every
  other action button on this page. Opens a confirm dialog with an optional `Textarea` (no minimum
  length, unlike Reject's) — mirrors the existing `confirmSubmit`/`rejectOpen` dialog pattern
  (`approveOpen`/`approveNote` state, `changeStatus("APPROVED", { note: approveNote || undefined })`).
- **Reject button:** no code change needed. It already renders whenever `allowed_actions` includes
  `REJECTED` and already posts through the same `changeStatus("REJECTED", { note: rejectNote })` used
  for the `DOCUMENT_REVIEW → REJECTED` case — the backend's new gate (§3) means it simply won't appear
  until the checklist is submitted, no frontend change required.
- **Inspection section** (the existing `app.inspection` block showing "Scheduled for … / Assigned to
  …"): once `app.inspection.submitted_at` is non-null, add a line — "Checklist: {passed} passed,
  {failed} failed, {na} n/a" — and change the existing "Continue inspection" button's label to "View
  inspection" (same link to `/inspections/{id}`, already read-only there once submitted per spec 06 —
  no change needed on that page).
- `lib/types.ts`: `InspectionOut` gains `submitted_at: string | null` and
  `checklist_summary: { passed: number; failed: number; na: number } | null`.
- `frontend/CLAUDE.md`: the Key screens table's `/applications/[id]` row gains "Approve / Reject (once
  the inspection is submitted)"; the "Officer field inspection" note ("Approve/Reject is a separate
  step-7 screen…") is replaced with a description of what actually renders on `/applications/[id]`.

## 7. Tests (backend)

Extend `tests/test_applications_transitions.py`:
- Success: a submitted inspection, `INSPECTION → APPROVED` by an in-scope `LM_OFFICER` who is **not**
  the assigned officer succeeds (proves §10 D1) — status becomes `APPROVED`, one history row, one audit
  row with `details.checklist_summary` matching the checklist's actual PASS/FAIL/NA counts, instrument
  stays location-locked (`GET /instruments/{id}` reflects it).
- Success: `INSPECTION → REJECTED` by an in-scope officer with a ≥10-char note succeeds; instrument
  unlocks and can accept a new application afterward.
- Not yet submitted (`submitted_at is None`) → attempting either target → **409** with the exact new
  message; `allowed_actions` for that application excludes both `APPROVED` and `REJECTED`.
- `REJECTED` with `note` `None` or `< 10` chars → still **422** (unchanged behavior, regression check).
- `APPROVED` with no `note` at all → succeeds, `ApplicationStatusHistory.note` is `null`.
- Wrong role (BUSINESS/admins/GATC) → 403; out-of-jurisdiction officer → 404. Same parametrization
  style as spec 05 §11/spec 06 §9.
- Update the test spec 06's verification record repointed: `test_applications_transitions.py`'s
  `INSPECTION → APPROVED` "not yet enabled" case now expects it **enabled** (this spec is what enables
  it) — flip that assertion rather than deleting the test.

Add a unit test for `checklist_summary_counts()` (or cover it indirectly through the submit/approve
tests above) confirming it produces the same dict shape `submit()` used to build inline.

## 8. Demo seed

No seed changes. The seeded `WEIGHING_SCALE` application reaches a submitted `INSPECTION` state live
via spec 06's demo; this step's demo drives Approve live from there, the same approach 05/06 took.

## 9. Deferred and recorded for later steps

- **Step 8:** certificate PDF/QR generation, `APPROVED → CERTIFICATE_ISSUED` (system-only, inside
  certificate creation), `certificate_number` (`LM-CERT-{year}-{seq:06d}`), `certificates` table
  (`valid_from`, `valid_until`, `status`, `pdf_path`, `qr_token`, `data_hash`).
- **Step 9:** public QR verification page consuming the certificate this step's Approve leads to.
- **Step 10:** expiry dashboard + daily job, reading `certificates.valid_until`.
- A "pending decisions" queue distinct from "in-progress inspections" (both currently live under
  `status=INSPECTION`; splitting them needs a `submitted_at IS NOT NULL` filter param if ever needed).
- Any appeal/resubmission path after `REJECTED` — currently a dead end by design (new application only).

## 10. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Who may Approve/Reject at `INSPECTION`? | **Any in-scope `LM_OFFICER`**, not assigned-officer-locked — a deliberate contrast with spec 06 D1 (starting/working the checklist stays assigned-officer-only). Safe because the checklist is frozen (`submitted_at`) before a decision is ever possible (§3's new gate), so a second officer only ever reads immutable data. |
| D2 | Must the checklist be submitted before deciding? | **Yes.** New 409 in `transition()` plus a matching filter in `allowed_actions()`, so the button and the enforcement agree. Without this, an officer could approve an instrument that was never actually checked. |
| D3 | How does the officer see the checklist before deciding? | **Inline summary** (`InspectionOut.checklist_summary`) on `/applications/[id]` **+ a link** to the existing read-only `/inspections/[id]` for full item-by-item detail — avoids duplicating the whole checklist UI on the application page while still giving a fast at-a-glance read. |
| D4 | Does Approve require a note? | **No — optional.** Consistent with every other non-`REJECTED` transition in the app (Start review, Schedule, Start inspection all take no note). `REJECTED` keeps its existing ≥10-char requirement unchanged. |
| D5 | Gate in `transition()` only, or also in `allowed_actions()`? | **Both.** `transition()` is the real enforcement (a direct API call must still be rejected); `allowed_actions()` mirrors it so the UI never shows a button that would immediately 409 — the same client-hint/server-enforcement pairing already used for Submit/`requirementsMet` (spec 03) and the checklist's `can_edit` (spec 06). |
| D6 | New audit action for Approve/Reject? | **No — reuse `APPLICATION_STATUS_CHANGED`**, the existing generic transition audit action, extended with `checklist_summary` in its `details` for this pair only. A dedicated `APPLICATION_APPROVED`/`APPLICATION_REJECTED` action was considered but rejected: every other transition (including the existing `DOCUMENT_REVIEW → REJECTED`) already uses the generic action, and splitting only this pair would be inconsistent. |

## 11. Acceptance criteria

- [x] `INSPECTION → APPROVED` and `INSPECTION → REJECTED` are enabled edges, reachable by any in-scope
  `LM_OFFICER` once (and only once) the inspection's checklist is submitted.
- [x] Attempting either before submission → 409 with the documented message; `allowed_actions` excludes
  both until then.
- [x] `REJECTED` still requires a ≥10-char `note` (422 otherwise); `APPROVED` works with no note.
- [x] The instrument stays location-locked after `APPROVED`; it unlocks and becomes available for a new
  application after `REJECTED`.
- [x] `/applications/[id]` shows the checklist's PASS/FAIL/NA summary once submitted, with Approve and
  Reject buttons appearing only then, and a working link into the read-only `/inspections/[id]`.
- [x] `ruff`, `eslint`, `tsc` and the build are clean; backend test suite green including the new and
  updated transition tests.
- [x] `backend/CLAUDE.md` updated: Application status flow section gains an "Approve/Reject (step 7)"
  subsection (mirroring the existing Scheduling/Field inspection ones); Data model section notes
  `InspectionOut`'s new fields if relevant. `frontend/CLAUDE.md` updated: Key screens table and the
  "Officer field inspection" note. Root `CLAUDE.md` step 7 marked ✅ linking to this spec.

## 12. Verification record

**One correction to §3/§4 found during implementation:** they assumed `a.inspection.checklist_items`
is a loadable ORM relationship. It isn't — `Inspection` (`app/models/inspection.py`) only declares an
`assigned_officer` relationship; checklist rows are always fetched via an explicit query
(`services/inspections.py: _checklist_items()`), never a relationship attribute, and `core/` modules
carry no ORM imports by convention. Implemented instead: a pure `checklist_summary_counts(results:
Iterable[str | None])` helper in `core/inspection_templates.py`, and a new public
`inspections_service.checklist_summary(db, inspection_id)` (reusing `_checklist_items()`) that
`services/applications.py` and the applications router call explicitly — one extra query, only issued
when there's a submitted inspection to summarize. No other design change from the spec.

Backend (`pytest`, local `lm_dev`/`lm_test`): full suite green — 368 tests, including 7 new tests in
`tests/test_applications_transitions.py` (approve by a non-assigned in-scope officer; approve with no
note; reject and instrument-unlock; the submitted-checklist 409 gate for both targets, and that
`allowed_actions` excludes both until then; reject's note-length rule still applies from `INSPECTION`;
role/scope 403/404 coverage) plus `test_evaluation_order`'s existing step-7 assertion updated to expect
the new gate's message instead of the now-stale "not yet enabled" one. `ruff check`/`ruff format --check`
clean.

Frontend (`tsc --noEmit`, `eslint`, `next build`): clean, no new suppressions needed.

Manual, in Chrome against local dev servers (`lm_dev`, `STORAGE_BACKEND=memory`): logged in as
`officer.dhn@lm.demo`, opened the live ABC Traders demo application (`APP-2026-000002`,
`LM-JH-DHN-000002`) whose inspection was already submitted (7/7 checklist items passed from an earlier
manual session) — `/applications/{id}` showed "Checklist: 7 passed, 0 failed, 0 n/a" and **Approve**/
**Reject** buttons. Clicked **Approve**, entered a note, confirmed — status badge became "Approved",
the timeline recorded the note, and the instrument's detail page still showed "Application in progress:
APP-2026-000002" (location fields stay locked through `APPROVED`, as designed — the instrument's
`active_application` only clears at a terminal status).
