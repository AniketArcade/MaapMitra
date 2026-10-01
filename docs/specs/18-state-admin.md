# Spec 18 — State Admin page

**Status:** Done. Implemented and verified (§11). §7's Decisions (D1–D6) were accepted as written,
following the implementation plan derived from this spec.
**Build order:** Step 18 (post-MVP addition, on top of steps 1–17)
**Depends on:** Spec 01 (`Role`, RBAC, `ROLE_RANK` — defined but **never used** anywhere in the
codebase today; this is its first consumer), Spec 10 (`ADMIN_ROLES`, `GET /admin/certificates/*`),
Spec 15 (`scope_organizations`, GATC directory), Spec 17 (`GET /api/users`, `PATCH /api/users/{id}`,
`GET /api/audit-logs`, `GET /api/organizations?type=GATC`, `GET /api/certificates`,
`GET /admin/state-overview` — this spec extends four of these rather than inventing new ones)
**Source input:** a pasted "State Admin — Frontend Specification" brief (20 sections: dashboard,
district/application/LMO/GATC/instrument/certificate management, assignment & scheduling, expiry
monitoring, enforcement, state analytics, reports, notifications, audit logs, user & role
management, state settings, sidebar). That brief is the starting point, not its contents verbatim
— §2 explains why, following the same pattern spec 17 §2 already established for its own brief.

## 1. Goal

Root `CLAUDE.md`'s role table puts `STATE_ADMIN` directly below `SUPER_ADMIN`. Today a
`STATE_ADMIN` who logs in gets the exact same page a `DISTRICT_ADMIN` gets: the plain
`ExpiryDashboard` from step 10 (four certificate-count cards + an expiring-soon table), nothing
more — despite `STATE_ADMIN` already being a first-class branch in **every** `scope_*` helper
(`app/services/scoping.py`): `scope_instruments`, `scope_applications`, `scope_organizations` all
already filter correctly to "the caller's own `state_code`, every district inside it." This spec
is the same move spec 17 made for `SUPER_ADMIN`: turn a data layer that already supports the role
into an actual page, reusing what exists instead of inventing a parallel system.

Demo relevance: the seed data's whole story (ABC Traders, Dhanbad, Jharkhand) lives inside one
state. A `STATE_ADMIN` for Jharkhand, logging in, would see that exact activity — instruments,
applications, the certificate once issued — automatically, through the scoping that already
exists, with no per-state wiring needed.

## 2. Why this spec is narrower than the pasted brief

Same reasoning spec 17 §2 already established, applied to the parts of this brief that repeat the
same patterns:

