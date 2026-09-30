# Spec 05 — Officer dashboard and scheduling (rev 2)

**Status:** Done. Implemented and verified (§13); all decisions resolved (§15)
**Build order:** Step 5 of 10
**Depends on:** Spec 04 rev 2 (`GET /applications/stats`, `lib/use-async.ts`, the "Needs your attention" pattern), Spec 03 rev 2 (`ALLOWED_TRANSITIONS`, `scope_applications`, instrument `LOCKED_FIELDS`, §15's deferred location lock), Spec 02 rev 2 (`InstrumentOut`)

## 1. Goal
Root `CLAUDE.md`'s lifecycle is `Register → Apply → Document review → Schedule → Field inspection → …`, and Spec 03 reserved `DOCUMENT_REVIEW → SCHEDULED` ("needs date + assigned officer") for this step. "Officer dashboard" is therefore two things done together:

1. A working dashboard for **LM_OFFICER**: jurisdiction-scoped status chips (reusing `GET /applications/stats`), a review queue, and upcoming inspections. It replaces the current placeholder.
2. The **Schedule** action: `DOCUMENT_REVIEW → SCHEDULED`, which needs a date, creates the inspection record, and locks the instrument's address and coordinates. Because there is no way back from SCHEDULED yet, this step also ships a minimal **Reschedule** so a mistyped date is fixable.

Demo story: the Dhanbad officer opens the dashboard, sees "Submitted, awaiting review", starts review, then schedules an inspection for a date. The dashboard's "Upcoming inspections" shows it, and ABC Traders sees "Scheduled for …" on their application.

**Out of scope:**
- `SCHEDULED → INSPECTION`, the checklist and measurements (step 6); approve/reject after inspection (step 7).
- Assigning to a **different** officer, or to GATC (D2).
- Cancelling a scheduled inspection (D7).
- The Admin dashboard branch (`DISTRICT_ADMIN` / `STATE_ADMIN` / `SUPER_ADMIN`): unchanged placeholder.
- Email/SMS notification of the business (Good-to-Have).

## 2. What rev 1 got wrong (why this rev exists)
| # | Problem in rev 1 | Consequence | Fix in rev 2 |
|---|---|---|---|
| P1 | "Today or later" was validated in UTC | For users in India, the UTC date lags by up to 5 h 30 min: yesterday's IST date is accepted around midnight–05:30 IST | Project timezone setting `APP_TIMEZONE` (default `Asia/Kolkata`, ASSUMPTION) used by backend **and** frontend (§4); plus a max horizon (typo guard) |
| P2 | Scheduling locked only the application row; the instrument-PATCH lock check reads the application status | A business could change the address in the same instant the officer schedules; the address would change *after* SCHEDULED | The scheduling transition also locks the instrument row; lock order documented (§5) |
| P3 | Schedule was irreversible (no reschedule, no cancel), had no confirmation ("not destructive"), and locks the address | A typo in the date is permanent and the address is frozen | Confirmation dialog stating the consequence, **and** a minimal `PATCH /applications/{id}/inspection` reschedule (§6, D7) |
| P4 | "Upcoming inspections" sorted by application `created_at`, not by date | The list was not "upcoming" at all | `sort=scheduled_asc` on `GET /applications` (§6, D5) |
| P5 | Lock lifecycle text said the lock lifts "once a new application starts after `CERTIFICATE_ISSUED`" | Wrong: the lock follows the **active** application, and both terminal states lift it | Corrected rule, a dedicated error message, and `locked_fields` computed by the backend so the UI never duplicates the rule (§7) |
| P6 | The test "edge used to 409, now succeeds" is not a real test; and Spec 03's existing "not yet enabled → 409" test almost certainly used *this* edge | That existing test **breaks** when the edge is enabled | Repoint it to `SCHEDULED → INSPECTION` (still disabled); add a proper success test (§11) |
| P7 | `scheduled_date` was accepted on any transition | Extra data silently ignored | Rejected (422) unless the target is SCHEDULED |
| P8 | The assigned officer's meaning for step 6 was undefined | Step 6 could not tell who may start the inspection | Recorded as a Step 6 requirement (§14) |

## 3. Access
No new scoping helper. An inspection is reached **only through its application**, already scoped by `scope_applications` (the same reasoning as `scope_documents`). The inspection date and assigned officer's name are visible to anyone who can already read that application: the owning business and jurisdiction officials. Showing the officer's name to the business is intended (a field visit).

`ALLOWED_TRANSITIONS` already reserves the edge:
```python
(S.DOCUMENT_REVIEW, S.SCHEDULED): Edge(frozenset({Role.LM_OFFICER}), enabled=False),  # step 5
```
This step flips `enabled=True`. No role change: DISTRICT_ADMIN, STATE_ADMIN, SUPER_ADMIN and GATC still get 403 on any transition or reschedule.

## 4. Time and dates
- New setting `APP_TIMEZONE: str = "Asia/Kolkata"` (**ASSUMPTION:** deployment serves India; change it if not) and `SCHEDULING_MAX_DAYS_AHEAD: int = 180` (ASSUMPTION).
- `today()` helper in `app/core/clock.py`: the current date **in `APP_TIMEZONE`**, built on the existing `_now()` so tests can freeze time. Timestamps in the database stay UTC.
- Valid `scheduled_date`: `today() <= date <= today() + MAX_DAYS_AHEAD`. Otherwise `Unprocessable(field="scheduled_date")`. No holiday or business-calendar logic (ASSUMPTION).
- `GET /applications/meta` gains `scheduling: { timezone, max_days_ahead }`. The frontend computes "today" in that timezone (e.g. `new Date().toLocaleDateString("en-CA", { timeZone })`) for the date input's `min`/`max`. It never uses the browser's local date. The server is still the authority.
- Application numbers keep the UTC year (Spec 03); unrelated to this.

## 5. Data model (migration `0004_inspections`)

### `inspections`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `application_id` | UUID FK → applications, `ON DELETE CASCADE`, **unique** | one inspection per application in MVP. Only DRAFT applications can be deleted, so a cascade never removes a real inspection |
| `scheduled_date` | `date`, not null | date only, no time slot (D3) |
| `assigned_officer_id` | UUID FK → users, `ON DELETE RESTRICT`, not null | always the scheduling officer in step 5 (D2). Reschedule does **not** change it |
| `created_at`, `updated_at` | timestamptz | `Timestamps` mixin |

- Index `(assigned_officer_id, scheduled_date)` now, for step 6's "My inspections".
- No `status` column: the application's own `status` is the single source of truth (D6). Step 6 adds checklist and measurement data to this row or a child table.
- The migration creates the table and index only (no enum, no sequence). `downgrade` drops both.

### Lock order (write this into `backend/CLAUDE.md`)
When one transaction needs several row locks, take them in this order: **application, then instrument**. Nothing may lock the instrument and then wait for an application lock. (Today only the scheduling transition takes both.)

## 6. Rules and API

### Schedule: `PATCH /applications/{id}/status` with `{"status": "SCHEDULED", "scheduled_date": "2026-10-15"}`
`StatusChange` gains `scheduled_date: date | None = None`. In `transition()`, alongside the REJECTED-note check:
- Target `SCHEDULED` **requires** `scheduled_date`, valid per §4. Missing or invalid → 422. `scheduled_date` sent with any other target → 422.
- Evaluation order is unchanged from Spec 03 §3 (scope → edge exists → role → enabled → edge rules → apply). Scope 404 also means an officer from another district can't schedule.
- On success, in the **same transaction**: lock the application row (already held), then **lock the instrument row `FOR UPDATE`**, change the status, create the `Inspection` (`assigned_officer_id = caller`), write the `application_status_history` row (note: `"Inspection scheduled for {date}"`, so the business's timeline shows it), and write **two** audit rows: `APPLICATION_STATUS_CHANGED` and `INSPECTION_SCHEDULED` (`application_id`, `scheduled_date`).
- Two officers scheduling at once: one succeeds; the other gets 409 (the edge `SCHEDULED → SCHEDULED` isn't in the map).

### Reschedule: `PATCH /applications/{id}/inspection` with `{"scheduled_date": "2026-10-20"}`
| | |
|---|---|
| Allowed | LM_OFFICER in jurisdiction (others 403; out of scope 404) |
| Precondition | application status is **SCHEDULED**, else 409 `"Only a scheduled inspection can be rescheduled"` |
| Validation | same as scheduling (§4); `extra="forbid"` |
| Behaviour | lock the application row; same date as stored → 200, no audit row, `updated_at` unchanged; otherwise update `scheduled_date`, write `INSPECTION_RESCHEDULED` (`details.changes = {"scheduled_date": [old, new]}`) |
| Response | `ApplicationDetail` |

The assigned officer is unchanged by a reschedule. Register `/applications/{id}/inspection` alongside the other `{id}` routes (no conflict with `/applications/meta` or `/stats`). `POST /api/inspections` stays reserved for step 6.

### Read changes
- `InspectionOut`: `scheduled_date: date`, `assigned_officer_name: str`.
- `ApplicationDetail` gains `inspection: InspectionOut | None` and `can_reschedule: bool` (computed for the caller: LM_OFFICER in scope and status SCHEDULED).
- `ApplicationOut` gains `scheduled_date: date | None`, read with **one LEFT JOIN** (`inspections.application_id` is unique, so rows don't multiply), never a query per row.
- `GET /applications` gains `sort: Literal["created_desc", "scheduled_asc"] = "created_desc"` (invalid → 422). `scheduled_asc` orders by `inspections.scheduled_date ASC NULLS LAST, applications.id`. Paging and `total` are unaffected.
- `GET /applications/stats`: unchanged. `SCHEDULED` simply becomes non-zero.

## 7. Instrument location lock (activates Spec 03 §15)
Replace the inline set logic in `services/instruments.py` with one pure function used by both `update()` and `InstrumentOut`:

```python
IDENTITY_LOCKED = frozenset({"manufacturer", "model", "serial_number", "capacity",
                             "capacity_unit", "accuracy_class", "state_code", "district_code"})
LOCATION_FIELDS = frozenset({"address", "latitude", "longitude"})
LOCATION_LOCK_STATUSES = frozenset({S.SCHEDULED, S.INSPECTION, S.APPROVED})

def locked_fields(active_status: S | None) -> frozenset[str]:
    if active_status is None: return frozenset()
    locked = IDENTITY_LOCKED
    if active_status in LOCATION_LOCK_STATUSES:
        locked = locked | LOCATION_FIELDS
    return locked
```
- "Active" means the application is **non-terminal** (Spec 03). Therefore the location lock lifts when the application reaches **REJECTED or CERTIFICATE_ISSUED**. DRAFT, SUBMITTED and DOCUMENT_REVIEW leave address/coordinates editable.
- `update()` returns 409 with a specific message when a location field is blocked: `"An inspection is scheduled for this instrument; its address and coordinates can't be changed until the application is completed or rejected."` Identity fields keep the Spec 03 message.
- `InstrumentOut` gains `locked_fields: list[str]` (sorted), produced by the same function. The instrument edit form disables exactly those fields and hard-codes none of the rule.
- The instrument row is locked `FOR UPDATE` in PATCH (Spec 03) and in the scheduling transition (above), so "address changed after SCHEDULED" cannot happen.
- **ASSUMPTION (unresolved):** after `CERTIFICATE_ISSUED` the address becomes editable again; whether a moved, certified instrument must be flagged for re-verification is a domain question for step 8+ (§14).

## 8. Officer dashboard UI contract
Same shape as Spec 04's business dashboard: independent sections via `lib/use-async.ts`, each with its own loading / error + **Retry** / empty state, fetched on mount and on tab focus. Replaces the `LM_OFFICER` branch of `RoleCard`.

```
┌ Welcome, {name} (LM_OFFICER) ─────────────────────────────┐
│ Jurisdiction: JH / DHN                                      │
│ 12 registered instruments            → /instruments         │
│ 7 applications                       → /applications        │
│ [Submitted 2] [Document review 1] [Scheduled 1] [...]        │  chips, lifecycle order, count > 0
│                                                              │
│ Needs your attention                                         │
│  • APP-…042 · XYZ12345 · Start document review               │  status = SUBMITTED
│  • APP-…031 · ABC9000  · Schedule inspection                 │  status = DOCUMENT_REVIEW
│  + N more →                                                  │  when a rule's total > 5
│                                                              │
│ Upcoming inspections                                         │
│  • 15 Oct 2026 · APP-…031 · ABC9000                          │  SCHEDULED, nearest date first, 5
│                                                              │
│ Recent                                                       │
│  APP-… · LM-JH-DHN-… · [badge] · date                        │  5 newest, any status
└──────────────────────────────────────────────────────────────┘
```
- **Instruments tile, applications total, chips:** the same components as Spec 04 (`GET /instruments?page_size=1` → `total`, `GET /applications/stats`). Counts always come from `total` / `by_status`, never `items.length`. Officer counts exclude DRAFTs (Spec 04 already guarantees this).
- **Needs your attention:** Spec 04's list component generalized to accept a rules array `{status, hint}`. One call per rule (`GET /applications?status=X&page_size=5`), each with its own `useAsync` and Retry. Each row links to `/applications/{id}`; "+ N more →" links to `/applications?status=X` (the list page already honours `?status=`, Spec 04).

  | Condition | Hint | 
  |---|---|
  | SUBMITTED | Start document review |
  | DOCUMENT_REVIEW | Schedule inspection |
- **Upcoming inspections:** `GET /applications?status=SCHEDULED&sort=scheduled_asc&page_size=5`. Shows `scheduled_date` per row. Past-dated inspections sort first (nothing can complete them until step 6); this is honest, and labels such as "Overdue" are deferred.
- **Recent:** `GET /applications?page_size=5`.
- **Empty states:** a section with nothing to show is hidden (needs-attention rows, upcoming); if the jurisdiction has no applications at all, show "No applications in your district yet".
- **Business side (small):** the business dashboard's Recent rows and the applications list show `Scheduled: {date}` when `scheduled_date` is present, so the business sees the date without opening the application.
- Admin / GATC branches: unchanged.

## 9. Application detail page
`app/applications/[id]/page.tsx`, officer view:
- When `allowed_actions` includes `SCHEDULED`: a **date input** (`min` = today, `max` = today + `max_days_ahead`, both in the meta timezone) and a **Schedule inspection** button. The button opens a **confirmation dialog**: *"Schedule the inspection for {date}? The instrument's address and coordinates will be locked until the application is completed or rejected."* Confirm sends `{status: "SCHEDULED", scheduled_date}`.
- When `can_reschedule`: the same date input with a **Change date** button (no dialog; not destructive) calling `PATCH /applications/{id}/inspection`.
- 422 on `scheduled_date` shows inline on the input.
- Once scheduled, the owning business **and** jurisdiction officials see `Scheduled for 15 Oct 2026` with the assigned officer's name. The status timeline shows the "Inspection scheduled for …" history note.
- The instrument edit form disables the fields listed in `InstrumentOut.locked_fields` and shows the lock message next to them.

## 10. Backend and frontend implementation
```
app/core/clock.py                   today() in APP_TIMEZONE (over _now())
app/core/config.py                  + APP_TIMEZONE, SCHEDULING_MAX_DAYS_AHEAD
app/models/inspection.py            Inspection (UUIDPk, Timestamps)
app/schemas/application.py          + InspectionOut, scheduling in meta; new fields on ApplicationOut/Detail; StatusChange.scheduled_date; InspectionReschedule
app/services/applications.py        enable SCHEDULED edge; scheduling branch (instrument lock, inspection row, history note, 2 audits); reschedule(); sort
app/services/instruments.py         locked_fields() replaces inline sets; specific location-lock message; locked_fields on InstrumentOut
app/routers/applications.py         PATCH /applications/{id}/inspection; sort query param
alembic/versions/0004_inspections.py

frontend:
app/dashboard/page.tsx              LM_OFFICER branch (sections above); business Recent shows scheduled date
components/applications/…           generalized needs-attention list (rules array), if not already shared
app/applications/[id]/page.tsx      Schedule (dialog) and Change date
app/applications/page.tsx           show scheduled date column/hint
instrument edit form                disable fields from locked_fields
lib/types.ts, lib/api.ts            new fields, sort param, reschedule call
```

## 11. Tests (backend)
Use the clock helper so time can be frozen.

**Update existing tests first**
- Spec 03's "edge exists but not yet enabled → 409 `not available yet`" test must use `SCHEDULED → INSPECTION` (still disabled), not `DOCUMENT_REVIEW → SCHEDULED`.

**Scheduling** (`tests/test_applications_transitions.py`)
- Success: the reviewing-jurisdiction LM_OFFICER schedules a DOCUMENT_REVIEW application with a valid date → status SCHEDULED, exactly one `inspections` row with `assigned_officer_id = caller`.
- Exactly one `APPLICATION_STATUS_CHANGED`, one `INSPECTION_SCHEDULED` and one history row (with the date in `note`).
- Missing `scheduled_date` → 422; `scheduled_date` on another target → 422.
- **Timezone/date boundaries** (freeze time): at `2026-10-14 20:00 UTC` (= 01:30 IST on 15 Oct), 14 Oct → 422, 15 Oct → 200. `today + 180` → 200; `today + 181` → 422; far-future typo (year 2062) → 422.
- Role/scope: BUSINESS → 403; DISTRICT_ADMIN / STATE_ADMIN / SUPER_ADMIN / GATC → 403; an officer from RNC on a DHN application → 404.
- Two concurrent schedule calls → exactly one succeeds, one inspection row.
- **Race with instrument PATCH:** run an address PATCH and the scheduling transition concurrently: either the PATCH commits first (200) and scheduling then succeeds, or scheduling commits first and the PATCH gets 409. Never a committed address change after the status became SCHEDULED.

**Reschedule**
- Success updates the date, keeps `assigned_officer_id`, writes one `INSPECTION_RESCHEDULED` row with `[old, new]`.
- Same date → 200, no audit row. Invalid date → 422. Status not SCHEDULED → 409. Business or admin roles → 403; out-of-scope officer → 404.
- `can_reschedule` is true only for an in-scope officer while SCHEDULED.

**Reads**
- `GET /applications/{id}`: both the owning business and the jurisdiction officer see `inspection`; another org's business → 404.
- `GET /applications/stats` and `?status=SCHEDULED` reflect the new status immediately.
- `sort=scheduled_asc`: ascending by date, applications without an inspection last, stable by id; `sort=bogus` → 422; default order unchanged; `total` correct; no per-row queries (assert query count on a 20-row page).

**Instrument lock** (`tests/test_instruments_lock.py`)
- `locked_fields()` parametrized over `None` and all 8 statuses: identity fields for DRAFT/SUBMITTED/DOCUMENT_REVIEW; identity + location for SCHEDULED/INSPECTION/APPROVED; nothing for REJECTED/CERTIFICATE_ISSUED (terminal, so treated as no active application).
- PATCH `address` / `latitude` / `longitude` → 200 in DRAFT/SUBMITTED/DOCUMENT_REVIEW; → 409 with the location message in SCHEDULED and APPROVED; → 200 again after REJECTED.
- `InstrumentOut.locked_fields` matches the function for the instrument's active application.

## 12. Acceptance criteria
- [x] `0004_inspections` round-trips locally (`upgrade`, `downgrade -1`, `upgrade`) and applies to Supabase.
- [x] The updated Spec 03 "not yet enabled" test passes; all earlier specs' tests still pass.
- [x] As `officer.dhn@lm.demo`: the dashboard shows jurisdiction instruments and applications, status chips, a "Start document review" row for a SUBMITTED application, and a "Schedule inspection" row for a DOCUMENT_REVIEW one.
- [x] Scheduling shows the confirmation dialog, moves the application to SCHEDULED, appears in "Upcoming inspections" (nearest first), and shows "Scheduled for …" to the officer and to `owner@abctraders.demo`.
- [x] Change date works while SCHEDULED and updates the dashboard order.
- [x] Missing, past or too-far dates show an inline error; the date input's `min`/`max` follow the meta timezone (check by setting the machine clock near midnight or by test).
- [x] The instrument's address/coordinates are uneditable (fields disabled, 409 on direct PATCH) while SCHEDULED, and editable again after REJECTED.
- [x] The business Recent rows show the scheduled date.
- [x] `backend/CLAUDE.md` updated: `inspections` table, `APP_TIMEZONE` and the `today()` rule, the lock order, new audit actions, `scheduled_date`, the reschedule endpoint, `sort`, `locked_fields`. `frontend/CLAUDE.md` updated: the officer dashboard, the Schedule and Change date actions, and the rule "use `locked_fields` from the API, don't re-derive locks".
- [x] `ruff`, `eslint`, `tsc` and the build are clean; root `CLAUDE.md` step 5 marked ✅ linking to this spec.

Seed: no changes. The demo drives the seeded Other Traders application and the live ABC application through Start review and Schedule. To repeat the demo, re-seed.

## 13. Verification record

Backend (`pytest`, local `lm_test`): full suite green — `tests/test_scheduling.py` (new, 20 tests:
success, exactly-one-of-each-row, missing/rejected `scheduled_date`, frozen-clock date boundaries
via `monkeypatch.setattr(clock, "now_utc", ...)`, role/scope 403/404, concurrent-schedule race
(one wins), a real concurrent schedule-vs-instrument-PATCH race, reschedule success/no-op/invalid/
wrong-status/role/scope, `can_reschedule`, inspection visibility + org isolation, stats/status-filter
consistency, `sort=scheduled_asc` ordering with nulls-last, invalid `sort` → 422, and a query-count
assertion via a `before_cursor_execute` event hook proving the list endpoint issues at most 2
`applications` queries regardless of page size) plus `tests/test_instruments_lock.py` extensions
(`locked_fields()` parametrized over all 8 statuses + `None`, PATCH behavior through
SCHEDULED/APPROVED/REJECTED, `InstrumentOut.locked_fields`). 327 tests pass; `ruff check` and
`ruff format --check` clean.

A real bug was found and fixed during implementation, not anticipated by this spec: the scheduling
transition originally reused `instruments_service.get(..., for_update=True)` to lock the instrument
row. That function's query `joinedload`s `Instrument.active_application` — the very `Application` row
just mutated in the same transaction — and `for_update`'s `populate_existing=True` silently
re-hydrated the just-set, not-yet-committed `application.status` back to its stale DB value,
reverting the whole transition in memory (it still committed correctly to the DB on the *next* call,
masking the bug in a naive test). Fixed by replacing it with a bare `SELECT ... FOR UPDATE` that
locks without eager-loading anything. Documented in `backend/CLAUDE.md`'s new Scheduling section as a
standing warning for future transitions that need a second lock.

Frontend (`tsc --noEmit`, `eslint`, `next build`): clean.

Manual, in Chrome against the running dev servers:
- As `officer.dhn@lm.demo`: dashboard showed "Schedule inspection" for the seeded DOCUMENT_REVIEW
  application; the Schedule dialog's date input defaulted to today; confirming moved it to SCHEDULED
  and showed "Scheduled for …" / "Assigned to Dhanbad LM Officer" with a "Change date" control.
- Typing a date via real keyboard input (not synthetic DOM events — this project's `Input` wraps
  `@base-ui/react/input`, which doesn't respond to a raw `dispatchEvent("input")`) into the date field
  and saving with a past-relative date correctly surfaced the backend's inline 422
  ("scheduled_date must be between …"); a valid future date succeeded and updated the header.
- Logged in as `owner@othertraders.demo`: the instrument edit form showed the location-lock notice and
  disabled every identity **and** location field.
- The business dashboard's Recent row showed "Scheduled: 05/10/2026" next to the status badge.
- Back as the officer: "Upcoming inspections" showed the rescheduled date, status chips showed
  "1 Scheduled" / "1 Rejected", and "Needs your attention" was correctly empty (nothing left to act on).

## 14. Deferred and recorded for later steps
- **Step 6:** decide who may take `SCHEDULED → INSPECTION`: only `assigned_officer_id`, or any officer in the jurisdiction. Recommendation: assigned officer only, with an admin/other-officer override. Also add checklist and measurements, `POST /api/inspections/{id}/submit`, and a "My inspections" list using the `(assigned_officer_id, scheduled_date)` index.
- Cancelling a scheduled inspection; reassigning to another LM_OFFICER or to GATC; a time slot and calendar export; "Overdue"/"Today" labels on the dashboard.
- Step 8+: whether a change to a certified instrument's address must flag it for re-verification.
- Email/SMS to the business when a date is set.

## 15. Decisions (resolved)
| # | Decision | Resolution |
|---|---|---|
| D1 | `inspections` table now, or columns on `applications`? | **New minimal table**; step 6 extends it |
| D2 | Who can be the assigned officer? | **Self only.** `assigned_officer_id` is a real column, so reassigning later is a service change, not a migration |
| D3 | Date only, or date + time slot? | **Date only** (ASSUMPTION) |
| D4 | Confirmation before scheduling? | **Yes** (revised): it locks the address, and only Change date can undo the date |
| D5 | Upcoming inspections order | **By scheduled date** via `sort=scheduled_asc` (revised: the LEFT JOIN already exists, so the cost is small) |
| D6 | `inspections.status` column | **No**; the application's status stays the single source of truth |
| D7 | Reschedule in this step? | **Yes, minimal** (`PATCH /applications/{id}/inspection`, SCHEDULED only). Cancel stays deferred |
| D8 | Timezone for "today" | **`APP_TIMEZONE`, default `Asia/Kolkata`** (ASSUMPTION), used by the backend and the frontend |
| D9 | Max scheduling horizon | **180 days** (ASSUMPTION), a typo guard |
| D10 | Where the lock rule lives | **Backend only** (`locked_fields()` + `InstrumentOut.locked_fields`); the frontend disables what it is told |