# Spec 17 — Super Admin page (rev 2)

**Status:** Done. Implemented and verified (§11). Scope deliberately cut down from the source
brief (§2); §7's Decisions (D1–D6) were accepted as written, plus three additional calls made
with the user before implementation (§7 "rev 2 additions" below).
**Build order:** Step 17 (post-MVP addition, on top of steps 1–16)
**Depends on:** Spec 01 (`Role`, RBAC, `ROLE_RANK`), Spec 10 (`ADMIN_ROLES`, `GET /admin/certificates/*`,
expiry buckets), Spec 15 (`scope_organizations`, the GATC directory shape)
**Source input:** a pasted "Super Admin — Frontend Specification" brief (18 sections: dashboard,
application/instrument/certificate/expiry/enforcement management, national analytics, reports,
jurisdiction management, user & role management, audit logs, notification center, sidebar). That
brief is the starting point for this spec, not its contents verbatim — §2 explains why.

## 1. Goal

Root `CLAUDE.md`'s role table already says what a Super Admin does: **"stats, users, audit
logs."** This spec turns that one-line scope into a real page, reusing the data this system
already has (applications, instruments, certificates, organizations, audit logs, users) instead of
inventing a parallel reporting system.

Demo story: the Super Admin logs in, sees national totals (instruments, applications by status,
certificates by status), opens the applications/instruments/certificates lists unfiltered by
jurisdiction (every other role is jurisdiction- or org-scoped; Super Admin is the one role that
sees everything, per `scope_applications`/`scope_instruments`/`scope_organizations`), can create or
deactivate official accounts, and can look up what happened and who did it in the audit log.

## 2. Why this spec is narrower than the pasted brief

The brief describes a large, mature govtech back office: an enforcement/violations module, a
national map, a generic multi-format report generator, an in-app notification center, and a
dynamic state/district/jurisdiction editor. None of that exists in this codebase today, and most
of it conflicts with decisions this project has already made on the record:

| Brief asks for | Why it doesn't fit as asked | What this spec does instead |
|---|---|---|
| India map, click a state for stats | Root `CLAUDE.md`'s **Deferred** list explicitly names "Leaflet maps" — not to be added without asking | A plain state-wise **table** (sortable, same numbers a map would show) — §6.4 |
| Enforcement Management (cases, violations, responsible authority) | No `enforcement`/`violation` concept exists anywhere in the data model, specs, or root `CLAUDE.md`'s lifecycle. Inventing one here would mean inventing a legal/procedural concept — root `CLAUDE.md`: "Never invent legal or regulatory facts" | Dropped from Phase 1. If this is a real requirement, it needs its own spec with a named source for what "enforcement" means in Legal Metrology practice |
| Verification Scheduling: pick a **time**, not just a date | Spec 05 D3 already resolved this: **"Date only, no time slot"** (ASSUMPTION), and it's load-bearing (`inspections.scheduled_date` is a `date` column, no migration pending) | Unchanged — Super Admin sees the same date-only `scheduled_date` every other role sees |
| "Scrutiny" screen with ACCEPT / QUERY-DEFICIENCY actions and a bespoke checklist | This is spec 11's **document review checklist** under different names — the real states are `DOCUMENT_REVIEW` → `SCHEDULED` or → `DOCUMENTS_DEFICIENT`, not "Accept"/"Query" | Reuse the existing checklist/status vocabulary verbatim; no parallel terminology |
| Add/manage States & Districts | `REGIONS` (`app/core/regions.py`) is a Python constant, not a table — see `docs/specs` conversation history (session "polish"): all 36 states/UTs + full district lists were just hand-populated there, flagged `ASSUMPTION`. Making this admin-editable is a schema change (a real `regions`/`districts` table) and a correctness risk (every `state_code`/`district_code` column everywhere references these codes) | Out of scope. Flagged as a real gap (§9) if it's ever needed |
| Notification Center (in-app alerts) | No in-app notification system exists. Only outbound email exists (Resend, certificate-expiry reminders only, step 10) | Dropped from Phase 1 — see §9 |
| Reports: generate/export CSV/PDF for 9 report types | No generic reporting/export engine exists; only one PDF exists today (the certificate, spec 08) | Dropped from Phase 1 — tables are already filterable/searchable on screen; CSV export is a reasonable Phase 2 add (§9), building a 9-report engine is not |
| LMO/GATC "performance" (pass rate, workload trend charts) | Computable in principle from `inspection_checklist_items`/`Application.status`, but needs new aggregation endpoints with real query cost — not a free reuse | Phase 1 ships **counts** (pending/completed cases) via `scope_applications`; pass-rate/workload **trend charts** move to Phase 2 (§9) |
| User "Approve" action | No such concept exists: officials are created directly by Super Admin (`POST /users`, already live), already active. Only `BUSINESS` self-registers, and it is never gated on approval | Dropped — "Create" and "Activate/Deactivate" cover the real lifecycle |