| Brief asks for | Why it doesn't fit as asked | What this spec does instead |
|---|---|---|
| Enforcement Management (cases, violations) | No `enforcement`/`violation` concept exists anywhere in the data model or lifecycle — same gap spec 17 §2 already flagged, not reopened here | Dropped. Needs its own spec with a named legal source, same as spec 17 said |
| Notification Center (in-app alerts) | No in-app notification system exists; only outbound email (Resend, certificate-expiry reminders, step 10) | Dropped — same as spec 17 §9 |
| Reports: generate/export 10 report types (PDF/Excel/CSV) | No generic export engine exists | Dropped — tables are already filterable/searchable on screen (spec 17 D4's reasoning again) |
| State Analytics: monthly trend charts, LMO/GATC workload charts | Needs new time-bucketed aggregation endpoints — real, separate work, not a free reuse (spec 17 §2 made the identical call for national trend charts) | Dropped from Phase 1 — counts and the district-performance table (below) ship instead; charts flagged for Phase 2 (§9) |
| Dynamic District Configuration (adding/renaming districts) | `REGIONS` is a Python constant, not a table (spec 17 §2's own entry on this, unchanged) | Out of scope |
| State Settings (notification settings, administrative preferences) | No settings concept exists for any role in this app today — not even a stub table | Dropped entirely, not even a read-only page: there is nothing real to show |
| "Assign LMO/GATC" as a State-Admin action in Assignment & Scheduling | Assignment already happens at the correct moment in the existing workflow: the scheduling `LM_OFFICER` routes `DOCUMENT_REVIEW → SCHEDULED` to a GATC (spec 15). A State Admin reassigning mid-flight would need to handle an in-progress or already-submitted checklist — spec 17 §6.2 ruled out the identical action for Super Admin for the same reason | Monitoring only (§6.7): see who's assigned, see the date, link into the existing applications flow. No reassignment action |
| Scheduling: pick a time, not just a date | Spec 05 D3: "Date only, no time slot" (ASSUMPTION), load-bearing (`inspections.scheduled_date` is a `date` column) | Unchanged |
| "Scrutiny" screen with ACCEPT / QUERY-DEFICIENCY actions | This is spec 11's document review checklist under different names — the real states are `DOCUMENT_REVIEW → SCHEDULED` or `→ DOCUMENTS_DEFICIENT` | Reuse the existing checklist/status vocabulary verbatim (§6.4) |
| "Average Scrutiny Time" | Computable in principle from `application_status_history` timestamps, but no endpoint aggregates it today — real new work, not a free reuse | Dropped from Phase 1, flagged for Phase 2 (§9) |
| User & Role Management: Assign Role, Assign District, Reset Access | No endpoint anywhere edits a user's role or jurisdiction after creation — spec 17 §6.6 explicitly deferred this for the identical reason (does old jurisdiction-scoped history move with them?) | Create + Activate/Deactivate only (§6.14), same two actions spec 17 built |

Everything else (district-wise KPIs, application/instrument/certificate monitoring within one
state, LMO/GATC directories, expiry monitoring, a narrower user directory, audit logs) maps onto
data this system already has, scoped to one state — much of it by `scope_*` branches that already
exist and have simply never had a frontend page built on top of them.

## 3. What this reuses outright (no new backend work)

The headline fact this spec rests on: **every endpoint below already returns `STATE_ADMIN`-scoped
data today** — the scoping was built once, generically, in step 1 and never revisited per-role.
Nothing here needs a new `scope_*` branch; it needs a frontend page that calls what's already
correct.

| Section | Endpoint | Notes |
|---|---|---|
| Applications list/search/filter | `GET /api/applications` | `READER_ROLES` already includes `STATE_ADMIN`; `scope_applications` already restricts to the caller's `state_code`. `district_code` query param (added in spec 17) already narrows further |
| Applications totals by status | `GET /api/applications/stats` | Same `Reader`/`scope_applications`; all 9 statuses zero-filled |
| Application detail, checklist, assigned officer/GATC | `GET /api/applications/{id}` | Unchanged — `STATE_ADMIN` is already a `Reader` |
| Instruments list/search (`instrument_type`, `district_code` filters already exist) | `GET /api/instruments` | `scope_instruments` already restricts to the caller's state |
| Certificate list, detail, PDF | `GET /api/certificates`, `GET /api/certificates/{id}`, `.../pdf` | Built in spec 17 (D8); its `Reader`/`scope_certificates` already admits `STATE_ADMIN` — this is not `SUPER_ADMIN`-only today |
| Certificate status buckets, expiring-soon list | `GET /admin/certificates/stats`, `GET /admin/certificates/expiring-soon` | `ADMIN_ROLES`-gated (already includes `STATE_ADMIN`), `scope_certificates`-scoped — this is the exact data the current `ExpiryDashboard` already renders for this role, unchanged |
| GATC eligibility-by-category (scheduling officer's own tool) | `GET /api/gatc/eligible` | Unchanged, `LM_OFFICER`-only, not reused here (this page monitors, doesn't schedule) |

No new tables, no migration, and — unlike most of this surface — **no router role-gate change
either** for this section: `STATE_ADMIN` can call every endpoint above right now. This spec's job
for these rows is purely a new frontend (§6).

## 4. New backend surface needed

Unlike §3, these four existing (spec 17) endpoints are gated `SUPER_ADMIN`-only today and need a
genuinely new per-role scoping rule, not just a router dependency swap — because, unlike
`scope_instruments`/`scope_applications`/`scope_organizations`, the `users` table has no `scope_*`
helper at all (it's permission-gated, not row-owned-by-org data). Getting this wrong means a
`STATE_ADMIN` could query another state's officials — treat this section as the real work in this
spec, not a formality.

| Endpoint | Change | New rule for a `STATE_ADMIN` caller |
|---|---|---|
| `GET /api/organizations?type=GATC` | Router role-gate only — **zero service changes** | `services/organizations.py: gatc_directory()` already calls `scope_organizations(select(...), user)`, and that helper already has a `STATE_ADMIN` branch (`scoping.py:116-119`). Its own docstring says so: *"future-proofs for free if a narrower admin role ever reuses this directory (spec 17 §5)."* This is that reuse |
| `GET /api/users` | Service gains actor-aware forcing, not just a role-gate swap | `state_code` is **forced to `actor.state_code`**, never taken from the query string for a `STATE_ADMIN` caller (a client-sent `state_code` differing from the actor's own is rejected — `422`, not silently overridden, so the UI can't be confused about whose data it's looking at). `role` filter is restricted to `{DISTRICT_ADMIN, LM_OFFICER}` — requesting `STATE_ADMIN`/`SUPER_ADMIN`/omitting `role` while results would include peers-or-above → `403`. This is `ROLE_RANK`'s first real use: "only see ranks strictly below your own" |
| `PATCH /api/users/{id}` | Service gains a target-row check | Target user's `state_code` must equal `actor.state_code` **and** `ROLE_RANK[target.role] < ROLE_RANK[actor.role]` (so only `DISTRICT_ADMIN`/`LM_OFFICER`) — otherwise `403`. The existing self-deactivation guard (spec 17 D9) is unconditional and unchanged |
| `POST /api/users` | Service gains the same two checks as `PATCH`, at creation time | `role` restricted to `{"DISTRICT_ADMIN", "LM_OFFICER"}` for a `STATE_ADMIN` actor (`UserCreate.role` already permits `STATE_ADMIN` too, for `SUPER_ADMIN` callers — this is a narrower check on top, not a schema change). `state_code` must equal `actor.state_code` (`422` if not — same "fail loud, don't silently redirect" rule as the `GET` above) |
| `GET /api/audit-logs` | Service gains a jurisdiction filter — **the one genuinely hard piece, flagged, not silently simplified** | See the dedicated subsection below |
| *(new)* `GET /admin/district-overview` | New endpoint, same router (`routers/admin.py`), same `Admin = require_roles(*ADMIN_ROLES)` dependency already on it | See below — a direct structural copy of `services/admin.py: state_overview()`, one level down |

### `GET /admin/audit-logs` jurisdiction filter — the one real complexity in this spec

`audit_logs` has **no jurisdiction column** (by design — a cross-cutting system table, per the
backend `CLAUDE.md`'s own note on this). Resolving "did this row happen inside my state" needs two
different joins depending on who the actor was:

- An **official** actor (`STATE_ADMIN`/`DISTRICT_ADMIN`/`LM_OFFICER`) carries `state_code` directly
  on their own `users` row — join `AuditLog.actor_user_id → users.state_code`.
- A **`BUSINESS`/`GATC`** actor has `state_code = NULL` on their own row (officials-only column,
  per `users`' own `district_scope`/`state_admin_scope` check constraints) — their jurisdiction
  lives on their `organization`, reachable either via `users.organization_id → organizations.
  state_code` or via `AuditLog.organization_id` directly (already populated on most, not all,
  `audit.log()` call sites — see `backend/CLAUDE.md`'s data model section).
- A **system** actor (`actor_user_id IS NULL`, e.g. the expiry job's `CERTIFICATE_EXPIRED` row) has
  no user and no organization to join through at all.

**Recommendation (D4): Phase 1 filters to rows where an official or org actor's own state matches
— `WHERE users.state_code = :state OR organizations.state_code = :state`, via two outer joins
(`AuditLog.actor_user_id → users`, `users.organization_id → organizations`) — and excludes every
system-actor row from a `STATE_ADMIN`'s view entirely.** This is an honest, disclosed gap, not a
silent one: a `STATE_ADMIN` would not see `CERTIFICATE_EXPIRED` rows for certificates in their own
state. Resolving that properly needs an `entity_type`-specific join (certificate → application →
state_code) that doesn't exist today and isn't worth building for one audit action — flagged in
§9, not built here.

### `GET /admin/district-overview` — the district-level sibling of spec 17's state-overview

`services/admin.py: state_overview()` already does exactly this shape one level up (one row per
`REGIONS` key, zero-filled, three `GROUP BY` queries over `scope_instruments`/
`scope_applications`/`scope_certificates` merged in Python). This is a direct structural copy,
grouped by `district_code` within one state instead of by `state_code` across all of them:

```python
def district_overview(db: Session, user: User, *, state_code: str | None) -> list[DistrictOverviewRow]:
    effective_state = user.state_code if user.role != Role.SUPER_ADMIN else state_code
    if not effective_state:
        raise Unprocessable("state_code is required", field="state_code")  # SUPER_ADMIN only
    if effective_state not in REGIONS:
        raise NotFound("Unknown state")
    # same GROUP BY district_code pattern as state_overview()'s GROUP BY state_code,
    # scoped the identical way (STATE_ADMIN/DISTRICT_ADMIN's own scope_* branches already
    # restrict every query to their own state regardless of what state_code says)
    ...
    return [
        DistrictOverviewRow(district_code=code, district_name=name, ...)
        for code, name in REGIONS[effective_state]["districts"].items()
    ]
```

For a `STATE_ADMIN`/`DISTRICT_ADMIN` caller, any client-sent `state_code` query param is ignored in
favor of `user.state_code` (same "server derives it, never trusts the client for this" rule as
§4's `GET /api/users` above) — it exists only so a `SUPER_ADMIN` can drill into one state from
spec 17's existing state-wise table. No new `scope_*` helper: this reuses the same three already
in `state_overview()`.

## 5. Access

Same structural call spec 17 §5 made, one rank down:

- §3's six endpoints already work for `STATE_ADMIN` today — no gate changes, so nothing to decide
  there.
- §4's five changes are scoped specifically to admit `STATE_ADMIN` (not `DISTRICT_ADMIN` — see D1).
  `GET /admin/district-overview` reuses the router's existing `ADMIN_ROLES` dependency (so
  `DISTRICT_ADMIN`/`SUPER_ADMIN` can call it too, harmlessly, same precedent `state_overview()`
  already set for itself), but **the new frontend page this spec builds is `STATE_ADMIN`-only.**
- `DISTRICT_ADMIN` keeps today's plain `ExpiryDashboard`, completely unchanged by this spec. A
  district-scoped admin page is real future work (§9), not a decision this spec makes by omission.

## 6. Page contract

### 6.1 Dashboard (`/admin` — today `STATE_ADMIN` and `DISTRICT_ADMIN` share the same
`ExpiryDashboard`; this spec gives `STATE_ADMIN` a richer variant, `DISTRICT_ADMIN` is unaffected)

```
┌ State Admin — Jharkhand ──────────────────────────────────────────┐
│ [Instruments: N] [Applications: N] [Pending: N] [Under verif.: N] │  KPI cards
│ [Certs valid: N] [Expiring: N] [Expired: N]                        │
│ [Active LMOs: N] [Active GATCs: N]                                 │
│                                                                     │
│ Verification overview                                              │
│  [Submitted N] [Document review N] [Deficient N] [Scheduled N]     │  GET /applications/stats
│  [Inspection N] [Approved N] [Rejected N] [Certificate issued N]   │  (already state-scoped)
│                                                                     │
│ District performance                           [table, not a map] │
│  District | Instruments | Pending apps | Certs valid | Certs exp. │  §4's district-overview
│  Dhanbad  | 1            | 1            | 0           | 0          │
│  → View                                                            │
│                                                                     │
│ Recent activity                                   → Audit logs    │
│  5 most recent in-state audit_logs rows (§4's D4 filter)           │
│                                                                     │
│ Quick actions: View applications · View districts · View LMOs ·   │
│                View GATCs · View expiring certs ·                 │
│                Create official account                             │
└─────────────────────────────────────────────────────────────────┘
```

Dropped from the brief's dashboard: "Open enforcement cases" (§2), monthly trend charts (§2), the
India-map precedent doesn't even apply here (the brief's own state dashboard never asked for a map
— it only asked for district rows, which the table above already is).

### 6.2 District management (`/admin/districts`)

One table, `GET /admin/district-overview` (own state, forced). **No bespoke "district detail"
page** — "View District" / "View Applications" / "View LMOs" / "View GATCs" each link to the
existing, already-filterable pages below with `?district_code=` pre-set, rather than inventing a
fifth place these same numbers are computed. Enforcement stats dropped (§2).

### 6.3 Application management (`/admin/applications`)

Same table/columns as spec 17's `/admin/applications` (cloned, not parameterized, matching that
page's own precedent), minus the **State** column (fixed, redundant for a single-state page) and
its state filter (same reason) — just **District**, with a district filter populated from
`REGIONS[own_state].districts`. Filters reuse exactly what `GET /applications` already supports:
`status`, `q`, `district_code`, `sort`. **Not built:** an Instrument-Type or LMO/GATC-assignee
filter — neither parameter exists on `GET /applications` today (`§3`), and adding either is a
real, separate backend change (an instrument-type filter needs a join to `instruments`; an
assignee filter needs one to `inspections`), not a free reuse — flagged for Phase 2 (§9), not
invented here. Row click goes to the existing `/applications/{id}` detail page, unchanged.

### 6.4 Scrutiny monitoring

Not a separate page: `/admin/applications?status=DOCUMENT_REVIEW` (and `DOCUMENTS_DEFICIENT` for
"Deficient/Query") **are** the scrutiny queue, in the real status vocabulary — same reuse
spec 17 §2 already did for the identical brief wording. "Fee Status" is `ApplicationDetail.
payment` (step 12, informational-only, unchanged). "Average Scrutiny Time" dropped from Phase 1
(§2, §9).

### 6.5 LMO management (`/admin/lmo`)

`GET /api/users?role=LM_OFFICER` (§4, now state-forced for `STATE_ADMIN`), same shape spec 17's
LMO directory already defined: name, district, pending/completed cases, active/inactive,
Activate/Deactivate via `PATCH /api/users/{id}` (§4's rank+state check). "Jurisdiction" column is
just district (state is fixed, same reasoning as §6.3).

### 6.6 GATC management (`/admin/gatc`)

`GET /api/organizations?type=GATC` (§4, router-gate-only change — zero service work), identical
shape to spec 17's GATC directory: org name, district, eligible categories, pending/completed
cases, nested authorized-staff table with Activate/Deactivate. No "Principal Officer" column —
same reason spec 17 §6.5 gave (no such column exists on `Organization`).

### 6.7 Assignment & scheduling — monitoring only, no action

The brief's assignment flow (`Application → Instrument Location → District → Jurisdiction →
Eligible LMO/GATC → Assignment`) is exactly spec 15's existing scheduling flow, already run by the
`LM_OFFICER` who schedules. This page shows the result — scheduled date, assigned officer/GATC,
verification mode (`OFFICE_TEST_CENTRE`/`ON_SITE`, spec 14) — already present on
`ApplicationDetail`/`ApplicationOut`, surfaced on the existing `/admin/applications` →
`/applications/{id}` path (§6.3). **No reassignment action** — §2 explains why, mirroring spec 17
§6.2's identical call for Super Admin.

### 6.8 Instrument management (`/admin/instruments`)

`GET /api/instruments`, already state-scoped, already supporting `instrument_type` and
`district_code` filters natively (§3 — this is the one list endpoint that already has *more*
filtering than Applications does). No new backend work; a thin reuse of the existing
`/instruments` list view, reachable from the `STATE_ADMIN` nav.

### 6.9 Certificate management (`/admin/certificates`)

`GET /api/certificates` (§3 — built in spec 17, already open to `STATE_ADMIN`, not
`SUPER_ADMIN`-only), `?status=` filter, links to `/certificates/[id]`. Identical reuse to spec 17
§6.3's own certificates page, one rank down.

### 6.10 Expiry monitoring (`/admin/certificates/expiring-soon`)

This is, literally, today's existing `ExpiryDashboard` — the page a `STATE_ADMIN` already sees at
`/admin` before this spec. No change needed beyond making it reachable as its own sidebar item once
`/admin` itself becomes the richer dashboard (§6.1), matching spec 17's own
`/admin/certificates/expiring-soon` precedent for exactly this reason.

### 6.11 State analytics

Phase 1 is the district-performance table (§6.1/§6.2) plus the existing verification-status chip
row (§6.1) — both already real numbers, not placeholders. Breakdown-by-instrument-type,
breakdown-by-month, and every chart in the brief's §12 are dropped per §2, flagged for Phase 2
(§9), same as spec 17 did for its own (larger) analytics section.

### 6.12 Reports

Dropped (§2) — same reasoning as spec 17 D4.

### 6.13 Notification center

Dropped (§2) — same reasoning as spec 17 §9.

### 6.14 Users (`/admin/users`)

Table: name, email, role (`DISTRICT_ADMIN`/`LM_OFFICER` only, §4), district, active. Actions:
**Create** (`POST /api/users`, role+state-restricted per §4) and **Activate/Deactivate**
(`PATCH /api/users/{id}`, §4). Explicitly not built, same reasons spec 17 §6.6 gave for its own
identical page: editing email/role/district after creation.

### 6.15 Audit logs (`/admin/audit-logs`)

`GET /api/audit-logs`, filtered to the caller's state (§4's D4 recommendation), same table shape
spec 17 §6.7 already defined (timestamp, actor, action, entity type/id, expandable `details`
JSON). Filters: date range, actor, action, entity type.

### 6.16 State settings

Dropped entirely (§2) — not even a read-only stub, since there is no real settings data anywhere
in this app to show for any role.

### 6.17 Sidebar

```
Dashboard
Applications
Instruments
Certificates
  Expiring soon
Districts
LMOs
GATCs
Users
Audit logs
```

Same flat-list pattern `SUPER_ADMIN_NAV` already established (`components/app-shell.tsx`) — one
level shorter (no national-only items), same reasoning spec 17 §6.8 gave for not building a nested
menu component for a single role's page.

## 7. Decisions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Build this for `STATE_ADMIN` only, or also give `DISTRICT_ADMIN` an equivalent page now? | **`STATE_ADMIN` only.** `DISTRICT_ADMIN` keeps today's `ExpiryDashboard`, unchanged | Matches the brief's stated role; the data layer already generalizes to `DISTRICT_ADMIN` for free later (every `scope_*` helper already has that branch too) — same "build the page, not the plumbing, per role" sequencing spec 17 §5/D1 used for `SUPER_ADMIN` |
| D2 | Should `GET /api/users` for a `STATE_ADMIN` caller include `STATE_ADMIN`-role peers in the same state (e.g. a co-administrator)? | **No — `{DISTRICT_ADMIN, LM_OFFICER}` only**, via `ROLE_RANK` (strictly below the caller) | A `STATE_ADMIN` managing another `STATE_ADMIN` is a peer-rank action with no clear ownership story (who can deactivate whom if both outrank each other identically?) — `SUPER_ADMIN` already handles that case today and keeps doing so |
| D3 | On a `state_code` mismatch (client sends one that isn't the `STATE_ADMIN`'s own) in `GET`/`POST /api/users`, reject (`422`) or silently force to the actor's own state? | **Reject.** Silent override is a worse UX failure mode than an explicit error — a form that "worked" but saved to the wrong place is far more dangerous than one that visibly refused | Matches `UserCreate`'s existing fail-loud validation style (unknown state/district → `ValueError` already, not a silent default) |
| D4 | `GET /api/audit-logs` jurisdiction filter: exclude system-actor rows for a `STATE_ADMIN`, or build the harder entity-type join to include them? | **Exclude for Phase 1**, disclosed as a known gap | The entity-type join (resolving a certificate's state through its application) is real, separate work for one audit action (`CERTIFICATE_EXPIRED`) that a `STATE_ADMIN` can already see the *effect* of via the Expiry dashboard (§6.10) — the audit trail gap is cosmetic, not a missing capability |
| D5 | `GET /admin/district-overview`: new endpoint, or extend `state_overview()` with an optional `group_by` param? | **New endpoint.** `StateOverviewRow`/`DistrictOverviewRow` are different shapes (district rows don't need a `state_code`/`state_name` pair the way state rows do) and the two call sites (national state-wise table vs. one state's district-wise table) have different required/optional `state_code` semantics (`SUPER_ADMIN` required to pass one here; irrelevant there) | Forcing one endpoint to serve both would couple two different callers' needs onto one response shape — the same reasoning spec 17 D3 used to keep `gatc/eligible` and the new GATC directory separate |
| D6 | CSV export on these tables? | **Not in Phase 1**, same as spec 17 D4 | Tables are already filterable/searchable on screen |

## 8. Frontend/backend file list (as built)

```
backend:
app/core/roles.py                    unchanged — ROLE_RANK already existed; this step is its
                                      first real consumer (in services/users.py, below)
app/routers/organizations.py         SuperAdmin -> SuperOrStateAdmin (one-line gate widen only)
app/routers/users.py                 SuperAdmin -> SuperOrStateAdmin; list_users() call passes actor
app/routers/audit.py                 SuperAdmin -> SuperOrStateAdmin; list_audit_logs() call passes actor
app/routers/admin.py                 + GET /admin/district-overview (§4)
app/schemas/admin.py                 + DistrictOverviewRow
app/services/organizations.py        unchanged — gatc_directory() was already actor-scoped
app/services/users.py                create_user()/list_users()/set_active() gain the
                                      state+ROLE_RANK checks in §4 (STATE_ADMIN branch);
                                      list_users() gains a required `actor` parameter
app/services/audit.py                list_audit_logs() gains a required `actor` parameter +
                                      the D4 jurisdiction filter (two outer joins)
app/services/admin.py                + district_overview()
tests/test_admin_district_overview.py (new, 9 tests)
tests/test_users.py                  + 13 STATE_ADMIN-scoping tests
tests/test_organizations.py          + 2 STATE_ADMIN-scoping tests
tests/test_audit_logs.py             + 4 STATE_ADMIN-scoping tests
tests/test_rbac.py                   4 existing SUPER_ADMIN-only sweeps widened to
                                      (SUPER_ADMIN, STATE_ADMIN)

frontend:
app/admin/page.tsx                       + STATE_ADMIN -> StateAdminDashboard branch, checked
                                          before the generic ADMIN_ROLES fallback
components/admin/state-admin-dashboard.tsx   (new) §6.1
components/admin/district-overview-table.tsx (new) §6.2, sibling of state-overview-table.tsx
app/admin/districts/page.tsx             (new) §6.2
app/admin/applications/page.tsx          parameterized in place (not cloned): gate widened,
                                          State column/filter hidden for a STATE_ADMIN viewer
app/admin/gatc/page.tsx, app/admin/lmo/page.tsx, app/admin/users/page.tsx,
  app/admin/audit-logs/page.tsx, app/admin/certificates/page.tsx   gate widened to admit
                                          STATE_ADMIN; gatc/lmo/users additionally hide the State
                                          filter for a STATE_ADMIN viewer (§3.5 — a correctness
                                          fix for users/lmo since GET /api/users rejects a
                                          mismatched state_code; UX consistency for gatc, whose
                                          scope_organizations() just ANDs to empty instead)
components/admin/user-create-form.tsx    STATE_ADMIN_ROLE_OPTIONS (drops STATE_ADMIN) + the
                                          State select locked to the creator's own state_code
                                          when the logged-in user is STATE_ADMIN
components/app-shell.tsx                 + STATE_ADMIN_NAV (§6.17), branched before the
                                          generic ADMIN_ROLES fallback
lib/api.ts                               + getDistrictOverview()
lib/types.ts                             + DistrictOverviewRow
```

## 9. Explicitly deferred (recorded, not committed)

- Enforcement Management — no data model, no named legal basis (same as spec 17 §9).
- Notification Center, CSV/PDF report export engine, trend charts (monthly applications/
  verifications, LMO/GATC workload-over-time) — same as spec 17 §9.
- "Average Scrutiny Time" — needs an `application_status_history` timestamp-diff aggregation
  endpoint that doesn't exist.
- Instrument-Type and LMO/GATC-assignee filters on `/admin/applications` — real backend joins,
  not a free reuse of the existing `GET /applications` query params.
- `GET /api/audit-logs`'s system-actor rows (D4) — a known, disclosed gap for Phase 1.
- Editing a user's email/role/jurisdiction after creation (same as spec 17 §6.6/§9).
- Extending this page's data layer to `DISTRICT_ADMIN` (D1) — cheap later (the `scope_*` branches
  already exist), not built now.
- State Settings — no real settings data exists for any role to show.

## 10. Acceptance criteria

- [x] As a `STATE_ADMIN`: dashboard KPIs match `GET /applications/stats` + `GET /admin/
  certificates/stats` exactly for their own state, with zero counts from other states leaking in
  — confirmed both by `tests/test_admin_district_overview.py` and live in the browser (13
  instruments, 10 non-draft applications, matching a direct API call with the same token).
- [x] District-performance table shows every district of the caller's own state (zero-filled where
  empty), never another state's districts — `test_every_district_present_and_zero_filled_with_no_data`,
  confirmed live (all 24 Jharkhand districts rendered, Dhanbad populated, the rest zero).
- [x] `GET /api/users` as `STATE_ADMIN`: returns only `DISTRICT_ADMIN`/`LM_OFFICER` rows from the
  caller's own state; a `state_code` query param for a different state is rejected (`422`); a
  `role=STATE_ADMIN` or `role=SUPER_ADMIN` filter is rejected (`403`) —
  `tests/test_users.py::test_state_admin_list_*`, confirmed live (a Karnataka officer and the
  acting admin's own peers never appeared in `/admin/users` or `/admin/lmo`).
- [x] `POST /api/users` / `PATCH /api/users/{id}` as `STATE_ADMIN`: creating/activating a
  `DISTRICT_ADMIN`/`LM_OFFICER` in-state succeeds; targeting another state, or a `STATE_ADMIN`/
  `SUPER_ADMIN` target, is rejected — `tests/test_users.py::test_state_admin_create_*`/
  `test_state_admin_patch_*`, confirmed live end-to-end (created and then deactivated a real
  `LM_OFFICER` in Dumka through the `/admin/users` UI).
- [x] `GET /api/organizations?type=GATC` as `STATE_ADMIN`: only GATC orgs in the caller's own state
  appear — `tests/test_organizations.py::test_state_admin_sees_only_own_state_gatc_orgs`.
- [x] `GET /api/audit-logs` as `STATE_ADMIN`: only rows whose actor (official or org) resolves to
  the caller's state appear; confirmed against a cross-state fixture —
  `tests/test_audit_logs.py::test_state_admin_*`, confirmed live (a Karnataka business's
  `USER_REGISTERED` row was invisible when filtered by action, while the two in-state ones showed).
- [x] A `DISTRICT_ADMIN` and every non-admin role get `403` on every §4 endpoint change —
  parametrized RBAC sweeps in `tests/test_rbac.py` and `tests/test_admin_district_overview.py`.
- [x] `DISTRICT_ADMIN`'s existing `/admin` page (`ExpiryDashboard`) is provably unchanged by this
  spec — confirmed live in the browser (still renders the plain four-card expiry dashboard and the
  narrower nav); no backend or frontend code path for `DISTRICT_ADMIN` was touched by this spec,
  and there is still no frontend test harness in this repo to pin this automatically.

## 11. Verification record

**Backend** (`pytest`, local `lm_test`): full suite green — 585 passed, zero modifications to any
pre-existing test's assertions beyond the four `test_rbac.py` sweeps this spec deliberately widens
(`SUPER_ADMIN`-only → `(SUPER_ADMIN, STATE_ADMIN)`). New/extended: `tests/test_admin_district_overview.py`
(9 new tests), `tests/test_users.py` (+13), `tests/test_organizations.py` (+2),
`tests/test_audit_logs.py` (+4). `ruff check .` and `ruff format --check .` both clean.

**Frontend** (`tsc --noEmit`, `eslint`/`npm run lint`, `next build`): all clean. `next build`
confirms `/admin/districts` registers as a new static route.

**Manual, in Chrome, against a local `lm_dev` Postgres instance** (not Supabase — `backend/.env`
was overridden to `DATABASE_URL=postgresql+psycopg://localhost/lm_dev`, `STORAGE_BACKEND=memory`,
`EMAIL_BACKEND=memory`, matching this repo's documented local-dev pattern), using the real seeded
`state.jh@lm.demo` / `LmDemo@2026` account (`database/seed/README.md`) plus a hand-added Karnataka
fixture (one `LM_OFFICER` + one `BUSINESS` org/user) created through the real API as a cross-state
isolation control:

- `/admin` rendered `StateAdminDashboard` (not `ExpiryDashboard`/`SuperAdminDashboard`): KPI cards
  matched a direct `curl` with the same token exactly (13 instruments, 10 applications, 1 cert
  valid, 1 expired, 2 active LMOs, 1 active GATC — the Karnataka officer correctly excluded from
  the LMO count); the district-performance table showed all 24 Jharkhand districts, only Dhanbad
  populated; recent activity showed only Jharkhand-actor rows.
- `/admin/districts` rendered the same table as a standalone page.
- `/admin/applications` showed no State column or filter, a District filter scoped to Jharkhand,
  and the subtitle "Every application in your state."
- `/admin/users`: the role filter and the create-account dialog's role dropdown only offered
  `DISTRICT_ADMIN`/`LM_OFFICER` (no `STATE_ADMIN`/`SUPER_ADMIN`); the State select in the create
  dialog was pre-filled with "Jharkhand" and disabled; the district dropdown inside it only listed
  Jharkhand's districts. Created a real `LM_OFFICER` ("Dumka Test Officer") end to end — it
  appeared immediately in the list with district `DUM` — then deactivated it, confirming the
  `Active`/`Inactive` badge flip.
- `/admin/lmo`: 3 Jharkhand officers shown (including the newly created one), the Karnataka
  officer absent, no State filter present.
- `/admin/gatc`: the one Jharkhand GATC org shown, no State filter present.
- `/admin/audit-logs`: filtering by `action=USER_REGISTERED` showed exactly the 2 Jharkhand
  `BUSINESS` registrations and correctly excluded the Karnataka one created for this test.
- **Regression — unaffected roles**, confirmed by logging in as each in turn: `district.dhn@lm.demo`
  (`DISTRICT_ADMIN`) still saw the unchanged plain `ExpiryDashboard` and the narrower
  `[...NAV, {Admin link}]` sidebar; `admin@lm.demo` (`SUPER_ADMIN`) still saw the unchanged
  `SuperAdminDashboard` (national KPIs, e.g. 3 active LMOs — correctly including the Karnataka one
  this time) and the full `/admin/users` table with every role and the State column/filter intact.

**One environment snag, unrelated to the implementation itself**: a frontend `next dev` instance
already running on port 3010 from an earlier session had its `API_ORIGIN` pointed at a different,
stale backend process on port 8010 that predated several specs (confirmed by its `GET /api/users`
returning `405`, meaning no `GET` handler existed yet on that build). Restarted it pointed at the
correct, current backend (port 8000, which was *not* restarted — it already ran with `--reload`)
before verification could proceed.

**Disclosed side effects**: verification created real rows in the local `lm_dev` database (not
Supabase) — `ka.officer@lm.demo` (`LM_OFFICER`, Karnataka), `ka.owner@lm.demo`/"Bengaluru Scales
Co 2" (`BUSINESS`, Karnataka), one extra orphaned "Bengaluru Scales Co" organization row with no
user (created by a direct `INSERT` before the API-driven fixtures replaced that approach), and
`dumka.test.officer@lm.demo` (currently deactivated). None are seed data; no delete-user endpoint
exists in this app to remove them through normal means — same disclosed-not-cleaned-up precedent
spec 17's own verification record used.
