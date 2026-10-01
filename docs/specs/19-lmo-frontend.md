# Spec 19 — LMO (LM_OFFICER) frontend

**Status:** Done. Implemented and verified (§11). §7's Decisions (D1–D5) were accepted as written.
**Build order:** Step 19 (post-MVP addition, on top of steps 1–18)
**Depends on:** Spec 05 (officer dashboard — the thing this spec extends, not replaces), Spec 06
(field inspection checklist/measurements), Spec 07 (approve/reject), Spec 08 (certificate
issuance), Spec 11 (document review checklist — this *is* "Scrutiny," §4), Spec 14
(transportability/verification mode), Spec 15 (GATC eligibility — scheduling already routes
here), Spec 10 (expiry job/admin certificate stats — extended here to admit `LM_OFFICER`)
**Source input:** a pasted "LMO — Frontend Specification" brief (28 sections: dashboard, my
applications, application details, scrutiny, query/deficiency management, scheduling, calendar,
verification workflow, field verification, digital inspection form, verification result,
pass/fail verification, certificate management, QR verification, instrument management,
verification history, expiry monitoring, re-verification, location/field support, documents,
notifications, reports, audit trail, profile, sidebar, responsibilities, access scope). That
brief is the starting point, not its contents verbatim — §2 explains why.

## 1. Goal

Unlike specs 17/18, `LM_OFFICER` is not a new role being onboarded — it's the single most-built
role in this codebase (specs 01, 03, 05, 06, 07, 08, 11, 14, 15 are all, in large part, about
`LM_OFFICER`). Read against what's actually built, **this brief mostly describes the existing
officer dashboard/applications/field-inspection flow in different words**, not a gap to fill. This
spec's real job is narrower than specs 17/18's: audit the brief section-by-section against what
exists, name the handful of genuine gaps, and reuse the existing vocabulary/endpoints everywhere
else — never build a second, parallel "LMO workflow" next to the one already live.

The two real, cheap gaps this spec actually proposes building (§4): `LM_OFFICER` currently has
**no access to expiry monitoring** (`GET /admin/certificates/*` is `ADMIN_ROLES`-only today,
despite `scope_certificates` already resolving correctly for an officer) and **no certificate
list page** of their own (`GET /api/certificates` already admits `LM_OFFICER` — spec 17's Reader
role set — but no officer-facing frontend page calls it). Both are one-line backend role-gate
changes plus a small frontend page/section, not new concepts.

## 2. Why this spec is narrower than the pasted brief

Same reasoning spec 17 §2 / spec 18 §2 already established, applied to a brief describing a role
that's mostly already built:

| Brief asks for | Why it doesn't fit as asked | What this spec does instead |
|---|---|---|
| §1 KPI cards: "Pending Scrutiny," "Accepted," "Passed," "Failed," "Certificates Pending" | These aren't real statuses — the actual lifecycle is `SUBMITTED → DOCUMENT_REVIEW → SCHEDULED → INSPECTION → APPROVED/REJECTED → CERTIFICATE_ISSUED`. The officer dashboard (spec 05) already renders exactly this breakdown via `ApplicationsSummary` (`GET /applications/stats`, zero-filled by-status chips) — functionally the same KPI row, real vocabulary. "Certificates Pending" has no real analog: there's no limbo state between `APPROVED` and `CERTIFICATE_ISSUED`, issuance is a single officer-triggered action | Reuse `ApplicationsSummary` verbatim, real status labels (§6.1) |
| §1 "Expiring Instruments" KPI | Real gap — see §1/§4 | New: widen `GET /admin/certificates/stats` to admit `LM_OFFICER` (§4) |
| §2/§3 "Priority" and "Verification Type" filters on the applications list | No priority concept exists anywhere in the data model; "Verification Type" already exists as `application_type` (`VERIFICATION`/`RE_VERIFICATION`) but `GET /applications` has no filter param for it today | Priority dropped entirely (inventing a field with no backing data); `application_type` filter flagged as a cheap possible Phase 2 addition (§9), not built here |
| §2 "Instrument Type" filter on the applications list | `GET /applications` has no `instrument_type` param (it exists on `GET /instruments`, not applications) — would need a new join, not a free reuse | Dropped from Phase 1, same "real backend join, not free" reasoning spec 18 §6.3 used for the identical ask |
| §4 Scrutiny | This is spec 11's document review checklist, verbatim: `DOCUMENT_REVIEW` status, `PATCH /applications/{id}/review-checklist`, Accept = `DOCUMENT_REVIEW → SCHEDULED`, Query = `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT` | Reuse unchanged — the existing checklist/status vocabulary, not a renamed parallel screen (same move spec 17 §2 made for the identical brief wording in the Super Admin spec) |
| §5 Query/Deficiency as its own entity (Query Type, Missing Document, Response Deadline, a 5-state Query status machine) | The real mechanism is one `note` field (10–1000 chars, `DEFICIENCY_NOTE_MIN`) on the `DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT` transition — no structured query object, no deadline, no separate status machine exists or is planned | Reuse the existing note-based deficiency flow; a structured query entity is a real, separate feature, not built here (§9) |
| §6 "Time" slot, "Mark Attendance," "Estimated Duration" | Spec 05 D3: "Date only, no time slot" (ASSUMPTION, load-bearing — `scheduled_date` is a `date` column). No attendance-marking or duration-estimate concept exists | Unchanged — date-only scheduling; attendance/duration dropped, no data to back them |
| §7 "My Verification Calendar" (Day/Week/Month views) | No calendar UI exists; the equivalent today is a sorted list (`GET /applications?status=SCHEDULED&sort=scheduled_asc`), already on `/dashboard` and filterable on `/applications` | Reuse the existing sorted-list pattern (§6.2); a calendar view is a real new frontend component for marginal benefit over a list — Phase 2 (§9) |
| §9 GPS/Location Capture, §20 Navigation/Map, "Mark Arrival"/"Start Visit" | Root `CLAUDE.md`'s Deferred list explicitly names Leaflet maps/PostGIS; no field-visit state machine (arrived/departed) exists beyond `SCHEDULED → INSPECTION` | Dropped — same deferred-tech boundary spec 17/18 already respect |
| §10 "LMO Digital Signature / Authentication" | Root `CLAUDE.md`'s own open decision: "Digital signature: hash-based in MVP, government e-sign later" — already resolved as a certificate-level `data_hash` tamper-evidence fingerprint (spec 08), not a live per-officer signature capture | Unchanged — no new signature-capture UI; the existing `data_hash` already is the MVP's answer to this open decision |
| §11 "Re-verification Required" as a third verification outcome alongside Pass/Fail | Root `CLAUDE.md`: "REJECTED is terminal. Re-verification means a new application" — there's no distinct non-terminal "needs re-verification" application status; `ApplicationType.RE_VERIFICATION` already models re-verification as its own application, not an outcome of this one | Map "Re-verification Required" onto the real flow: `REJECTED` + applicant/owner later files a new `RE_VERIFICATION` application (§6.9/§19 reuse, already works end to end) |
| §13 structured "Failure Category," "Recommended Action" fields | Only a single free-text note exists on `REJECTED` (`REJECT_NOTE_MIN = 10`) — no structured taxonomy of failure reasons | Reuse the existing note field; a failure-reason taxonomy is new structured data, not built here (§9) |
| §15 "Scan QR" (camera-based scanning) | No QR-scanning UI exists anywhere in the app; the public verify page is a URL target, not a scanner. An officer "verifying" a certificate today just opens the same public page any consumer would | Dropped — camera QR scanning is a real new feature (device camera access, a decode library), not a frontend reshuffle (§9) |
| §17 per-instrument "Verification History" as a dedicated timeline screen | The supersede chain (`supersedes_certificate_id`/`superseded_by_certificate_id`, spec 13) already encodes this relationally, but no frontend renders it as a timeline on `/instruments/[id]` today | Flagged as a cheap, real, small Phase 2 addition (§9) — not inventing new data, just not wired to a screen yet |
| §22 Notifications, §23 Reports | No in-app notification system exists (email only, step 10); no generic report engine exists | Dropped — identical reasoning to spec 17 §9/spec 18 §9 |
| §24 Audit Trail ("my activity" log for the officer) | `audit_logs` already records every officer action, but `GET /api/audit-logs` is `SUPER_ADMIN`/`STATE_ADMIN`-only (spec 17/18) — opening it to `LM_OFFICER` needs a **new, narrower** scoping concept (self-only, not jurisdiction-wide, since an officer seeing another officer's actions in the same district is a real RBAC question this spec doesn't want to silently decide) | Flagged as Decision D3 — recommend deferring, not a free reuse of the existing jurisdiction-shaped filter |
| §25 "Authorized Instrument Categories" on the LMO profile | No such concept exists — `LM_OFFICER` is not category-gated the way a GATC org's `gatc_eligible_category_ids` is; an officer already handles every instrument type in their district | Dropped as inapplicable, not silently invented |
| §26 nested sidebar (Applications/Verification submenus) | Every other role's nav in this codebase is a flat list (`NAV`, `SUPER_ADMIN_NAV`, `STATE_ADMIN_NAV`) — no nested-menu sidebar component exists | Two new flat links added to the existing officer `NAV` (§6.8), not a new nested-menu component |