Everything else in the brief (dashboard KPIs, application/instrument/certificate management,
expiry monitoring, GATC/LMO directories with real counts, basic user management, audit logs) maps
cleanly onto data this system already has. That's Phase 1, below.

## 3. What this reuses outright (no new backend work)

| Section | Endpoint | Notes |
|---|---|---|
| Applications list/search/filter | `GET /api/applications` | Already unscoped for `SUPER_ADMIN` (`scope_applications`); supports `q`, `status`, `instrument_id`, `sort` |
| Applications totals by status | `GET /api/applications/stats` | Already unscoped for `SUPER_ADMIN`; all statuses zero-filled |
| Application detail, review checklist, assigned officer/GATC | `GET /api/applications/{id}` | Unchanged — Super Admin is already in `READER_ROLES` |
| Instruments list/search | `GET /api/instruments` | Already unscoped for `SUPER_ADMIN` (`scope_instruments`) |
| Certificate status buckets (valid/expiring/expired/revoked/superseded) | `GET /api/admin/certificates/stats` | Already `ADMIN_ROLES`-gated (includes `SUPER_ADMIN`), jurisdiction-scoped (unscoped for Super Admin) |
| Expiring-soon certificate list | `GET /api/admin/certificates/expiring-soon` | Same as above |
| Certificate detail / PDF | `GET /api/certificates/{id}`, `.../pdf` | Unchanged |
| Create an official account | `POST /api/users` | Already `SUPER_ADMIN`-only; creates `STATE_ADMIN`/`DISTRICT_ADMIN`/`LM_OFFICER` (not `GATC` — deferred by the schema's own docstring, not a gap this spec reopens) |
| GATC eligibility by category | `GET /api/gatc/eligible` | `LM_OFFICER`-only today (§7 D1 on whether to extend it) |

## 4. New backend surface needed (no migrations — every field below already exists on an
existing table; this is new routes/queries only)

