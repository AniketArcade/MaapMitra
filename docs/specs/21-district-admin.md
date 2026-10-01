# Spec 21 — District Admin page

**Status:** Done. Implemented and verified (§11). D1's recommendation (no account creation for
`DISTRICT_ADMIN`) was confirmed by the user before implementation and built as written.
**Build order:** Step 21 (post-MVP addition, on top of steps 1–20)
**Depends on:** Spec 01 (`Role`, `ROLE_RANK`, RBAC), Spec 10 (`ADMIN_ROLES`, `GET /admin/certificates/*`),
Spec 15 (`scope_organizations`, GATC directory), Spec 17 (`GET/POST /api/users`,
`PATCH /api/users/{id}`, `GET /api/audit-logs`, `GET /api/organizations?type=GATC`,
`GET /api/certificates`, `GET /admin/state-overview`), **Spec 18 is this spec's direct
precedent** — same move, one rank further down, and most of this doc exists only to say "same
as spec 18, substitute DISTRICT_ADMIN for STATE_ADMIN and district_code for state_code" with the
handful of places that genuinely differ called out explicitly (§2, §7).
**Source input:** a pasted "District Admin — Frontend Specification" brief (23 sections: largely
the same shape as the State Admin brief spec 18 already triaged — dashboard, application/LMO/
GATC/instrument/certificate management, assignment monitoring, scheduling, expiry/re-verification
monitoring, enforcement, analytics, LMO/GATC performance, reports, notifications, audit logs,
users, district profile, sidebar, responsibilities, access scope).

## 1. Goal

Root `CLAUDE.md`'s role table puts `DISTRICT_ADMIN` directly below `STATE_ADMIN`. Today a
`DISTRICT_ADMIN` who logs in gets the plain `ExpiryDashboard` from step 10 (four certificate-count
cards + an expiring-soon table) — the **same** page a bare `ADMIN_ROLES` fallback has always given
it, unchanged by spec 17 or spec 18 (both of which explicitly scoped themselves to one role only
and left `DISTRICT_ADMIN` on this fallback — spec 17 D1, spec 18 D1). Meanwhile every `scope_*`
helper in `app/services/scoping.py` **already has a `DISTRICT_ADMIN` branch**, and has since step
1 — it's bundled with `LM_OFFICER` in every one of them (`scope_instruments`,
`scope_applications`, `scope_organizations`), scoped to `state_code` **and** `district_code`, i.e.
already narrower than what `STATE_ADMIN` gets. `DISTRICT_ADMIN` is also already a member of
`ADMIN_ROLES` (`core/roles.py`) and therefore already allowed to call `GET /admin/certificates/
{stats,expiring-soon}` and `GET /admin/district-overview` — it just has no page that calls them
beyond the generic four-card dashboard. This spec is the same move spec 17 made for `SUPER_ADMIN`
and spec 18 made for `STATE_ADMIN`, applied to the role that was already closest to ready: build
the page, not the plumbing, because almost all of the plumbing exists.

Demo relevance: a `DISTRICT_ADMIN` for Dhanbad, logging in, would see the seed data's entire demo
story (ABC Traders, `XYZ12345`, `CERT-2026-000123`) through scoping that already exists today,
with zero backend changes needed for the read-only surface.

## 2. Why this spec is narrower than the pasted brief — and where it differs from spec 18, not just repeats it

Most of spec 18 §2's table applies verbatim, one rank down (enforcement, notifications, report
export, trend charts, dynamic region config, district/LMO/GATC settings, time-slot scheduling,
"scrutiny" as a separate screen, "Average Scrutiny Time", mid-flow reassignment). Not re-derived
here — see spec 18 §2 for the reasoning on each; it's unchanged by rank.

What's genuinely different about this brief, not just a copy of spec 18's:

| Brief asks for | Difference from spec 18's State Admin brief | What this spec does |
|---|---|---|
| §19 User Management actions: "View User, View Role, View Office, **Activate/Deactivate where permitted**, View Activity" | Spec 18's State Admin brief implied account *creation* (its §19 was resolved as Create + Activate/Deactivate, spec 18 §6.14). This brief's own §19 **never lists a Create action for District Admin** anywhere — not here, and not in §5's LMO Management ("Manage status where permitted" only). That's a real, consistent signal in the source text, not an omission to paper over | **No account creation for `DISTRICT_ADMIN` in Phase 1** (D1 below) — `POST /api/users` stays `SUPER_ADMIN`/`STATE_ADMIN`-only, untouched. `DISTRICT_ADMIN` gets list + Activate/Deactivate of `LM_OFFICER` accounts in its own district, nothing more |
| §2 "District-wise KPIs" / §14 "District Analytics" | A `STATE_ADMIN` needed a breakdown **across** several districts (spec 18's `DistrictOverviewTable`, one row per district). A `DISTRICT_ADMIN` **is** one district — there's nothing to break down | No new table. `GET /admin/district-overview` already returns one row per district of the caller's own state, correctly zero-filled for every district but the caller's own (scoping already floors every underlying query to `state_code` **and** `district_code` — a `DISTRICT_ADMIN` physically cannot see another district's real numbers through this endpoint even unmodified). The dashboard renders **the caller's own row only**, as a compact "District profile" summary (§6.1, §6.20) — not the full 20-ish-district table a `STATE_ADMIN` sees. Zero backend change; a client-side filter on an endpoint that already works |
| §6 GATC Management / §5 LMO Management: "Workload", "Pass/Fail Statistics" | Identical ask to spec 18 §6.5/§6.6, just at district scope | Same reuse, `GET /api/users?role=LM_OFFICER` / `GET /api/organizations?type=GATC` — see §4, since neither endpoint admits `DISTRICT_ADMIN` yet (only `SUPER_ADMIN`/`STATE_ADMIN` do, as of spec 18) |
| §13 Enforcement Monitoring | Same gap as spec 17/18 §2 | Dropped, same reasoning |
| §20 District Profile: "Number of LMOs", "Number of GATCs" | New wording not in the State Admin brief, but trivially the `total` field `GET /api/users?role=LM_OFFICER&is_active=true` / `GET /api/organizations?type=GATC&is_active=true` already return as `Page.total` | No new endpoint — the dashboard's existing KPI cards (§6.1) already compute this count; the profile section just reuses the same number, not a second query |

Everything else — application/instrument/certificate monitoring, expiry monitoring, scheduling
visibility, re-verification monitoring, audit logs — maps onto data this system already scopes
to `DISTRICT_ADMIN` today, the same way spec 18 §3 found for `STATE_ADMIN`.

## 3. What this reuses outright (no backend work at all)

Unlike spec 18 §3, which had to point out that `STATE_ADMIN` was *already* admitted to these
endpoints (a fact worth stating because it wasn't obvious), `DISTRICT_ADMIN`'s starting position is
even further along: it's already in **every** role list below, including the ones spec 18 itself
had to widen for `STATE_ADMIN`'s sake elsewhere in this codebase.

| Section | Endpoint | Why `DISTRICT_ADMIN` already works |
|---|---|---|
| Applications list/search/filter/stats | `GET /api/applications`, `GET /api/applications/stats` | `routers/applications.py` already lists `Role.DISTRICT_ADMIN`; `scope_applications`'s `(DISTRICT_ADMIN, LM_OFFICER)` branch already restricts to the caller's own state **and** district |
| Application detail, checklist, documents | `GET /api/applications/{id}`, `GET /api/documents/...` | `routers/documents.py` already lists `Role.DISTRICT_ADMIN` as a reader |
| Instruments list/search | `GET /api/instruments` | `routers/instruments.py` already lists `Role.DISTRICT_ADMIN`; `scope_instruments` already restricts to state+district |
| Certificate list/detail/PDF | `GET /api/certificates`, `GET /api/certificates/{id}`, `.../pdf` | `routers/certificates.py` already lists `Role.DISTRICT_ADMIN`; chains through `scope_applications` |
| Certificate stats, expiring-soon | `GET /admin/certificates/stats`, `GET /admin/certificates/expiring-soon` | `routers/admin.py`'s `Admin = require_roles(*ADMIN_ROLES)` already includes `DISTRICT_ADMIN` — **this is today's actual `ExpiryDashboard` data**, already correct, just not presented as anything richer |
| District-wise overview (own district populated, every other district in-state zero-filled) | `GET /admin/district-overview` | Same `Admin` dependency; `services/admin.py: district_overview()` already forces `state_code` to `user.state_code` for any non-`SUPER_ADMIN` caller, and the three `scope_*` calls inside it already floor every row to the caller's own district for a `DISTRICT_ADMIN` caller — **zero code touches this function** |

No router change, no service change, no migration for this section — purely new frontend (§6).

## 4. New backend surface needed

The only real gap, same shape spec 18 §4 closed for `STATE_ADMIN` one rank up: `users`,
`organizations` (GATC directory) and `audit_logs` are not reachable by `DISTRICT_ADMIN` today,
because — unlike `applications`/`instruments`/`certificates` — their role gates were written
narrowly (`SuperOrStateAdmin`) rather than against `ADMIN_ROLES`, back when only `SUPER_ADMIN`
(step 17) and then `STATE_ADMIN` (step 18) needed them.

| Endpoint | Change | New rule for a `DISTRICT_ADMIN` caller |
|---|---|---|
| `GET /api/organizations?type=GATC` | Router gate widened `SuperOrStateAdmin → Admin` (`require_roles(*ADMIN_ROLES)`, the same constant `routers/admin.py` already uses) — **zero service change** | `scope_organizations()` already has the `(DISTRICT_ADMIN, LM_OFFICER)` branch (state **and** district); this is that branch's first real caller |
| `GET /api/users` | Router gate widened to `Admin` for the `GET` only (not `POST` — see D1). `list_users()` gains a `DISTRICT_ADMIN` branch | `state_code`/`district_code` both forced to the actor's own (a client-sent mismatch on either → `422`, same D3 "reject, never silently override" rule spec 18 set). An explicit `role` filter at the actor's own rank or above (`ROLE_RANK[role] >= ROLE_RANK[DISTRICT_ADMIN]`, i.e. anything but `LM_OFFICER`) → `403`. Omitting `role` narrows the base query to `{LM_OFFICER}` only — the single rank strictly below `DISTRICT_ADMIN` that `OFFICIAL_ROLES` contains |
| `PATCH /api/users/{id}` | Router gate widened to `Admin`. `set_active()` gains a `DISTRICT_ADMIN` branch | Target must have `state_code == actor.state_code` **and** `district_code == actor.district_code` **and** `ROLE_RANK[target.role] < ROLE_RANK[actor.role]` (i.e. `LM_OFFICER` only) — `403` otherwise. Existing unconditional self-deactivation `409` guard is unchanged and still checked first |
| `POST /api/users` | **Not widened** (D1) | `DISTRICT_ADMIN` never reaches `create_user()` — the router dependency stays `SuperOrStateAdmin`, so this is a `403` at the dependency layer, same as every other non-admitted role, no service-level check needed |
| `GET /api/audit-logs` | Router gate widened to `Admin`. `list_audit_logs()` gains a `DISTRICT_ADMIN` branch | See the dedicated subsection below — the district-level tightening of spec 18's own D4 filter |
| `GET /admin/district-overview` | **No change at all** | Already correct for `DISTRICT_ADMIN` today (§3) |

### `GET /api/audit-logs` — tightening spec 18's own filter one level further

Spec 18 §4 already solved "no jurisdiction column on `audit_logs`" for `STATE_ADMIN` with two
outer joins (an official actor's own `users.state_code`, or an org actor's
`users.organization_id → organizations.state_code`), OR'd together, excluding system-actor rows
(a disclosed Phase-1 gap, not silent). This spec's `DISTRICT_ADMIN` branch reuses the exact same
two joins and simply **ANDs a district match onto each side** instead of checking state alone:

```python
if actor.role == Role.DISTRICT_ADMIN:
    stmt = stmt.outerjoin(Organization, User.organization_id == Organization.id).where(
        or_(
            and_(User.state_code == actor.state_code, User.district_code == actor.district_code),
            and_(
                Organization.state_code == actor.state_code,
                Organization.district_code == actor.district_code,
            ),
        )
    )
```

Same disclosed gap as spec 18 D4, now additionally narrowed: a `DISTRICT_ADMIN` sees neither
system-actor rows (`CERTIFICATE_EXPIRED`) nor another district's rows in their own state — strict
district isolation, consistent with root `CLAUDE.md`'s "org isolation is absolute" framing applied
to jurisdiction instead of organization.

## 5. Access

- §3's six endpoints already admit `DISTRICT_ADMIN` today — no gate changes.
- §4's three gate widenings use the existing `ADMIN_ROLES` constant verbatim (it already **is**
  `{SUPER_ADMIN, STATE_ADMIN, DISTRICT_ADMIN}` — no new frozenset to define), so `routers/users.py`,
  `routers/organizations.py` and `routers/audit.py` each gain a second `Admin` dependency alongside
  their existing `SuperOrStateAdmin` (kept, for `POST /api/users` only — D1).
- `SUPER_ADMIN`/`STATE_ADMIN` behavior on every one of these endpoints is **completely unchanged**
  — widening a role list to add a third, lower-ranked role never alters what a higher-ranked caller
  already sees, the same non-interference spec 18 §4/§10 confirmed when it added `STATE_ADMIN`
  alongside `SUPER_ADMIN`.
- `LM_OFFICER`/`GATC`/`BUSINESS` are unaffected — none of them were ever admitted to this surface
  and none become admitted by this spec.

## 6. Page contract

### 6.1 Dashboard (`/admin` — today `DISTRICT_ADMIN` sees the plain `ExpiryDashboard`; this spec
gives it the richer variant `STATE_ADMIN` already has, one rank down)

```
┌ District Admin — Dhanbad, Jharkhand ──────────────────────────────┐
│ [Instruments: N] [Applications: N] [Pending: N] [Under verif.: N] │  GET /applications/stats
│ [Certs valid: N] [Expiring: N] [Expired: N]                        │  (already district-scoped)
│ [Active LMOs: N] [Active GATCs: N]                                 │  §4's GET /users?role=
│                                                                     │  LM_OFFICER&is_active=true /
│                                                                     │  GET /organizations?type=
│                                                                     │  GATC&is_active=true .total
│ Verification overview                                              │
│  [Submitted N] [Document review N] [Deficient N] [Scheduled N]     │
│  [Inspection N] [Approved N] [Rejected N] [Certificate issued N]   │
│                                                                     │
│ District profile                              [one row, not a table]
│  District: Dhanbad (DHN) · State: Jharkhand · LMOs: N · GATCs: N  │  §2's table — own row of
│  Instruments: N · Applications: N · Certs valid: N · expired: N   │  GET /admin/district-overview
│                                                                     │
│ Recent activity                                   → Audit logs    │
│  5 most recent in-district audit_logs rows (§4's district filter) │
│                                                                     │
│ Quick actions: View applications · View LMOs · View GATCs ·       │
│                View expiring certs · View audit logs               │
└─────────────────────────────────────────────────────────────────┘
```

Dropped from the brief's dashboard: "Open enforcement cases" (§2), every monthly trend chart (§2).
No "Create official account" quick action — D1.

### 6.2 Application management (`/admin/applications`)

Reuses spec 18's already-parameterized `/admin/applications` page (§6.3 there), gated open one
more rank: for a `DISTRICT_ADMIN` viewer, **both** the State **and** District columns/filters are
hidden (not just State, as for `STATE_ADMIN`) — both are fixed for this role, same reasoning spec
18 used to hide State alone for `STATE_ADMIN`. Subtitle: "Every application in your district."
Row click → existing `/applications/{id}`, unchanged. Not built, same as spec 18: Instrument-Type
or LMO/GATC-assignee filters (§2's table / spec 18 §2 — real new joins, not a free reuse).

### 6.3 Scrutiny monitoring

Not a separate page, same as spec 18 §6.4: `/admin/applications?status=DOCUMENT_REVIEW` /
`?status=DOCUMENTS_DEFICIENT` **are** the scrutiny queue in the real status vocabulary. "Average
Scrutiny Time" dropped (§2).

### 6.4 LMO management (`/admin/lmo`)

`GET /api/users?role=LM_OFFICER` (§4, now district-forced for `DISTRICT_ADMIN`), same shape spec
18 §6.5 already defined: name, pending/completed cases, active/inactive, Activate/Deactivate via
`PATCH /api/users/{id}` (§4's rank+state+district check). No District column (fixed, same
reasoning as §6.2) — unlike spec 18's `/admin/lmo`, which still needed one (a state spans several
districts).

### 6.5 GATC management (`/admin/gatc`)

`GET /api/organizations?type=GATC` (§4, router-gate-only change), identical shape to spec 18
§6.6: org name, eligible categories, pending/completed cases, nested per-user table with
Activate/Deactivate. No State or District column (both fixed). Root `CLAUDE.md`'s rule stands
unchanged here too: **District Admin does not create a GATC** — no create action exists on this
page for any admin role today, so there's nothing to additionally restrict.

### 6.6 Assignment & scheduling — monitoring only, no action

Same as spec 18 §6.7: scheduling is the routing `LM_OFFICER`'s job (spec 15); this page only shows
the result (scheduled date, assigned officer/GATC, verification mode) already on
`ApplicationDetail`, reached via §6.2. No reassignment action.

### 6.7 Instrument management (`/admin/instruments`)

`GET /api/instruments`, already district-scoped (§3), already supporting `instrument_type` —
reuse of the existing `/instruments` list view, same as spec 18 §6.8.

### 6.8 Certificate management (`/admin/certificates`)

`GET /api/certificates` (§3, already open to `DISTRICT_ADMIN`), `?status=` filter, links to
`/certificates/[id]`. Identical reuse to spec 18 §6.9, one rank down.

### 6.9 Expiry monitoring (`/admin/certificates/expiring-soon`)

Today's existing `ExpiryDashboard` — the page `DISTRICT_ADMIN` already sees at `/admin` before
this spec. Same treatment as spec 18 §6.10: becomes reachable as its own sidebar item once `/admin`
itself becomes the richer dashboard (§6.1).

### 6.10 Re-verification monitoring

Not a separate page or status: `ApplicationType.RE_VERIFICATION` already flows through the
identical lifecycle visible in §6.2/§6.8 — same conclusion spec 19 reached for `LM_OFFICER`'s own
copy of this brief section.

### 6.11 District analytics / LMO-GATC performance

Phase 1 is §6.1's KPI cards and verification-overview chip row — both real numbers already, no
placeholders. Every chart, and a dedicated "LMO vs GATC performance" comparison view beyond the
two directory pages (§6.4/§6.5) already show, is dropped per §2, flagged for Phase 2 (§9).

### 6.12 Reports

Dropped (§2) — same reasoning as spec 17 D4 / spec 18 §6.12.

### 6.13 Notification center

Dropped (§2) — same reasoning as spec 17 §9 / spec 18 §6.13.

### 6.14 Users (`/admin/users`)

Table: name, email, role (`LM_OFFICER` only — the single role `DISTRICT_ADMIN` may ever see or
touch here, per §4), active. Action: **Activate/Deactivate** only (`PATCH /api/users/{id}`, §4).
**No Create button** — D1: this role does not create accounts in Phase 1. Role filter either
hidden or fixed to `LM_OFFICER` (nothing else is ever returned for this caller, per §4's implicit
narrowing).

### 6.15 Audit logs (`/admin/audit-logs`)

`GET /api/audit-logs`, filtered to the caller's state **and** district (§4's district-tightened
filter), same table shape spec 17 §6.7 / spec 18 §6.15 already defined.

