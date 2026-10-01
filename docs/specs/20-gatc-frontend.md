# Spec 20 — GATC (Government Approved Test Centre) frontend

**Status:** Done. Implemented and verified (§11). §7's Decisions (D1–D4) were accepted as written.
**Build order:** Step 20 (post-MVP addition, on top of steps 1–19)
**Depends on:** Spec 06 (field inspection checklist/measurements), Spec 07 (approve/reject),
Spec 08 (certificate issuance), Spec 15 (GATC eligibility/allocation — this spec **finishes the
rollout** that one deliberately left narrow), Spec 19 (LMO frontend — the identical reuse pattern,
one role further down)
**Source input:** a pasted "GATC — Frontend Specification" brief (31 sections, closely mirroring
spec 19's LMO brief but adding a Principal-Officer/Staff hierarchy, test-centre operations, and
GATC-level analytics). Not its contents verbatim — §2 explains why.

## 1. Goal

Spec 15 built a genuine, narrow, identity-scoped `GATC` role: a `GATC`-role user becomes the
`assigned_officer_id` on an `Inspection` and then flows through the **exact same**
inspection/checklist/measurement/approve-reject machinery `LM_OFFICER` already uses —
`scope_applications()` already has a `GATC` branch (the narrowest of any role: exactly the
application(s) this specific person has ever been assigned to inspect), and every downstream
helper that chains through it (`scope_documents`, `scope_certificates`, `scope_inspections`)
already resolves correctly for `GATC` too. But spec 15 deliberately left several **router-level**
role gates narrow — `GET /applications` (list), `GET /applications/stats`, every certificate
endpoint, and document view/upload — so a `GATC` user today can act on the one application a
`LM_OFFICER` directly linked them to, but cannot browse a list of their own work, view their own
certificates, view the applicant's documents, or upload their own evidence photos. The frontend's
own `/dashboard` reflects this half-finished state literally: every other role gets a real
dashboard; `GATC` gets a hard-coded stub, **"GATC dashboard — Assigned verifications will appear
here."**

This spec is step 15's unfinished rollout, not a new workflow: four narrow router role-gates get
widened (zero or near-zero service-layer changes in every case — the scoping was already built),
replacing the dashboard stub with a real one and giving `GATC` the same page-reuse treatment spec
19 gave `LM_OFFICER`.

## 2. Why this spec is narrower than the pasted brief

Same reasoning specs 17/18/19 §2 already established. Several sections here fail for a reason
spec 19's LMO brief never hit: `GATC`'s own `ALLOWED_TRANSITIONS` membership (`services/
applications.py`) proves several brief sections describe actions `GATC` is **structurally
incapable of performing** in the real system, not just actions nobody built a screen for —
`GATC` is only ever granted `SCHEDULED → INSPECTION` and `INSPECTION → APPROVED`/`REJECTED`.
Scrutiny, querying, and scheduling are — and per spec 15's explicit design, always will be — the
routing `LM_OFFICER`'s job alone.