| New endpoint | Role | Purpose |
|---|---|---|
| `GET /api/users` | `SUPER_ADMIN` | Paginated list of official accounts (`role != BUSINESS`, since `GATC`/`BUSINESS` orgs aren't managed here — see §7 D2), filterable by `role`, `state_code`, `district_code`, `is_active`, free-text `q` on name/email |
| `PATCH /api/users/{id}` | `SUPER_ADMIN` | Only `{"is_active": bool}` (`StrictModel`, nothing else writable here — email/role/jurisdiction edits are a separate, harder decision, §9) |
| `GET /api/audit-logs` | `SUPER_ADMIN` | Paginated, filterable by `date_from`/`date_to`, `actor_user_id`, `action`, `entity_type` — straight read of the existing `audit_logs` table, already fully populated by every write path in this codebase |
| `GET /api/organizations?type=GATC` | `SUPER_ADMIN` | A GATC directory: org name, state/district, `gatc_eligible_category_ids`, and **computed** pending/completed case counts (`COUNT` over `applications` joined through `inspections.assigned_officer_id`'s organization) |
| `GET /api/applications` gains `state_code`/`district_code` query params | `SUPER_ADMIN`-relevant, but harmless for every role (officials are already jurisdiction-locked by scope, so the params are a no-op refinement for them) | Lets the state-wise table (§6.4) and the Applications page drill into one state/district without a second endpoint |

No new tables, no new columns, no Alembic migration. This is the cheapest possible version of
"Super Admin can see everything" — it is pure read (plus one `is_active` toggle) over data every
other part of the app already writes correctly.

### "Active LMOs" / "Active GATCs" KPI cards

Defined as: `COUNT(users) WHERE role = 'LM_OFFICER' AND is_active` and the count of **organizations**
with `type = 'GATC'` that have at least one active `GATC`-role user — both answerable by the new
`GET /api/users` list's `total` field with the right filters (no separate endpoint needed; the
dashboard just calls the list endpoint with `page_size=1` the same way `InstrumentsSection`
already does for instrument counts, per `frontend/CLAUDE.md`'s existing "never aggregate paged
data on the client" rule).

## 5. Access

All of §3/§4 is `ADMIN_ROLES`-shaped data (every endpoint already uses `scope_*` helpers that
already support `STATE_ADMIN`/`DISTRICT_ADMIN` at a narrower jurisdiction). **This spec still scopes
the new frontend page to `SUPER_ADMIN` only** (§7 D1) — not because the data layer can't support
the other two admin roles (it already can, for free), but because:

- The pasted brief's own "Role" line says Super Admin specifically.
- `POST /api/users` and the two new endpoints that touch accounts (`GET/PATCH /api/users`) are
  already, or should be, `SUPER_ADMIN`-only — a `STATE_ADMIN` managing officials outside its own
  rank is a real RBAC question this spec doesn't want to silently decide.
- `STATE_ADMIN`/`DISTRICT_ADMIN` keep the existing, simpler `/admin` page (spec 10) — unchanged by
  this spec.

If a future spec wants `STATE_ADMIN`/`DISTRICT_ADMIN` to get this same richer page at their own
jurisdiction, the backend changes needed are small (the `scope_*` helpers already narrow correctly)
— flagged in §9, not built here.

## 6. Page contract

### 6.1 Dashboard (`/admin` — the existing `ADMIN_ROLES`-shared page gets a `SUPER_ADMIN`-only
richer variant; `STATE_ADMIN`/`DISTRICT_ADMIN` keep today's page unchanged)

```
┌ Super Admin ───────────────────────────────────────────────────┐
│ [Instruments: N] [Applications: N] [Pending: N] [Under verif.: N]│  KPI cards, §4.1
│ [Certificates valid: N] [Expiring: N] [Expired: N]                │
│ [Active LMOs: N] [Active GATCs: N]                                 │
│                                                                    │
│ Verification overview                                             │
│  [Submitted N] [Document review N] [Deficient N] [Scheduled N]    │  from GET /applications/stats
│  [Inspection N] [Approved N] [Rejected N] [Certificate issued N]  │  (existing statuses, unrenamed)
│                                                                    │
│ State-wise overview                            [table, not a map] │
│  State | Instruments | Pending apps | Certs valid | Certs expired │  §6.4
│  JH    | 142         | 8            | 51          | 3             │
│  → View                                                            │
│                                                                    │
│ Recent activity                                   → Audit logs    │
│  5 most recent audit_logs rows                                    │
│                                                                    │
│ Quick actions: View pending applications · View expiring certs ·  │
│                Create official account                            │
└────────────────────────────────────────────────────────────────┘
```

Every section follows the existing `lib/use-async.ts` contract (own loading / error+Retry / empty
state), same as the business and officer dashboards (specs 04/05).

**Dropped from the brief's dashboard, explicitly:** "Open enforcement cases" KPI (§2), "Monthly
applications/verifications" and "Re-verification activity" **charts** (no re-verification concept
exists — a new application is how re-verification happens, per root `CLAUDE.md`'s lifecycle; a
trend chart needs a time-bucketed aggregation endpoint that doesn't exist yet — Phase 2, §9), the
India map (table instead, §6.4).

### 6.2 Applications (`/admin/applications` — a Super-Admin-scoped list reusing the existing
applications list components)

Same table/columns the business/officer applications list already renders
(`frontend/app/applications/page.tsx`), plus **State** and **District** columns (already on
`ApplicationOut`) and the two new filter params from §4. Row click goes to the existing
`/applications/{id}` detail page — unchanged, since `SUPER_ADMIN` is already a full `Reader`.

**Not built:** a parallel "Assign LMO/GATC" action at the application-list level. Assignment
already happens at the right moment in the existing workflow (the scheduling `LM_OFFICER` routes to
GATC at `DOCUMENT_REVIEW → SCHEDULED`, spec 15) — a Super Admin reassigning mid-flight is a
materially different, riskier feature (it would need to handle an in-progress or already-submitted
checklist) and isn't in scope here.

### 6.3 Instruments (`/admin/instruments`) and Certificates (`/admin/certificates`)

Same reuse pattern: the existing instrument list/detail and certificate admin views
(`/instruments`, `/certificates/[id]`, `GET /admin/certificates/expiring-soon`), unfiltered by
jurisdiction for Super Admin. No new UI beyond removing the jurisdiction scope's effect (already
automatic server-side — nothing to build except making sure the page is reachable from the Super
Admin's own nav).

### 6.4 State-wise overview (table, not a map)

One row per state in `REGIONS` with data: instrument count, pending-applications count,
certificates-valid count, certificates-expired count — four `COUNT ... GROUP BY state_code` queries
(reusing existing scoped tables with `scope_*` stripped to `SUPER_ADMIN`'s unscoped case), not four
new concepts. A state with zero instruments/applications simply shows zeros — `REGIONS` already
lists every state/UT regardless of whether any data exists for it yet.

### 6.5 GATC directory (`/admin/gatc`) and LMO directory (`/admin/lmo`)

Two read-only tables from §4's new endpoints:

- **GATC:** org name, state/district, eligible categories (names, via `instrument_categories`),
  pending cases, completed cases, active/inactive. No "Principal Officer" column — that concept
  doesn't exist on `Organization` (no column for it); adding one is a schema change out of scope
  here (§9).
- **LMO:** name, state, district, pending cases (`scope_applications`-equivalent count for that
  one officer, not the whole jurisdiction), completed cases, active/inactive.

**Dropped:** pass/fail rate and workload **trend** — Phase 2 (§9). "Activate/deactivate" reuses the
one `PATCH /api/users/{id}` from §4 for both directories.

### 6.6 Users (`/admin/users`)

Table: name, email, role, state/district, active. Actions: **Create** (opens the existing
`POST /api/users` form — `STATE_ADMIN`/`DISTRICT_ADMIN`/`LM_OFFICER` only, matching the schema's
existing role restriction) and **Activate/Deactivate** per row.

**Explicitly not built:** editing a user's email, role, or jurisdiction after creation. The backend
has no endpoint for this, and silently reassigning a `DISTRICT_ADMIN`'s district_code after they
already have a jurisdiction-scoped history (applications they reviewed, etc.) is a real design
question (does old history move with them?) that deserves its own decision, not a drive-by field on
this page.

### 6.7 Audit logs (`/admin/audit-logs`)

Table: timestamp, actor (name/email — join `users`, fall back to "System" for the `actor_user_id IS
NULL` rows the expiry job and CLI already write), action, entity type, entity id, a `details`
JSON viewer (expand/collapse, since `details` shapes vary per action — never attempt one unified
schema for it). Filters: date range, actor, action, entity type — all `GET /api/audit-logs` query
params from §4.

### 6.8 Sidebar

```
Dashboard
Applications
Instruments
Certificates
  Expiring soon
GATC directory
LMO directory
Users
Audit logs
```

Flatter than the brief's two-level tree (Verification/Administration/Analytics groups) — there's
nothing under those groups yet that isn't one of the nine items above, so the nesting would be
decoration, not information. `AppShell`'s existing sidebar component (`components/app-shell.tsx`)
already renders a flat list for every other role; this follows the same pattern rather than adding
a new nested-menu component for one role.

## 7. Decisions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Build this page for `SUPER_ADMIN` only, or make it jurisdiction-generic for all three admin roles from day one? | **`SUPER_ADMIN` only for Phase 1** | Matches the brief's stated role; the account-management endpoints (§4) are already-or-should-be `SUPER_ADMIN`-only regardless; the data-layer scoping already generalizes for free later (§5) |
| D2 | Should `GET /api/users` include `BUSINESS`/`GATC` accounts too? | **No — officials only (`role != BUSINESS`), and list `GATC` users through the GATC directory (§6.5), not the Users page** | A `BUSINESS` user is managed by registering/logging in, never by a Super Admin editing them directly (no such need exists anywhere in the current product); mixing all five+ roles into one undifferentiated table would also leak every business owner's identity to a page whose job is official-account administration |
| D3 | Extend `GET /api/gatc/eligible` to `SUPER_ADMIN`, or build the new `GET /api/organizations?type=GATC` directory (§4) instead? | **New directory endpoint** | `gatc/eligible` is purpose-built for the scheduling officer's allocation dropdown (category-filtered, no case-count columns); forcing it to also serve a general-purpose directory page would couple two different call sites' needs onto one response shape |
| D4 | CSV/PDF export on these tables? | **Not in Phase 1** — every table is already paginated/filterable on screen, which covers "I need to find X," the actual job these tables do today | A generic multi-format export engine is real, separate work (brief's §13 asked for 9 report types) — worth its own spec if a specific report is actually needed, not a one-line add-on here |
| D5 | `PATCH /api/users/{id}` — allow more than `is_active`? | **No, `is_active` only, `StrictModel` (extra fields → 422)** | Keeps this endpoint's blast radius small and matches the "Activate/deactivate" action the brief and this spec actually describe; broader profile editing is §6.6's explicitly-deferred item |
| D6 | Where do "pending/completed case" counts for LMO/GATC directories come from — a live query per row, or a precomputed/cached figure? | **Live query, same as every other `*_stats` endpoint in this codebase** (`GET /applications/stats`, `GET /admin/certificates/stats`) | Consistent with the existing "server computes the aggregate, never the client" rule (`frontend/CLAUDE.md`); MVP data volumes don't need caching yet — revisit only if the directory page is measurably slow |

### rev 2 additions — three calls made with the user before implementation

| # | Decision | Resolution | Why |
|---|---|---|---|
| D7 | Should `SUPER_ADMIN`'s sidebar drop the "Profile" link (not in §6.8's 9-item list)? | **No, keep it.** `SUPER_ADMIN_NAV` includes `/profile` alongside the 9 spec items | Profile was added to every role's nav in the prior session; dropping it for `SUPER_ADMIN` specifically would be an unintended regression |
| D8 | "Certificates" nav target: reuse `/applications?status=CERTIFICATE_ISSUED`, or build a dedicated list? | **Dedicated list** (`GET /api/certificates`, new — §1.6/§4 amendment below) | User's explicit choice over the cheaper reuse option |
| D9 | Should `PATCH /api/users/{id}` allow a Super Admin to deactivate their own account? | **No — 409 "Cannot deactivate your own account."** Not in the original spec text; added as a safety guard during implementation planning | A lone Super Admin locking themselves out, with nobody left to re-enable the account, is an unrecoverable MVP failure mode; the check is one line and costs nothing |

D8 means one endpoint beyond this spec's original §4: **`GET /api/certificates`** (no certificate
list endpoint existed before this step — only `GET /certificates/{id}` and `.../pdf`). Same
`Reader` role set and `scope_certificates()` as every other certificate endpoint, `?status=`
filter, reuses the existing `CertificateOut` schema verbatim. See `backend/CLAUDE.md`'s "Super
Admin (step 17)" subsection for the exact implementation.

## 8. Frontend/backend file list (as built)

```
backend:
app/core/roles.py               + OFFICIAL_ROLES
app/routers/users.py            + GET "" (list), PATCH "/{id}" (is_active only)
app/routers/audit.py            (new) GET /audit-logs
app/routers/organizations.py    (new) GET "" ?type=GATC, with case-count aggregation
app/routers/admin.py            + GET /admin/state-overview (table data, §6.4)
app/routers/certificates.py     + GET "" (list) — D8 amendment
app/routers/applications.py     + state_code/district_code query params on GET ""
app/main.py                     registers audit.router, organizations.router
app/schemas/user.py             + UserListOut, UserActivate
app/schemas/audit.py            (new) AuditLogOut
app/schemas/organization.py     (new) GatcDirectoryOut, GatcDirectoryUserOut
app/schemas/admin.py            + StateOverviewRow
app/services/users.py           + list_users(), set_active()
app/services/audit.py           + list_audit_logs() (read side, alongside the existing log() writer)
app/services/organizations.py   (new) gatc_directory()
app/services/admin.py           + state_overview()
app/services/certificates.py    + list_certificates() — D8 amendment
app/services/applications.py    list_applications() gains state_code/district_code kwargs
tests/test_users.py, test_audit_logs.py, test_organizations.py,
  test_admin_state_overview.py  (new)
tests/test_rbac.py, test_certificates.py, test_applications_crud.py  (extended)

frontend:
app/admin/page.tsx                            SUPER_ADMIN -> SuperAdminDashboard,
                                               other ADMIN_ROLES -> ExpiryDashboard (unchanged)
components/admin/expiry-dashboard.tsx         (new) extracted verbatim from the old app/admin/page.tsx
components/admin/super-admin-dashboard.tsx    (new) §6.1
components/admin/state-overview-table.tsx     (new) §6.4
components/admin/active-badge.tsx             (new) shared by Users/GATC/LMO
components/admin/user-create-form.tsx         (new) §6.6
app/admin/certificates/expiring-soon/page.tsx (new) wraps ExpiryDashboard
app/admin/certificates/page.tsx               (new) the dedicated list — D8 amendment
app/admin/applications/page.tsx               (new) §6.2
app/admin/gatc/page.tsx                       (new) §6.5
app/admin/lmo/page.tsx                        (new) §6.5
app/admin/users/page.tsx                      (new) §6.6
app/admin/audit-logs/page.tsx                 (new) §6.7
components/app-shell.tsx                      SUPER_ADMIN_NAV (10 items incl. Profile, D7)
                                               instead of today's single "Admin" link
lib/api.ts, lib/types.ts                      new types/calls for the endpoints above
```

## 9. Explicitly deferred (recorded, not committed)

- India map visualization (would need Leaflet — a deferred technology; the state-wise **table**
  in §6.4 is the Phase 1 substitute).
- Enforcement Management module — no data model, no named legal basis. Needs its own spec with a
  real source for what "enforcement case" means here, not an assumption.
- Notification Center (in-app alerts/badges).
- CSV/PDF report export engine (9 report types from the brief's §13).
- Trend charts (monthly applications/verifications, re-verification volume, workload-over-time).
- Dynamic State/District/Jurisdiction management UI (`REGIONS` stays a code constant, not a table).
- Editing a user's email/role/jurisdiction after creation; a "Principal Officer" field on GATC
  organizations.
- Extending this page's jurisdiction-generic data layer to `STATE_ADMIN`/`DISTRICT_ADMIN` (noted in
  §5/D1 as cheap later, not built now).

## 10. Acceptance criteria

- [x] As a `SUPER_ADMIN`: dashboard shows national KPIs matching `GET /applications/stats` +
  `GET /admin/certificates/stats` totals exactly (no client-side aggregation of paged data) —
  confirmed live via browser against real Supabase data (2 instruments, 2 applications).
- [x] Applications/Instruments/Certificates pages show data across every state/district, not just
  Jharkhand — `tests/test_admin_state_overview.py::test_super_admin_sees_data_outside_jh_br`
  seeds data in Karnataka and confirms it's visible.
- [x] GATC and LMO directories show correct pending/completed counts that match a manual count —
  `tests/test_organizations.py::test_pending_and_completed_case_counts`,
  `tests/test_users.py::test_lm_officer_filter_populates_case_counts`.
- [x] Creating a user via the Users page round-trips through the existing `POST /api/users`
  unchanged; deactivating a user immediately blocks their next login — confirmed both by
  `tests/test_users.py::test_patch_toggles_is_active_and_blocks_next_login` and live in the
  browser (create → list refreshes → deactivate → `ActiveBadge` flips to Inactive).
- [x] Audit logs page shows the just-created user's `USER_CREATED` row with the right actor, and
  the details `Dialog` renders the pretty-printed JSON — confirmed live in the browser.
- [x] `STATE_ADMIN`/`DISTRICT_ADMIN`/`LM_OFFICER`/`GATC`/`BUSINESS` all get 403 on every new
  endpoint — parametrized sweeps in `tests/test_rbac.py`.
- [x] Self-deactivation is blocked (D9) — `tests/test_users.py::test_patch_self_deactivation_is_409`.
- [x] The dedicated certificates list (D8) works, filterable by status —
  `tests/test_certificates.py::test_list_certificates_pagination_and_scoping`/
  `test_list_certificates_status_filter`.
- [x] `backend/CLAUDE.md` and `frontend/CLAUDE.md` updated: new endpoints, new pages, the
  `SUPER_ADMIN`-only scoping decision (D1), and the stale pre-existing "migration not yet applied
  to Supabase" markers for `0012`/`0013` corrected (found stale during this step's planning, not
  something this step's own migrations caused — this step adds no migrations of its own).

## 11. Verification record

Backend (`pytest`, local `lm_test`): full suite green, zero modifications to any pre-existing
test's assertions (two pre-existing tests were extended in place —
`test_instruments_rbac.py`/`test_public_verify.py`'s JH-district assertions, from an unrelated
same-session change, not this spec). New/extended files: `tests/test_users.py` (11 tests),
`tests/test_audit_logs.py` (7), `tests/test_organizations.py` (7),
`tests/test_admin_state_overview.py` (5), plus RBAC sweeps added to `tests/test_rbac.py` and new
cases in `tests/test_certificates.py`/`tests/test_applications_crud.py`. `ruff check .` and
`ruff format --check .` both clean.