Everything else (my applications, application details, scrutiny, scheduling, field verification,
digital inspection form, pass/fail, certificate issuance, instrument management, re-verification,
documents/evidence, access scope) maps exactly onto specs 01/03/05/06/07/08/11/14/15 as already
built — this spec changes none of it.

## 3. What already exists (no new backend work, mapped to the brief's own section numbers)

| Brief section | Already built as | Spec |
|---|---|---|
| §1 Dashboard (minus Expiring Instruments) | `OfficerDashboard` (`app/dashboard/page.tsx`): instrument count, `ApplicationsSummary` (by-status chips), needs-attention (SUBMITTED/DOCUMENT_REVIEW/INSPECTION), upcoming inspections (`sort=scheduled_asc`), recent | 05 |
| §2 My Applications | `/applications` list, officer-scoped via `scope_applications`, status filter, search, `sort` | 03/05 |
| §3 Application Details | `/applications/[id]`: applicant/business/instrument info, documents, previous certificate via supersede chain, fee status (`payment`, informational) | 03/08/12/13 |
| §4 Scrutiny | `PATCH /applications/{id}/review-checklist`, Accept/Query via `DOCUMENT_REVIEW → SCHEDULED`/`DOCUMENTS_DEFICIENT` | 11 |
| §5 Query/Deficiency (as a note, not an entity) | `DOCUMENTS_DEFICIENT` transition + `note`, `DOCUMENTS_DEFICIENT → SUBMITTED` resubmit | 03/11 |
| §6 Verification Scheduling | `DOCUMENT_REVIEW → SCHEDULED` (`scheduled_date`), reschedule (`PATCH .../inspection`), GATC routing | 05/15 |
| §8/§9 Verification Workflow / Field Verification | Mobile-first `/inspections/[id]`: instrument details → checklist → measurements → photos → remarks → submit | 06 |
| §10 Digital Inspection Form | Checklist items (`item_key`, `result`: PASS/FAIL/NA) + measurements (`label`, `expected_value`, `observed_value`); evidence photos (`INSPECTION_EVIDENCE`) | 06 |
| §11 Verification Result | `POST /inspections/{id}/submit`, then `INSPECTION → APPROVED/REJECTED` | 06/07 |
| §12 Pass Verification | `POST /applications/{id}/certificate`: cert + QR, `CERTIFICATE_ISSUED` | 08 |
| §13 Failed Verification | `INSPECTION → REJECTED` + note | 07 |
| §14 Certificate Management (single-application view) | `/certificates/[id]`: QR, PDF view/download | 08 |
| §16 Instrument Management | `/instruments` list + detail, officer read-only, jurisdiction-scoped | 02/05 |
| §19 Re-verification | `ApplicationType.RE_VERIFICATION` already exists and flows through the identical lifecycle — confirmed live in the seed data (`APP-2026-000012`, type Re-verification) | 03 |
| §21 Documents & Evidence | Upload/view/delete pipeline, evidence photos distinct from business documents | 03/06 |
| §28 Access Scope | `scope_applications`/`scope_instruments`'s existing `LM_OFFICER` branch (state **and** district locked) already enforces every line in this section | 01 |

No new tables, no migration, no new scoping branch — every item above is a frontend reuse of an
endpoint that already works correctly for `LM_OFFICER`.

## 4. New backend surface needed

| Endpoint | Change | Why |
|---|---|---|
| `GET /admin/certificates/stats`, `GET /admin/certificates/expiring-soon` | Router dependency widened from `Admin = require_roles(*ADMIN_ROLES)` to a **new, separate** `AdminOrOfficer = require_roles(*ADMIN_ROLES, Role.LM_OFFICER)` local to `routers/admin.py` — `ADMIN_ROLES` itself (`core/roles.py`) is **not** touched, since it's reused elsewhere for genuinely admin-only things (`GET /api/users`, etc.) and `LM_OFFICER` must not gain those. **Zero service change**: `services/admin.py: certificate_stats()`/`expiring_soon()` already call `scope_certificates(..., user)`, which already resolves through `scope_applications`'s existing `LM_OFFICER` branch (state **and** district locked) — this is the exact "the data layer already supports it, build the page" move specs 17/18 made, one rank further down |
| `GET /api/certificates` | **No change at all** — already in the `Reader` role set (`BUSINESS`/`LM_OFFICER`/`*_ADMIN`, spec 17). This is a pure frontend gap: no officer-facing page calls it yet |