| Brief asks for | Why it doesn't fit as asked | What this spec does instead |
|---|---|---|
| §4 Scrutiny, §5 Query/Deficiency Management | `GATC` is never in the role set for `DOCUMENT_REVIEW → SCHEDULED`/`DOCUMENTS_DEFICIENT` — a `GATC` user is *routed to* at scheduling time by the `LM_OFFICER` who already did scrutiny; `GATC` never scrutinizes anything itself, in the brief's vocabulary or the real one | Dropped entirely — not a reuse-under-different-name like spec 19's Scrutiny mapping, because this action is structurally not `GATC`'s to take |
| §6 "Schedule Verification," "Reschedule" actions | `PATCH /applications/{id}/inspection` (reschedule) and the `DOCUMENT_REVIEW → SCHEDULED` transition are both `LM_OFFICER`-only (spec 05/15) — `GATC` only ever *executes* a schedule already set for them | Dropped; `GATC`'s real actions start at "Start verification" (`SCHEDULED → INSPECTION`), already built (spec 06) |
| §7 GATC Test Calendar (Day/Week/Month) | Same reasoning as spec 19 D2 — no calendar UI exists; a sorted list already serves this | Reuse the existing sorted-list pattern, not a new calendar component |
| §9/§20 GPS/location capture, "Mark Attendance," "Instrument Received" state, Estimated Duration | Deferred tech (root `CLAUDE.md`'s Leaflet/PostGIS list) or an unmodeled field-visit state machine — identical to spec 19 §2's identical asks for LMO | Dropped |
| §10 "Authorized GATC Staff" / "Principal Officer" **authentication** on the inspection form | No per-submission signer-identity concept exists beyond the already-logged `actor_user_id` on every audit row and the certificate's own `data_hash` (root `CLAUDE.md`'s resolved digital-signature decision) | Unchanged — same answer spec 19 §2 gave for the identical ask |
| §11 "Re-verification Required" as a 3rd outcome | Same as spec 19 §2: `REJECTED` is terminal; re-verification is a new `ApplicationType.RE_VERIFICATION` application, not a status | Map onto the real flow, already works end to end |
| §13 structured "Failure Category," "Recommended Action" | Only a single free-text rejection note exists (`REJECT_NOTE_MIN = 10`) | Reuse the existing note field |
| §15 "Scan QR" (camera-based scanning) | No QR-scanning UI exists anywhere in the app | Dropped — same as spec 19 §2 |
| §16 Instrument Management (a browsable list) | `scope_instruments()` has **no `GATC` branch at all** (falls through to `false()` — zero rows), unlike `scope_applications`/`scope_certificates`/`scope_documents`. Building one needs a genuinely new join (instrument → application → inspection → assigned_officer_id), not a free reuse of an existing branch the way every other gate in this spec is | Deferred (D1) — the one instrument `GATC` is working on is already fully embedded in `ApplicationDetail.instrument`, reachable without a separate list |
| §17 a dedicated "Verification/Test History" timeline screen | Same as spec 19 D5: the data (supersede chain, application history) already exists; no screen renders it as a timeline for anyone yet | Deferred, same reasoning |
| §18 Expiry Monitoring as its own dashboard | `GET /admin/certificates/{stats,expiring-soon}` was widened to `LM_OFFICER` in spec 19 because an officer's jurisdiction can hold dozens of certificates. A `GATC` user's lifetime certificate count is whatever they've personally tested — already fully visible on the certificate list this spec opens (§6.5), making a second "expiring soon" dashboard low-value for this role | Deferred (D2) — not built, `GATC`'s own certificate list already shows real status per row |
| §20 "Test Centre Operations," "Test Queue" | This is "my applications filtered to `SCHEDULED`/`INSPECTION`" — already the dashboard's needs-attention section, not a separate operational queue concept | Reuse (§6.1) |
| §22 Staff Management, §23 Principal Officer view | **No such hierarchy exists in the data model.** `Role.GATC` is one flat role — there is no `principal_officer_id` column on `Organization`, no staff-vs-principal distinction anywhere, no "assign a test to a specific staff member" concept (a `LM_OFFICER` already names a specific `GATC` *user* at scheduling time, spec 15's own `gatc_user_id`, so per-person assignment already exists — just not a principal-manages-staff hierarchy on top of it) | Dropped as inapplicable, not invented — the existing per-org staff roster is already visible to a `SUPER_ADMIN`/`STATE_ADMIN` via the GATC directory (spec 17/18), which stays the only place that view lives |
| §24 GATC Analytics, §25 Reports, §26 Notifications | Same deferred reasoning as every prior spec's own §9 — no chart/report/notification infrastructure exists | Dropped |
| §28 "Authorized Instrument Categories" on the profile | Unlike spec 19's identical ask for `LM_OFFICER` (inapplicable there), this one **is real data** — `organizations.gatc_eligible_category_ids` (spec 15). But no endpoint exposes it back to the `GATC` user themselves today (only `SUPER_ADMIN`'s GATC directory reads it) | Flagged as a small, real, cheap Phase 2 addition (D3) — not core to unblocking the dashboard stub, so not bundled into this spec's backend diff |