A real bug was found and fixed during implementation, not anticipated by this spec:
`services/organizations.py`'s case-count query originally wrapped `db.execute(...).all()` directly
in `dict(...)` — but the query selects three columns (`org_id, pending, completed`), and `dict()`
on a 3-tuple sequence raises `ValueError: dictionary update sequence element #0 has length 3; 2 is
required`. Fixed by building the dict explicitly:
`{org_id: (pending, completed) for org_id, pending, completed in count_rows}`. Caught immediately
by `tests/test_organizations.py`'s first run, not by manual testing.

A second bug, same family: `services/certificates.py: list_certificates()` initially ordered by
`Certificate.issued_at`, a column that doesn't exist on the ORM model (`issued_at` is a
`CertificateOut` schema field, derived at read time — the underlying table column, from the
`Timestamps` mixin, is `created_at`). Caught by a live smoke-test request (500,
`AttributeError: type object 'Certificate' has no attribute 'issued_at'`) before any automated
test was written for it, then fixed and covered by `test_list_certificates_pagination_and_scoping`.

Frontend (`tsc --noEmit`, `eslint .`, `next build`): all clean. `next build` additionally cleared
a stale `.next/types` route-type cache mismatch that had been present since before this step
(unrelated to this step's own code — a `.next/types/routes.d.ts` left over from a build that
predated an earlier same-session route addition).