That's the entire backend diff for this spec. Compare to specs 17/18, where four endpoints needed
real new actor-aware scoping logic — here, the scoping was already correct; only the role gate on
one shared router needed widening, carefully scoped to a *new* local dependency so it can't
accidentally leak into admin-only endpoints on the same router or elsewhere.

## 5. Access

`AdminOrOfficer` (§4) is used **only** on the two `/admin/certificates/*` routes. Every other
`ADMIN_ROLES`-gated endpoint (`GET /api/users`, `GET /api/audit-logs`, `GET /api/organizations?
type=GATC`, `GET /admin/state-overview`, `GET /admin/district-overview`) is untouched —
`LM_OFFICER` gains **no** new access beyond the two certificate-stats endpoints and the
already-open `GET /api/certificates`. The new frontend pages/sections this spec adds (§6) are
`LM_OFFICER`-only renders, same "build the page for the role that needs it" sequencing as
specs 17/18's own D1s.

## 6. Page contract

### 6.1 Dashboard (`/dashboard`'s existing `OfficerDashboard`, extended)

Add one KPI line reusing the now-available `GET /admin/certificates/stats` (§4):

```
┌ Officer dashboard ────────────────────────────────────────┐
│ Jurisdiction: JH / DHN                                      │
│ [Instruments: N]                                             │
│ Applications: N total — [8 Submitted] [4 Document review] … │  ApplicationsSummary, unchanged
│ [Certs expiring soon: N]                                      │  new, §4
│                                                               │
│ Needs attention: Submitted → Start review · Document review │  unchanged
│   → Schedule · Inspection → Continue inspection              │
│ Upcoming inspections (next 5, scheduled_asc)                 │  unchanged
│ Recent                                                        │  unchanged
└───────────────────────────────────────────────────────────┘
```

Dropped from the brief's §1: "Certificates Pending" (no real status for it, §2), "Today's
Verifications" as a distinct bucket (the existing "Upcoming inspections" list already is this —
splitting it into Today/Upcoming/Overdue sub-buckets is a client-side grouping of data already
fetched, flagged as a cheap Phase 2 polish item, §9, not core to this spec).

### 6.2 Certificates (`/certificates`, new page)

Thin reuse of `GET /api/certificates` (§4), same shape as spec 17/18's own certificate directory
pages: status filter, paginated, links to `/certificates/[id]`. Scoped automatically to the
officer's own jurisdiction via the existing `scope_certificates` → `scope_applications` chain —
no new filter logic needed beyond what spec 17 already built for this endpoint.

### 6.3 Expiring soon (`/certificates/expiring-soon`, new page)

Reuses `ExpiryDashboard` (`components/admin/expiry-dashboard.tsx`) **verbatim** — the exact same
component `STATE_ADMIN`/`DISTRICT_ADMIN` already see at `/admin`, now also reachable for
`LM_OFFICER` at a non-`/admin`-prefixed route (an officer has no `/admin` page at all, so this
needs its own path, not `/admin/certificates/expiring-soon`). No new component.

### 6.4 Sidebar

```
Dashboard
Instruments
Applications
Certificates          ← new (§6.2)
Expiring soon          ← new (§6.3)
Profile
```