Everything else (application detail, field verification, digital inspection form, pass/fail,
certificate issuance's downstream display, documents/evidence once unblocked, access scope) maps
onto specs 06/07/08/15 exactly as already built.

## 3. What already exists (no new scoping logic needed anywhere in this spec)

| Brief section | Already built as | Spec |
|---|---|---|
| §8/§9 Verification Workflow / GATC Verification | `_reader_or_assigned_gatc()` (`routers/applications.py`, and the analogous pair in `routers/inspections.py`) already admits the specifically-assigned `GATC` user to `GET/PATCH /applications/{id}...` and `GET/PATCH/POST /inspections/{id}...` — these single-item endpoints needed per-request identity checks and spec 15 already built them | 06/15 |
| §10 Digital inspection form | Checklist items + measurements, identical shape `LM_OFFICER` uses (`item_key`/`result`, `label`/`expected_value`/`observed_value`) | 06 |
| §11/§12/§13 Result, Pass, Fail | `POST /inspections/{id}/submit`, then `INSPECTION → APPROVED`/`REJECTED` — `GATC` is already in `ALLOWED_TRANSITIONS` for both (spec 15) | 06/07/15 |
| §19 Re-verification | `ApplicationType.RE_VERIFICATION` already exists, same lifecycle | 03 |
| §31 Access Scope | `scope_applications()`'s `GATC` branch (`Application.inspection.has(Inspection.assigned_officer_id == user.id)`, a correlated `EXISTS`) already enforces every line of this section — narrower than any other role's scope, by design | 15 |
| Evidence-photo upload identity check | `services/documents.py: _check_upload_allowed()`'s `INSPECTION_EVIDENCE` branch is **already identity-based, not role-based** (`application.inspection.assigned_officer_id != user.id` → 403) — it would already accept a `GATC` user correctly. Only the **router's** `Uploader` dependency excludes `GATC` today (§4) | 06 |

No new tables, no migration, no new `scope_*` branch anywhere in this spec — every gap is a
router-level role-set that was left narrow in spec 15 and never revisited, not a missing
capability in the data layer.

## 4. New backend surface needed

Four existing role-set constants get `Role.GATC` added. Every one of them already sits in front of
a service function that calls `scope_applications()` (or something that chains through it) — zero
service-layer changes anywhere in this table.

| File / constant | Change | Why it's safe (already correctly scoped) |
|---|---|---|
| `routers/applications.py: READER_ROLES` | `+ Role.GATC` | `list_applications()`/`stats()` already call `scope_applications(stmt, user)`, whose `GATC` branch already exists (spec 15) |
| `routers/certificates.py: Reader` | `+ Role.GATC` | `list_certificates()`/`get()` already call `scope_certificates(select(...), user)` → `scope_applications()`. **Also fixes a latent dead link**: a `GATC`-tested application that later reaches `CERTIFICATE_ISSUED` already shows a certificate summary on `/applications/{id}` (embedded via `ApplicationDetail.certificate`) with a "View certificate" link to `/certificates/{id}` — today that link 403s a `GATC` viewer; this closes that gap as a side effect, not a separate task |
| `routers/documents.py: Reader` | `+ Role.GATC` | `GET /documents/{id}/url` → `scope_documents()` → `scope_applications()`. Lets `GATC` view applicant/ownership/previous-certificate documents for their own assigned application (brief §3/§21) |
| `routers/documents.py: Uploader` | `+ Role.GATC` | `_check_upload_allowed()`'s `INSPECTION_EVIDENCE` branch is already identity-based (see §3) — adding `GATC` here only unblocks evidence-photo upload/delete during the `GATC` user's own active inspection; the `else` branch (ordinary business documents) still hard-rejects any non-`BUSINESS` actor unchanged, so `GATC` still cannot touch applicant-submitted documents, correctly |

**Not widened** (§7 D1): `routers/instruments.py: Reader`, and `scope_instruments()` gains no
`GATC` branch — a real new join, not a free reuse, and not essential (§2).
**Not widened** (§7 D2): `routers/admin.py`'s `AdminOrOfficer` (spec 19) stays `LM_OFFICER`-only,
not extended to `GATC`.

## 5. Access

Exactly the four gates in §4 change. `GATC` remains `403` on every other endpoint it was already
excluded from: `GET /instruments`, `GET /admin/*`, `GET /api/users`, `GET /api/audit-logs`,
`GET /api/organizations`, scheduling/reschedule, document-review-checklist — nothing here widens
any of those.

## 6. Page contract

### 6.1 Dashboard (`app/dashboard/page.tsx`'s `RoleCard` — today's fallback/stub branch, replaced)

Current code (verified): any role not `BUSINESS`/`LM_OFFICER`/`ADMIN_ROLES` falls into a literal
placeholder — `<CardTitle>GATC dashboard</CardTitle>` / `"Assigned verifications will appear
here."` — no data fetch at all. New `GatcDashboard`, modeled on `OfficerDashboard` but narrower
(no district/jurisdiction line — `GATC` has none; no instrument count — §2's D1):

```
┌ GATC dashboard ───────────────────────────────────────────┐
│ {organization_name}                                         │
│ Applications: N total — [2 Inspection] [1 Certificate issued]│  getApplicationStats(), now open
│                                                               │
│ Needs attention: Scheduled → Start verification ·           │  only these two buckets — GATC
│   Inspection → Continue inspection                          │  is never in SUBMITTED/DOCUMENT_REVIEW
│ Recent                                                        │  unchanged pattern
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Applications (`/applications`)

**Zero frontend changes.** The existing shared list page has no role allowlist of its own — it
already relies entirely on the backend 403 that's being lifted (§4). Once `READER_ROLES` admits
`GATC`, this page works unchanged, showing exactly the (small) set of applications
`scope_applications` resolves for that `GATC` user.

### 6.3 Application details / Field verification / Digital inspection form / Result / Pass / Fail

**Zero changes anywhere.** Already fully functional for the specifically-assigned `GATC` user
since spec 15 (§3).

### 6.4 Documents & Evidence

**Zero frontend changes.** The existing document-viewer on `/applications/{id}` and the
evidence-photo upload step on `/inspections/{id}` both already call the same endpoints `BUSINESS`/
`LM_OFFICER` use — once `Reader`/`Uploader` admit `GATC` (§4), both start working for a `GATC`
user with no new code.

### 6.5 Certificates (`/certificates`, reused from spec 19)

Widen the existing page's gate from `user.role === "LM_OFFICER"` to
`["LM_OFFICER", "GATC"].includes(user.role)`. One copy adjustment: the subtitle ("Every
certificate in your district") doesn't fit `GATC`'s non-jurisdictional scope — swap to a
role-aware line ("Every certificate in your district." / "Every certificate you've tested."). No
new page, no backend change beyond §4's certificate `Reader` widen. `/certificates/expiring-soon`
is **not** extended to `GATC` (D2) — stays `LM_OFFICER`-only.

### 6.6 Sidebar

```
Dashboard
Applications
Certificates
Profile
```

A new `GATC_NAV` (not an edit to the shared `NAV`, same reasoning spec 19 §3.4 used for
`OFFICER_NAV`) — no "Instruments" (dead end, §2/D1), no "Expiring soon" (D2).

## 7. Decisions

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Build a `scope_instruments()` `GATC` branch + instrument list page? | **Not in Phase 1** | Real new join (instrument → application → inspection → assigned_officer_id), not a free reuse like every other gate in this spec; the one instrument a `GATC` user is working on is already fully embedded in `ApplicationDetail.instrument` |
| D2 | Extend `GET /admin/certificates/{stats,expiring-soon}` (spec 19's `AdminOrOfficer`) to `GATC` too? | **No** | A `GATC` user's lifetime certificate count is small and already fully visible, with real status, on the certificate list this spec opens (§6.5) — a second "expiring soon" view adds little for this role |
| D3 | Expose `organizations.gatc_eligible_category_ids` back to the `GATC` user on their own profile? | **Not in Phase 1**, flagged for later | Real data, genuinely useful, but needs a new field on a response the `GATC` user themselves can read (today only `SUPER_ADMIN`'s GATC directory does) — a small, separate addition, not bundled into a spec whose backend diff is otherwise four pure role-set widenings with zero new exposure surfaces |
| D4 | Build the brief's Staff Management / Principal Officer hierarchy? | **No — inapplicable, not deferred** | No such data model exists (`Role.GATC` is flat); inventing one would be a real new feature with no named source, the same "never invent" bar root `CLAUDE.md` sets for legal/regulatory facts |

## 8. Frontend/backend file list (as built)

```
backend:
app/routers/applications.py   READER_ROLES gains Role.GATC; the now-fully-redundant
                               _reader_or_assigned_gatc()/ReaderOrAssignedGatc (and its unused
                               Forbidden/gatc_service imports) removed -- GET/PATCH
                               /{application_id} now just use the plain Reader dependency
app/routers/certificates.py   Reader gains Role.GATC
app/routers/documents.py      Reader and Uploader both gain Role.GATC
tests/test_rbac.py, test_applications_rbac.py, test_applications_stats.py,
  test_applications_transitions.py, test_scheduling.py, test_inspection_start.py,
  test_gatc_eligibility.py
                               every pre-existing GATC-403 assertion on an endpoint this spec
                               widened flipped to the new, correct narrow-scope behavior (200
                               + empty list, or 404 out-of-scope -- never 403 once GATC is a
                               Reader); found via a full-suite run, several beyond what the
                               original plan anticipated (e.g. an unrelated GATC user hitting a
                               status-transition endpoint now 404s instead of 403)
tests/test_gatc_access.py (new)
                               positive-case coverage: an assigned GATC user sees only their own
                               application in the list, reads their own documents, sees their own
                               certificate once issued, uploads/deletes evidence during their own
                               inspection (and is still rejected for ordinary document types),
                               and is still 403 everywhere this spec didn't touch

frontend:
app/dashboard/page.tsx        RoleCard's GATC fallback replaced with a real GatcDashboard (§6.1);
                               the now-unreachable final fallback simplified to `return null`
app/certificates/page.tsx     gate widened to ["LM_OFFICER","GATC"]; role-aware subtitle (§6.5);
                               page function renamed CertificatesPage (no longer officer-only)
components/app-shell.tsx      + GATC_NAV (§6.6), branched before the generic NAV fallback
```

No other frontend files change — `/applications`, `/applications/[id]`, `/inspections/[id]`,
`/certificates/[id]` all work unchanged once the backend gates open (§6.2–6.4).

## 9. Explicitly deferred (recorded, not committed)

- `scope_instruments()` `GATC` branch + instrument list page (D1).
- Expiry monitoring for `GATC` (D2).
- `gatc_eligible_category_ids` surfaced on the `GATC` user's own profile (D3).
- A Staff Management / Principal Officer hierarchy (D4) — no data model, not invented here.
- A structured Query/Deficiency entity, scheduling actions, a calendar view, GPS/maps, camera QR
  scanning, a structured failure-reason taxonomy, a verification-history timeline screen,
  analytics/reports/notifications — same reasoning as specs 17/18/19's own deferred lists.

## 10. Acceptance criteria

- [x] As `GATC`: `GET /applications`/`/applications/stats` return `200`, scoped to exactly the
  application(s) this user has been assigned to — never another `GATC` user's —
  `tests/test_gatc_access.py::test_gatc_sees_only_assigned_application_in_list`, confirmed live.
- [x] As `GATC`: `GET /api/certificates`, `GET /certificates/{id}` return `200`, scoped
  identically; a certificate from an application this `GATC` user was never assigned to → `404` —
  `test_gatc_access.py::test_gatc_can_view_own_certificate_once_issued`, confirmed live (an empty
  "No certificates match." state for a `GATC` user with no issued certificate yet).
- [x] As `GATC`: `GET /documents/{id}/url` returns `200` for a document on their own assigned
  application; `POST/DELETE /documents` succeeds for `INSPECTION_EVIDENCE` during their own active
  (not yet submitted) inspection, and still `403`s for any ordinary (non-evidence) document type —
  `test_gatc_access.py::test_gatc_can_read_assigned_application_documents`/
  `test_gatc_can_upload_and_delete_evidence_during_own_inspection`.
- [x] `GET /instruments`, every `/admin/*` route, `/api/users`, `/api/audit-logs`,
  `/api/organizations` all still `403` for `GATC` — `test_gatc_access.py::
  test_gatc_still_forbidden_elsewhere`; confirmed live (`/instruments` → "You don't have access to
  instruments.", `/certificates/expiring-soon` → "You don't have access to this page.").
- [x] `/dashboard` as `GATC` shows real counts (not the old static stub text), matching a direct
  `GET /applications/stats` call — confirmed live (1 application, 1 Inspection chip, a real
  needs-attention row linking to the assigned inspection).
- [x] `/applications`, `/applications/[id]`, `/inspections/[id]`, `/certificates/[id]` all render
  correctly for `GATC` with zero frontend code changes (confirms §4 alone was sufficient) —
  confirmed live for `/applications`.
- [x] `/certificates` as `GATC`: shows only certificates for applications they were assigned to;
  subtitle reads the `GATC`-specific copy ("Every certificate you've tested."), not the officer
  district wording — confirmed live.
- [x] Sidebar shows exactly `Dashboard, Applications, Certificates, Profile` for `GATC` — no
  "Instruments," no "Expiring soon"; every other role's nav is unchanged — confirmed live for
  `GATC`, `LM_OFFICER` (`OFFICER_NAV` untouched), and `BUSINESS` (plain `NAV` untouched).

## 11. Verification record

**Backend** (`pytest`, local `lm_test`): full suite green — 597 passed (592 pre-existing + 5 new
in `test_gatc_access.py`). `ruff check .` and `ruff format --check .` both clean (two auto-fixed
formatting wraps). A full-suite run surfaced several pre-existing tests whose GATC-403 assumption
broke as a direct, correct consequence of widening `READER_ROLES` — beyond what the implementation
plan had anticipated — each fixed to assert the new, narrow-scope behavior (`200`+empty-list or
`404`, never `403`, for an unrelated `GATC` caller): `test_applications_rbac.py`
(`test_owner_only_endpoints`, `test_read_endpoints`, `test_document_url`),
`test_applications_stats.py::test_rbac`, `test_applications_transitions.py`
(`test_evaluation_order`, `test_approve_reject_role_and_scope`),
`test_scheduling.py::test_schedule_role_and_scope`, `test_inspection_start.py::
test_start_role_rejected`, and `test_gatc_eligibility.py::
test_assigned_gatc_can_start_perform_and_approve`'s own `other_gatc` assertions. Also removed
`routers/applications.py`'s `_reader_or_assigned_gatc()` dependency and `ReaderOrAssignedGatc`
alias entirely, since widening `READER_ROLES` made its `GATC`-specific branch unreachable dead
code with a now-false docstring claim ("must still see exactly 403, never 404") — `GET/PATCH
/{application_id}` now just use the plain `Reader` dependency.

**Frontend** (`tsc --noEmit`, `eslint`, `next build`): all clean. `next build` shows no new routes
(this spec reuses `/applications`, `/certificates`, `/dashboard` — no new paths).

**Manual, in Chrome**, against the local `lm_dev`-backed dev server, logged in as the seeded
`gatc.dhn@lm.demo` / `LmDemo@2026` account (the same one used as a regression check in specs
18/19's own verification):
- `/dashboard` rendered the real `GatcDashboard` — "Dhanbad GATC Test Centre", "1 application", a
  "1 Inspection" status chip, a "Needs your attention" row linking the one assigned application
  ("Continue inspection"), and a matching "Recent" entry — not the old stub text.
- `/applications` showed exactly that one application, using the exact same shared list page every
  other role sees.
- `/certificates` showed the `GATC`-specific subtitle and correctly rendered "No certificates
  match." (this `GATC` user's one assigned application is still `INSPECTION`, no certificate
  issued yet).
- `/instruments` → "You don't have access to instruments." (`D1`, confirmed still blocked).
- `/certificates/expiring-soon` → "You don't have access to this page." (`D2`, confirmed still
  `LM_OFFICER`-only).
- **Regression**: logged in as `officer.dhn@lm.demo` (`LM_OFFICER`) — `OFFICER_NAV` and
  `/certificates/expiring-soon` both rendered exactly as before (1 valid / 0 expiring / 1 expired
  / 0 revoked), untouched by this spec. Logged in as `owner@abctraders.demo` (`BUSINESS`) — sidebar
  showed the plain, unmodified `NAV` (`Dashboard, Instruments, Applications, Profile`, no
  "Certificates" link), and `/certificates/expiring-soon` correctly still 403s them.