Manual, in Chrome, logged in as a real `SUPER_ADMIN` account against a live Supabase-backed
instance (not seed data — the account and a handful of real instruments/applications already
existed from earlier in the session):
- Sidebar showed all 10 `SUPER_ADMIN_NAV` items, including Profile (D7).
- `/admin` dashboard rendered real KPI numbers (2 instruments, 2 applications, 0 certificates, 0
  active LMOs/GATCs), a "2 Submitted" status chip, all 36 states in the state-wise table
  (confirmed by scrolling through the full list), and a "Super Admin — LOGIN_SUCCEEDED" row in
  Recent activity.
- `/admin/applications` showed both real applications with correct State/District columns.
- `/admin/users`: created an official account end-to-end through the dialog (full name → email →
  password → role → cascading state/district selects, Jharkhand → Dhanbad rendered correctly),
  the dialog closed and the list refreshed with the new row; clicked Deactivate, the `ActiveBadge`
  flipped to Inactive immediately (self-deactivation guard correctly did *not* block this, since
  it targeted a different user than the logged-in Super Admin).
- `/admin/audit-logs` showed the resulting `USER_CREATED` and `USER_STATUS_CHANGED` rows with the
  correct actor; "View details" opened a dialog with the pretty-printed JSON
  (`{"role": "LM_OFFICER", "is_active": false}`); older `System`-actor rows (`LOGIN_FAILED`,
  a prior CLI-created `USER_CREATED`) correctly rendered "System", not blank or an error.