### 6.16 District profile

Not a standalone page — folded into the dashboard (§6.1) as the "District profile" row, since
there is exactly one district to show and a dedicated page for a single row of already-visible
data would be a wasted click, same reasoning spec 18 §6.2 used to avoid a bespoke district-detail
page.

### 6.17 Sidebar

```
Dashboard
Applications
Instruments
Certificates
  Expiring soon
LMOs
GATCs
Users
Audit logs
Profile
```

One rank narrower than `STATE_ADMIN_NAV` (spec 18 §6.17): no "Districts" link — there's only one
district to show and it's already the dashboard's own profile row (§6.16), so a separate drill-down
list would have exactly one entry, itself.

## 7. Decisions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Should `DISTRICT_ADMIN` create `LM_OFFICER` accounts (`POST /api/users`), the way `STATE_ADMIN` creates `DISTRICT_ADMIN`/`LM_OFFICER` accounts (spec 18)? | **No, not in Phase 1.** `POST /api/users` stays `SUPER_ADMIN`/`STATE_ADMIN`-only | The source brief's own §19 (User Management) and §5 (LMO Management) actions list View/Activate-Deactivate/View-Activity for this role but **never** a Create action anywhere — unlike the State Admin brief spec 18 triaged, which did carry that implication and was built accordingly. Treating an absent action as an oversight would be inventing a permission the brief doesn't ask for; if wanted later, it's a small, isolated addition (one more `elif actor.role == Role.DISTRICT_ADMIN` branch in `create_user()`, mirroring spec 18's `STATE_ADMIN_CREATABLE_ROLES` pattern with `{Role.LM_OFFICER}` only) |
| D2 | Should the dashboard show the full `GET /admin/district-overview` table (every district of the state, zero-filled except the caller's own), or just the caller's own row? | **Own row only**, as a "District profile" summary (§6.1/§6.16) | A table of ~20 zero rows and one real one reads as "no data," not "not your jurisdiction" — confusing, even though nothing leaks (every other district's row is genuinely zero through this caller's own scoping, not merely hidden). One clear profile row is the honest presentation of what this caller can actually see |
| D3 | `GET /api/users`/`PATCH /api/users/{id}` for `DISTRICT_ADMIN`: reject a mismatched `state_code`/`district_code` (`422`/`403`), or silently force to the actor's own? | **Reject**, same as spec 18 D3 | Consistency with the identical rule one rank up; a form that "worked" but queried/targeted the wrong jurisdiction is a worse failure mode than a visible error |
| D4 | `GET /api/audit-logs` jurisdiction filter: narrow to district, or leave `DISTRICT_ADMIN` seeing the whole state (spec 18's `STATE_ADMIN` filter, unmodified)? | **Narrow to district** (§4) | Root `CLAUDE.md`'s "org isolation is absolute" principle, applied to jurisdiction: a `DISTRICT_ADMIN` seeing another district's audit trail in the same state would be a real, avoidable visibility leak, not a cosmetic gap like the system-actor exclusion both ranks already share |
| D5 | `GET /admin/district-overview`: extend/reuse as-is (§3), or build a dedicated single-district summary endpoint? | **Reuse as-is**, filtered client-side to the caller's own row | The endpoint already returns exactly the right, already-scoped numbers for the caller's own district; a new endpoint would duplicate `district_overview()`'s three-query pattern for a strict subset of what it already computes |

## 8. Frontend/backend file list (as built)

```
backend:
app/routers/users.py          GET/PATCH gain a second `Admin = require_roles(*ADMIN_ROLES)`
                               dependency alongside the existing SuperOrStateAdmin (kept, POST only)
app/routers/organizations.py  SuperOrStateAdmin -> Admin (require_roles(*ADMIN_ROLES))
app/routers/audit.py          SuperOrStateAdmin -> Admin (require_roles(*ADMIN_ROLES))
app/services/users.py         list_users()/set_active() gain a DISTRICT_ADMIN branch (state +
                               district forced/checked, role narrowed to {LM_OFFICER});
                               create_user() unchanged (D1)
app/services/audit.py         list_audit_logs() gains a DISTRICT_ADMIN branch (state+district
                               AND'd on both the official-actor and org-actor join, §4)
app/services/admin.py         unchanged — district_overview() already correct (§3)
app/services/organizations.py unchanged — gatc_directory() already correct (§3)
tests/test_users.py           + DISTRICT_ADMIN-scoping tests (list/patch; POST stays 403)
tests/test_organizations.py   + DISTRICT_ADMIN-scoping tests
tests/test_audit_logs.py      + DISTRICT_ADMIN district-isolation tests (same-state,
                               different-district rows excluded)
tests/test_rbac.py            relevant SUPER_ADMIN/STATE_ADMIN-only sweeps widened to include
                               DISTRICT_ADMIN where §4 now admits it; POST /api/users sweep
                               stays unchanged (D1)

frontend:
app/admin/page.tsx                 + DISTRICT_ADMIN -> DistrictAdminDashboard branch, checked
                                    before the generic ADMIN_ROLES fallback (mirrors spec 18's
                                    STATE_ADMIN branch, which stays above this one unchanged)
components/admin/district-admin-dashboard.tsx   (new) §6.1 — reuses GET /admin/district-overview
                                    filtered to the caller's own district_code row, plus the same
                                    stats/certificate-stats calls state-admin-dashboard.tsx uses
app/admin/applications/page.tsx    further parameterized (not re-cloned): State column/filter
                                    already hidden for STATE_ADMIN (spec 18); District column/
                                    filter now also hidden for a DISTRICT_ADMIN viewer
app/admin/lmo/page.tsx, app/admin/gatc/page.tsx, app/admin/users/page.tsx,
  app/admin/audit-logs/page.tsx, app/admin/certificates/page.tsx   gate widened to admit
                                    DISTRICT_ADMIN; lmo/gatc/users additionally hide the District
                                    filter/column (already hiding State since spec 18) for a
                                    DISTRICT_ADMIN viewer
components/admin/user-create-form.tsx   unchanged — DISTRICT_ADMIN never reaches this dialog (D1,
                                    no Create button rendered for this role on /admin/users)
components/app-shell.tsx           + DISTRICT_ADMIN_NAV (§6.17), branched before the generic
                                    ADMIN_ROLES fallback — no role falls through to it anymore
lib/api.ts, lib/types.ts           unchanged — reuses getDistrictOverview()/DistrictOverviewRow
                                    from spec 18 as-is
```

## 9. Explicitly deferred (recorded, not committed)

- Enforcement Management, Notification Center, CSV/PDF report export, trend charts — same as
  spec 17/18 §9.
- "Average Scrutiny Time" — same unresolved aggregation gap as spec 18 §9.
- Instrument-Type and LMO/GATC-assignee filters on `/admin/applications` — real new joins.
- `GET /api/audit-logs`'s system-actor rows — same disclosed Phase-1 gap as spec 18 D4, now also
  excluding other-district rows (D4).
- `POST /api/users` for `DISTRICT_ADMIN` (D1) — straightforward to add later if the product
  decision changes; deliberately not built now because the source brief doesn't ask for it.
- Editing a user's email/role/jurisdiction after creation — same as spec 17/18.
- A dedicated LMO-vs-GATC performance comparison view beyond the two existing directories.

## 10. Acceptance criteria

- [x] As a `DISTRICT_ADMIN`: dashboard KPIs match `GET /applications/stats` + `GET /admin/
  certificates/stats` exactly for their own district, with zero counts from other districts (even
  in the same state) leaking in — confirmed live (`district.dhn@lm.demo`: 13 instruments, 10
  applications, 1 cert valid, 1 expired, 2 active LMOs, 1 active GATC) and by
  `tests/test_admin_district_overview.py::test_district_admin_other_districts_zero_filled`.
- [x] District profile row shows the caller's own district's real numbers; `GET /admin/
  district-overview`'s other rows for the same state are present in the raw response (zero-filled)
  but never rendered as if they were additional jurisdictions to browse (D2) — confirmed live
  (Dhanbad populated, every other Jharkhand district absent from the rendered profile).
- [x] `GET /api/users` as `DISTRICT_ADMIN`: returns only `LM_OFFICER` rows from the caller's own
  state **and** district; a mismatched `state_code` or `district_code` query param is rejected
  (`422`); a `role` filter for anything but `LM_OFFICER` is rejected (`403`) —
  `tests/test_users.py::test_district_admin_list_*`, confirmed live (a Dumka officer and a
  Karnataka officer both absent from `/admin/users`/`/admin/lmo`).
- [x] `POST /api/users` as `DISTRICT_ADMIN` → `403` (D1) —
  `tests/test_users.py::test_district_admin_create_is_403`, confirmed live (no Create button
  renders on `/admin/users` for this role).
- [x] `PATCH /api/users/{id}` as `DISTRICT_ADMIN`: activating/deactivating an in-district
  `LM_OFFICER` succeeds; targeting another district (same state), another state, or any
  rank ≥ `DISTRICT_ADMIN` → `403` — `tests/test_users.py::test_district_admin_patch_*`, confirmed
  live end-to-end (deactivated and reactivated `officer.dhn@lm.demo` through `/admin/lmo`).
- [x] `GET /api/organizations?type=GATC` as `DISTRICT_ADMIN`: only GATC orgs in the caller's own
  district appear — `tests/test_organizations.py::test_district_admin_sees_only_own_district_gatc_orgs`,
  confirmed live (one Dhanbad GATC centre shown, no state/district columns).
- [x] `GET /api/audit-logs` as `DISTRICT_ADMIN`: only rows whose actor (official or org) resolves
  to the caller's own district appear — confirmed against a same-state, different-district
  fixture, `tests/test_audit_logs.py::test_district_admin_*`, confirmed live (only Dhanbad-actor
  rows shown; the Dumka and Karnataka officers' own rows excluded).
- [x] `STATE_ADMIN` and `SUPER_ADMIN` behavior on every §4 endpoint is unchanged by this spec
  (regression) — confirmed live: `state.jh@lm.demo` still sees the full district-wise table, the
  Create button, and the unrestricted role/District filters; `admin@lm.demo` still sees the
  national dashboard with all 3 active LMOs (Karnataka included).
- [x] `/admin/applications`, `/admin/lmo`, `/admin/gatc`, `/admin/users` each hide both State and
  District columns/filters for a `DISTRICT_ADMIN` viewer (both fixed) — confirmed live on all
  four pages.

## 11. Verification record

**Backend** (`pytest`, local `lm_test`): full suite green — 615 passed (up from 585 after spec
18), zero modifications to any pre-existing test's assertions beyond the four `test_rbac.py`
sweeps this spec deliberately widens (`(SUPER_ADMIN, STATE_ADMIN)` → `(SUPER_ADMIN, STATE_ADMIN,
DISTRICT_ADMIN)`; the `POST /api/users` sweep is untouched, proving D1 as a side effect). New:
11 tests in `tests/test_users.py`, 2 in `tests/test_organizations.py`, 4 in
`tests/test_audit_logs.py`, 1 in `tests/test_admin_district_overview.py`. `ruff check .` and
`ruff format --check .` both clean.

**Frontend** (`npm run lint`, `npx tsc --noEmit`, `npm run build`): all clean. `next build`'s
route list is unchanged (no new route — `/admin` is parameterized in place, not cloned).

**Manual, in Chrome, against a local `lm_dev` Postgres instance** (not Supabase — backend run
with `DATABASE_URL=postgresql+psycopg://localhost/lm_dev`, `STORAGE_BACKEND=memory`,
`EMAIL_BACKEND=memory`), using the real seeded `district.dhn@lm.demo` / `LmDemo@2026` account
(Jharkhand/Dhanbad) plus two pre-existing fixtures already present in `lm_dev` from earlier
spec-verification sessions — `dumka.test.officer@lm.demo` (`LM_OFFICER`, Jharkhand/Dumka — a
same-state, different-district control) and `ka.officer@lm.demo` (`LM_OFFICER`, Karnataka — a
cross-state control):

- Logging in via the Official Login → District Admin card landed on `/admin` rendering
  `DistrictAdminDashboard` (confirmed by the sidebar's new `DISTRICT_ADMIN_NAV`, distinct from the
  generic `ADMIN_ROLES` fallback): heading "District Admin — Dhanbad, Jharkhand", KPI cards (13
  instruments, 10 applications, 1 cert valid, 0 expiring, 1 expired, 2 active LMOs, 1 active
  GATC), a "District profile" row (not a table) showing Dhanbad's own numbers, and "Recent
  activity" showing only Dhanbad-actor rows (the district admin itself and the in-district ABC
  Traders business) — no Karnataka or Dumka rows, no "Create official account"/"View districts"
  quick actions.
- `/admin/applications`: subtitle "Every application in your district," no State or District
  column or filter — only Search and Status.
- `/admin/lmo`: 2 officers shown (the in-district `officer.dhn@lm.demo` and a disposable test
  fixture), the Dumka and Karnataka officers both absent, no State/District filters. Deactivated
  and reactivated `officer.dhn@lm.demo` from this page — both PATCHes succeeded and the badge
  flipped correctly each time.
- `/admin/gatc`: the one Dhanbad GATC organization shown, no state/district filters, no per-card
  location line.
- `/admin/users`: role filter offered only "All roles"/"LM Officer" (no District Admin/State
  Admin/Super Admin options); **no Create official account button rendered at all** (D1); no
  State/District columns.
- `/admin/audit-logs`: every row's actor was a Dhanbad-district user — confirmed the Dumka and
  Karnataka officers' own `LOGIN_SUCCEEDED`/status-change rows never appeared.
- `/admin/districts` → "You don't have access to this page." (unchanged, `STATE_ADMIN`-only).
- Direct API checks (`curl`, same token as the browser session) before the UI pass: `GET
  /api/users` returned only in-district officers; `?state_code=KA` and `?district_code=DUM` both
  `422`; `POST /api/users` → `403`; `PATCH` on the Dumka and Karnataka officers both → `403 "Cannot
  manage this account"`; `GET /api/organizations?type=GATC` returned only the Dhanbad centre; `GET
  /admin/district-overview` returned Dhanbad populated and every other Jharkhand district
  genuinely zero.
- **Regression — unaffected roles**, confirmed by logging in as each in turn: `state.jh@lm.demo`
  (`STATE_ADMIN`) still saw the unchanged `StateAdminDashboard` (district-wise table including the
  Dhanbad district admin's own row, Create button present, District filter/column intact) and
  `/admin/users` still listed all 4 in-state officials including `district.dhn@lm.demo` itself;
  `admin@lm.demo` (`SUPER_ADMIN`) still saw the unchanged national dashboard with 3 active LMOs
  (Karnataka correctly included this time).

**Disclosed side effects**: none new — verification reused pre-existing `lm_dev` fixtures
(`dumka.test.officer@lm.demo`, `ka.officer@lm.demo`) left over from earlier specs' own manual
verification, and the one stateful action taken (deactivate/reactivate `officer.dhn@lm.demo`) was
restored to its original `is_active=true` state before finishing.