Two new flat links added to the existing officer `NAV` array (`components/app-shell.tsx`) — not a
new nav array, not a nested menu (§2's note on §26).

### 6.5–6.9 Everything else in the brief

No page contract needed — §3's table already names the existing page for every other brief
section (My Applications → `/applications`, Scrutiny → the existing checklist on
`/applications/[id]`, Field Verification → `/inspections/[id]`, etc.). This spec does not modify
any of them.

## 7. Decisions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Widen `ADMIN_ROLES` itself to include `LM_OFFICER`, or add a new narrower dependency? | **New dependency (`AdminOrOfficer`), `ADMIN_ROLES` unchanged** | `ADMIN_ROLES` gates genuinely admin-only endpoints elsewhere (user management, audit logs, GATC directory, state/district overview) — widening the shared constant would silently grant `LM_OFFICER` access to all of those too. A new, narrowly-scoped local dependency (same pattern `routers/users.py: SuperOrStateAdmin` already set in spec 18) keeps the blast radius to exactly the two endpoints this spec means to open |
| D2 | Build the brief's calendar view (§7), or keep the existing sorted-list pattern? | **Keep the list** | A calendar is a real, separate frontend component (month/week/day grid, event rendering) for marginal benefit over a list that already sorts by `scheduled_date` — not a reuse, a new feature. Revisit only if officers report the list is genuinely hard to scan |
| D3 | Give `LM_OFFICER` a "my activity" audit view (§24)? | **Not in Phase 1** | Needs a new scoping concept (`actor_user_id == self`, not jurisdiction-wide like every existing `scope_*` branch) that no endpoint has today — a real RBAC decision (can an officer see a colleague's actions in the same district?) this spec shouldn't make by omission inside an otherwise-small spec |
| D4 | Add `instrument_type`/`application_type` filters to `GET /applications`? | **Not in Phase 1** | Real backend joins/params, not a free reuse (same reasoning spec 18 §6.3 used for the identical ask on the Super/State Admin applications page) — flagged for Phase 2 if officers actually need it (§9) |
| D5 | Wire the certificate supersede chain into a visible "Verification History" timeline on `/instruments/[id]` (§17)? | **Not in Phase 1**, but cheap later | The data already exists (`supersedes_certificate_id`/`superseded_by_certificate_id`); this is a small, real frontend addition, not a backend gap — worth a future one-page spec of its own rather than a drive-by addition here |

## 8. Frontend/backend file list (proposed — not yet built)

```
backend:
app/routers/admin.py          + AdminOrOfficer = require_roles(*ADMIN_ROLES, Role.LM_OFFICER),
                               used only on GET /admin/certificates/{stats,expiring-soon}
tests/test_admin_certificates.py   extended: LM_OFFICER sees only own-district certs via
                                    scope_certificates (already correct — this just proves it
                                    through the newly-opened route), every other non-admin/
                                    non-officer role still 403
tests/test_rbac.py            extended: the two endpoints' existing admin-only sweep gains an
                               LM_OFFICER-admitted case; GET /api/users, /api/audit-logs,
                               /api/organizations?type=GATC, state/district-overview all keep
                               their existing LM_OFFICER → 403 assertions unchanged (proves D1's
                               isolation — ADMIN_ROLES itself was never touched)

frontend:
app/certificates/page.tsx                 (new) §6.2 — mirrors app/admin/certificates/page.tsx's
                                           shape but LM_OFFICER-gated, non-/admin-prefixed path
app/certificates/expiring-soon/page.tsx   (new) §6.3 — thin wrapper around the existing
                                           ExpiryDashboard, same pattern as
                                           app/admin/certificates/expiring-soon/page.tsx
app/dashboard/page.tsx                    OfficerDashboard gains one KPI card (§6.1), reusing a
                                           new getAdminCertificateStats() call already LM_OFFICER
                                           can now make
components/app-shell.tsx                  NAV (base array) gains Certificates + Expiring soon
                                           links (§6.4) — SUPER_ADMIN_NAV/STATE_ADMIN_NAV
                                           untouched
lib/api.ts, lib/types.ts                  no new types — getAdminCertificateStats()/
                                           getCertificates() already exist from spec 17
```

## 9. Explicitly deferred (recorded, not committed)

- A structured Query/Deficiency entity (type, missing-document taxonomy, response deadline, a
  5-state status machine) — the single `note` field stays the mechanism (§2).
- A calendar view (Day/Week/Month) for scheduled inspections — the existing sorted list stays
  (§2/D2).
- GPS/location capture, map/navigation links, a field-visit state machine (arrived/departed) — all
  deferred tech or unmodeled concepts (§2).
- Camera-based QR scanning — a real new feature (device camera + decode library), not a reshuffle
  (§2).
- A structured failure-reason taxonomy beyond the existing free-text rejection note (§2).
- An `LM_OFFICER`-scoped "my activity" audit trail (D3) — needs a new self-only scoping concept.
- `instrument_type`/`application_type` filters on `GET /applications` (D4) — real new backend
  params.
- A visible per-instrument "Verification History" timeline surfacing the existing supersede chain
  (D5) — small, real, but a frontend-only addition deserving its own short spec.
- Splitting "Upcoming inspections" into Today/Upcoming/Overdue sub-buckets — client-side grouping
  of data already fetched, a polish item, not core to this spec.
- Notifications, generic report export — same reasoning as specs 17/18's own §9s.

## 10. Acceptance criteria

- [x] As `LM_OFFICER`: `GET /admin/certificates/stats` and `.../expiring-soon` return `200`,
  scoped to the officer's own district — `tests/test_admin_certificates.py::test_admin_certificates_scope`
  (extended) and `test_admin_certificates_stats_scoped_to_officer_district` (new); confirmed live
  (`officer.dhn@lm.demo` saw exactly the 3 Dhanbad certificates, matching a direct API call).
- [x] Every other `ADMIN_ROLES`-gated endpoint still returns `403` for `LM_OFFICER` — proved for
  free by `test_rbac.py`'s existing `ALL_ROLES` sweeps for `GET /api/users`, `/api/audit-logs`,
  `/api/organizations?type=GATC` (unchanged by this spec, `ALL_ROLES` already includes
  `LM_OFFICER`), confirming the new `AdminOrOfficer` dependency never leaked into `ADMIN_ROLES`.
- [x] `/certificates` as `LM_OFFICER`: shows only certificates in the officer's own district,
  status filter present, links to `/certificates/[id]` unchanged — confirmed live.
- [x] `/certificates/expiring-soon` as `LM_OFFICER`: renders the identical `ExpiryDashboard` four
  card layout the admin roles already see, jurisdiction-scoped to the officer — confirmed live
  (1 valid / 0 expiring / 1 expired / 0 revoked, matching a direct `GET /admin/certificates/stats`
  call with the same token).
- [x] `/dashboard`'s officer view shows a real "Certificates expiring soon" count matching a
  direct call to the same endpoint — confirmed live (showed `0`, matching the API).
- [x] Sidebar shows exactly `Dashboard, Instruments, Applications, Certificates, Expiring soon,
  Profile` for `LM_OFFICER`, via a new dedicated `OFFICER_NAV` array (not an edit to the shared
  `NAV`); `BUSINESS`/`GATC` nav is pixel-identical to before — confirmed live by logging in as
  `owner@abctraders.demo` and `gatc.dhn@lm.demo` and seeing the plain, unchanged `NAV`.
- [x] `BUSINESS` and `GATC` still get `403` on both new/extended endpoints — `test_rbac.py::
  test_admin_certificate_endpoints_admit_officer` (new `ALL_ROLES` sweep); also confirmed live
  (`owner@abctraders.demo` navigating directly to `/certificates/expiring-soon` got "You don't
  have access to this page").

## 11. Verification record

**Backend** (`pytest`, local `lm_test`): full suite green — 592 passed. New/extended:
`tests/test_admin_certificates.py` (docstring updated, `LM_OFFICER` removed from the
forbidden-roles tuple, 2 new officer-scoping assertions/test), `tests/test_rbac.py` (+1 new
`ALL_ROLES` sweep for the two certificate-monitoring endpoints). `ruff check .` and
`ruff format --check .` both clean (one auto-fixed line-length wrap).

**Frontend** (`tsc --noEmit`, `eslint`, `next build`): all clean. `next build` confirms
`/certificates` and `/certificates/expiring-soon` register as new routes.

**Manual, in Chrome**, against the local `lm_dev`-backed dev server (the same one used for spec
18's verification, already pointed at the correct backend on port 8000):
- Logged in as the seeded `officer.dhn@lm.demo`: sidebar showed exactly the new `OFFICER_NAV`
  (Dashboard, Instruments, Applications, Certificates, Expiring soon, Profile); dashboard showed
  a new "Certificates expiring soon" row reading `0`, matching a direct API call; existing
  sections (instrument count, applications summary, needs-attention, recent) all rendered
  unchanged.
- `/certificates` showed exactly the 3 certificates belonging to Dhanbad applications (VALID,
  SUPERSEDED, EXPIRED statuses, confirming the status chip and table render correctly), with a
  working status filter.
- `/certificates/expiring-soon` rendered the identical four-card `ExpiryDashboard` (1 valid, 0
  expiring, 1 expired, 0 revoked) already used at `/admin/certificates/expiring-soon`.
- **Regression**: logged in as `owner@abctraders.demo` (`BUSINESS`) and `gatc.dhn@lm.demo`
  (`GATC`) in turn — both showed the plain, unmodified `NAV` (no Certificates/Expiring soon
  links), and both were correctly blocked ("You don't have access to this page") when navigating
  directly to `/certificates/expiring-soon` by URL.