- `/admin/lmo` showed the newly created (and just-deactivated) officer with correct 0/0 case
  counts and an Inactive badge.
- `/admin/gatc` and `/admin/certificates` correctly rendered their empty states ("No GATC
  organizations match." / "No certificates match.") — no GATC org or certificate exists in this
  particular database yet.
- `/admin/certificates/expiring-soon` rendered the original four-card expiry dashboard unchanged.

One environment-only snag, unrelated to the implementation: `next start`'s rewrite destination
(`API_ORIGIN`) is baked into `.next/routes-manifest.json` at **build** time, not read fresh at
server-start time — a build run without the env var set serves the default origin regardless of
what's exported before `next start`. Rebuilding with `API_ORIGIN` set fixed it. Worth remembering
for any future production-mode verification against a non-default backend.

One disclosed side effect: verification created two disposable accounts directly against the
live Supabase database — a `BUSINESS` org ("Spec17 Test Co" / `spec17test@example.com`, created
while smoke-testing `POST /auth/register` for the 403 sweep) and an `LM_OFFICER`
("Test Officer Dhanbad" / `test.officer.spec17@test.demo`, created through the real `/admin/users`
UI flow, currently deactivated). Neither is seed data and no delete-user endpoint exists in this
app to remove them through normal means; flagged for the user to remove directly if desired.
