# Spec 15 — GATC eligibility + allocation (rev 1)

**Status:** Implemented, tested locally, **not yet applied to Supabase**
**Build order:** Step 15 (post-MVP addition, on top of steps 11/14/13/12/16 — branched from
`feat/spec-16-instrument-categories`)
**Depends on:** Spec 06 (`assigned_officer_id`'s "a specific person" semantics, the checklist/
approve-reject machinery this step reuses verbatim), Spec 14 (`verification_mode`/
`OFFICE_TEST_CENTRE`/`ON_SITE`), Spec 16 (`instrument_categories`/`instruments.category_id`)

## 1. Goal

`GATC` has existed as a real `Role`/`OrgType` value since spec 01, but with zero actual workflow:
every inspection was performed by a self-assigning `LM_OFFICER`, and `GATC` was rejected (403) by
every application/instrument/document endpoint. The root `CLAUDE.md`'s open decision — "GATC
workflow depth: minimal" — is resolved by this step as **minimal but real**: a GATC-role user
becomes a genuine, category-gated `assigned_officer_id` on an `Inspection`, and then flows through
the *exact same* inspection/checklist/measurement/approve-reject machinery an `LM_OFFICER` already
uses. Nothing about that machinery is duplicated or forked for GATC.

Three pieces, all additive:

1. `organizations.gatc_eligible_category_ids` — which `instrument_categories.id` values a GATC
   organization is approved to test.
2. `inspections.assignee_role` — a denormalized record of which role (`LM_OFFICER` or `GATC`) was
   actually assigned, alongside the existing `assigned_officer_id`.
3. `GET /api/gatc/eligible` (+ a small `GET /api/gatc/{organization_id}/users` helper) and an
   extended `DOCUMENT_REVIEW -> SCHEDULED` transition that can target a specific GATC user instead
   of always self-assigning the scheduling officer.

**Out of scope** (explicit simplifications, not oversights):
- Any endpoint to *write* `gatc_eligible_category_ids` — configured directly in the database (or a
  future seed) until an org-management step adds one. This step only *reads* it (§9 D5).
- GATC access to evidence-photo upload/delete (`POST/DELETE /api/documents`) and to the
  general-purpose `GET /applications` (list) / `GET /applications/stats` endpoints. A GATC
  inspection can be fully completed (checklist + measurements + submit + approve/reject) without
  evidence photos, which are optional (`services/inspections.py: submit()` never requires them);
  see §9 D6 for why these specific endpoints stay untouched.
- Deep validation of `gatc_eligible_category_ids` against real `instrument_categories` rows (no FK
  is possible on a JSONB array element) — same "MVP simplification, not an oversight" posture spec
  16 already takes for its own `category_values` validation.
- Any change to who may issue a certificate (`POST /applications/{id}/certificate` stays
  `LM_OFFICER`-only, unchanged) — GATC inspects and may approve/reject, but never stamps/issues.

## 2. Access

No change to instrument endpoints (GATC still 403 there, unchanged since spec 01). For
applications/inspections, this step is intentionally **narrower** than every other official role,
by design (§9 D7):

- `GET /api/gatc/eligible`, `GET /api/gatc/{organization_id}/users`: `LM_OFFICER` only — the sole
  role that ever schedules (§4).
- `GET /api/applications/{id}`, `PATCH /api/applications/{id}/status`: unchanged for every existing
  role; a `GATC` caller is admitted **only** for the one application they are the
  `assigned_officer_id` of (checked directly against the path's `application_id`, not via
  `scope_applications` — see §9 D8 for why). Every other `GATC` caller still gets a flat 403,
  exactly as before this step.
- `GET /api/inspections/{id}`, `PATCH /api/inspections/{id}`, `POST /api/inspections/{id}/submit`:
  same pattern, keyed on `inspection_id`.
- `POST /api/applications/{id}/certificate`, `PATCH /api/applications/{id}/inspection`
  (reschedule), `PATCH /api/applications/{id}/review-checklist`: unchanged, `LM_OFFICER`-only.

## 3. Data model (migration `0013_gatc_eligibility`)

### `organizations.gatc_eligible_category_ids` (new column)

| column | type | notes |
|---|---|---|
| `gatc_eligible_category_ids` | JSONB, nullable | array of `instrument_categories.id` values |

- Nullable forever, no backfill: `NULL` means "not configured for GATC eligibility" (every
  organization, before this step). A `CHECK` constraint (`gatc_eligible_only_for_gatc_org`)
  enforces it can only be non-`NULL` on a `type = 'GATC'` organization.
- **`none_as_null=True`** on the SQLAlchemy `JSONB` type (`app/models/organization.py`) —
  load-bearing, not cosmetic: without it, SQLAlchemy writes a Python `None` as the JSON literal
  `'null'::jsonb`, not SQL `NULL`, which silently fails the `CHECK` constraint above (`'null'::jsonb
  IS NULL` is `false`) and would make `services/gatc.py: list_eligible()`'s own
  `.isnot(None)`/`IS NULL` filtering wrong. Caught by the very first test run against a real
  Postgres `CheckViolation` — see §12.

### `inspections.assignee_role` (new column + new enum type)

| column | type | notes |
|---|---|---|
| `assignee_role` | enum (`LM_OFFICER`, `GATC`) | added nullable, backfilled `LM_OFFICER`, then `NOT NULL` |

- Same 3-step "nullable -> backfill -> `NOT NULL`" sequence as `0009_transportability`'s own
  `instruments.transportable` — but unlike that column's *assumed* backfill value, this one is a
  **known fact**: every `Inspection` row that exists before this migration was created by the
  pre-spec-15 `services/applications.py: transition()`, which only ever let `LM_OFFICER` reach
  `DOCUMENT_REVIEW -> SCHEDULED` and always self-assigned the caller. `LM_OFFICER` is not a guess
  for these rows; it is what they already are.
- New enum type, added via `ADD COLUMN` on an existing table — same pattern as `0009`'s own
  `verification_mode` (an explicit `CREATE TYPE` before `ADD COLUMN`, since SQLAlchemy only
  auto-issues one as part of `CREATE TABLE`).

## 4. Enum placement (`app/core/gatc_types.py`)

**Decision (see §9 D1):** `InspectionAssigneeRole` (`LM_OFFICER`, `GATC`) lives in its own new
sibling module, mirroring `core/verification_types.py`'s own precedent (spec 14 §4/D3): it's a
narrow, two-value, denormalized *snapshot* concept, not a fit for `core/roles.py` (the caller's own
account role, five values, used everywhere for RBAC) or `core/application_types.py`.

**Type choice — real Postgres `Enum`, not a CHECK-constrained `Text` column.** Surveying this
codebase's existing small closed-value columns: `ChecklistResult`, `VerificationMode`,
`PaymentStatus`, `OrgType`, and `Role` itself are all real `Enum(...)` columns. `CheckConstraint` is
used throughout, but only for cross-field/format invariants — `state_code`'s regex, `capacity > 0`,
`org_matches_role` (role ↔ organization_id), the new `gatc_eligible_only_for_gatc_org` above —
never to restrict one column to a small fixed set of strings; that job already has a consistent,
established tool. `assignee_role` follows the existing convention.

```python
class InspectionAssigneeRole(StrEnum):
    LM_OFFICER = "LM_OFFICER"
    GATC = "GATC"
```

No `*_LABELS` dict: `ChecklistResult` sets the precedent that a small, self-evident, model-owned
enum needs no meta-exposed label mapping.

## 5. Backend implementation

```
app/core/gatc_types.py            InspectionAssigneeRole
app/models/organization.py        + gatc_eligible_category_ids (JSONB, none_as_null=True) + CHECK
app/models/inspection.py          + assignee_role (Enum, NOT NULL)
app/services/scoping.py           + scope_organizations(); scope_applications() gains a GATC branch
app/services/gatc.py              list_eligible(), list_org_gatc_users(), resolve_gatc_assignment(),
                                   is_assigned_gatc_for_application(), is_assigned_gatc_for_inspection()
app/schemas/gatc.py                GatcEligibleOrgOut, GatcOrgUserOut
app/routers/gatc.py                GET /gatc/eligible, GET /gatc/{organization_id}/users
app/main.py                        registers gatc.router
app/schemas/application.py         StatusChange gains gatc_organization_id/gatc_user_id (paired);
                                    InspectionOut gains assignee_role
app/schemas/inspection.py          InspectionDetail gains assignee_role
app/services/applications.py       ALLOWED_TRANSITIONS: GATC added to the three inspection-stage
                                    edges; transition()'s SCHEDULED branch resolves the assignee
app/routers/applications.py        GET/PATCH .../status: a new _reader_or_assigned_gatc dependency
app/routers/inspections.py         GET/PATCH/submit: _reader_or_assigned_gatc / _officer_or_assigned_gatc
alembic/versions/0013_gatc_eligibility.py
```

### `services/gatc.py: resolve_gatc_assignment()` — validation and status codes

Called from `services/applications.py: transition()`'s `SCHEDULED` branch only when
`body.gatc_organization_id` is provided. Two deliberately distinct failure shapes:

- **422 (`Unprocessable`)** for a reference that is simply wrong, nonexistent, or outside the
  officer's own jurisdiction: an unknown `gatc_organization_id`, an org that isn't `type=GATC`, or a
  `gatc_user_id` that isn't an active `GATC`-role member of that exact org. This mirrors this
  codebase's existing "unknown `category_id` -> 422" (spec 16) / "unknown `item_key` -> 422" (spec
  06/11) convention for a mutation body naming something that doesn't exist. The organization
  lookup is scoped through `scope_organizations()` (§6), so "wrong jurisdiction" and "doesn't
  exist" both collapse into the same 422 — this is request-body validation, not a resource `GET`,
  so `scope_*`'s own "out of scope -> 404" convention (which is about loading a resource by id)
  doesn't apply verbatim here.
- **409 (`Conflict`)** for a reference that is entirely valid on its own, but not allowed for this
  application's current state: the org exists and is `GATC`, but isn't configured for this
  instrument's category, or the application's `verification_mode` is `ON_SITE`. Mirrors "Document
  review checklist incomplete" / "must be submitted before approving" — legitimate references
  blocked by a business rule, not bad references.

## 6. Jurisdiction scoping (`services/scoping.py: scope_organizations()`)

New helper, mirroring `scope_instruments()`'s exact state/district rule, applied to
`Organization.state_code`/`district_code` instead of `Instrument`'s: `SUPER_ADMIN` unrestricted,
`STATE_ADMIN` by state, `DISTRICT_ADMIN`/`LM_OFFICER` by state+district, everything else `false()`.
Used by both `GET /api/gatc/eligible` (which GATC orgs even appear in the allocation dropdown) and
`resolve_gatc_assignment()` (§5) — an officer can never target, or even discover the existence of,
a GATC organization outside their own jurisdiction. `BUSINESS`/`GATC` callers never reach this
(neither role ever schedules or looks up GATC orgs).

## 7. `scope_applications()` — the GATC branch

```python
if user.role == Role.GATC:
    return stmt.where(Application.inspection.has(Inspection.assigned_officer_id == user.id))
```

Deliberately the **narrowest** scoping rule of any role in this codebase: not jurisdiction-wide
like `LM_OFFICER`/`DISTRICT_ADMIN`, not org-wide like `BUSINESS` — exactly the one application (if
any) this specific person has been assigned to inspect. A GATC organization may have several
staff; only the individual named in `Inspection.assigned_officer_id` may see or act on that
application, mirroring `assigned_officer_id`'s own existing "a specific person" semantics (spec 06
D1) rather than granting the whole org visibility.

`Application.inspection.has(...)` is a correlated `EXISTS`, not a `JOIN` — it never collides with a
join some other caller path may already have added to the same statement (e.g.
`list_applications()`'s own explicit `outerjoin(Application.inspection)` for `sort=scheduled_asc`),
and needs no special-casing in `scope_inspections()`/`scope_documents()`, which already delegate to
`scope_applications()`.

**Consequence, not a special case:** the existing "approve/reject is open to any in-scope officer,
not just the one who ran the inspection" wording (spec 07 D1) still holds verbatim for `GATC` in
`ALLOWED_TRANSITIONS` — but because GATC's own *scope* is per-assignment, "any in-scope GATC user"
mechanically narrows to "the one assigned GATC user." No extra code enforces this; it falls out of
the scoping rule above.

## 8. Router-level plumbing — why two extra dependencies, not a role-set addition

The straightforward approach — add `Role.GATC` to the existing `Reader` dependencies on
`GET/PATCH /applications/{id}...` and `GET/PATCH/POST /inspections/{id}...` — was tried first and
rejected: it flips the HTTP status for an **unrelated** GATC caller from `403` to `404` (since
`scope_applications`'s "out of scope -> 404, never 403" convention would then run for a role the
endpoint hadn't previously admitted at all), which breaks a wide swath of pre-existing, unmodified
RBAC tests that pin an exact `403` for GATC — e.g. `test_applications_rbac.py::test_read_endpoints`,
`test_applications_transitions.py::test_evaluation_order` /
`test_approve_reject_role_and_scope`, `test_applications_stats.py::test_rbac`,
`test_inspection_start.py::test_start_role_rejected`,
`test_inspection_checklist.py::test_patch_non_officer_role_rejected`.

The fix: `routers/applications.py: _reader_or_assigned_gatc()` and the analogous pair in
`routers/inspections.py` check the path's own `application_id`/`inspection_id` **directly** (via
`services/gatc.py: is_assigned_gatc_for_application()`/`is_assigned_gatc_for_inspection()`) *before*
falling through to `Forbidden`. Every existing role's behavior is byte-for-byte unchanged (they
still pass via the original `role in READER_ROLES` check); an unrelated `GATC` caller still hits
the same `Forbidden` (403) it always did; only the one assigned `GATC` user is newly admitted, and
only for that one application/inspection. `GET /applications` (list) and `GET /applications/stats`
are deliberately left untouched (still flat 403 for every `GATC` caller, §9 D6) since neither has
an id in its path to check against.

## 9. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | `assignee_role` enum home | New sibling module `core/gatc_types.py`, mirroring spec 14 D3's reasoning (§4). |
| D2 | `assignee_role` type: real Postgres `Enum` or CHECK-constrained `Text`? | **Real `Enum`** (`inspection_assignee_role`) — matches every other small closed-value column in this codebase (`ChecklistResult`, `VerificationMode`, `PaymentStatus`, `OrgType`, `Role`); `CheckConstraint` here is reserved for cross-field/format invariants, never single-column enum restriction (§4). |
| D3 | Does `assignee_role` need continuous re-validation against the live `users.role`? | **No — set once, at assignment, never re-checked.** Confirmed safe by reading every write path in `services/users.py`/`routers/users.py`: no endpoint mutates `role` after a user is created (the only `role =` assignment anywhere in the codebase is a deliberate, test-only DB mutation in `tests/test_tokens.py` to exercise JWT-claim staleness — a scenario that already independently invalidates the user's token, unrelated to `assignee_role`). Since a user's role can never change, a denormalized snapshot of it can never go stale. |
| D4 | Backfill `assignee_role` for pre-existing `Inspection` rows, or leave `NULL`? | **Backfill `LM_OFFICER` and set `NOT NULL`** — unlike spec 14's `verification_mode` (a true snapshot of a *past instant* that can't be reconstructed), this is a known, provable fact about every existing row: the pre-spec-15 code path that created them only ever self-assigned an `LM_OFFICER` caller. |
| D5 | Add a write endpoint for `gatc_eligible_category_ids` in this step? | **No.** Not requested by the task, and this step's own "minimal but real" framing is specifically about making *routing* real, not building an org-management console. Configured directly in the database (or a future seed) until a dedicated step adds a write path — the same posture spec 16 already takes for `instrument_categories` itself (no write endpoint, DB/migration-seeded only, though that table is truly static reference data while this column is per-org configuration a human will eventually need to edit — flagged here as the clearest gap this step leaves for a follow-up). |
| D6 | Extend evidence-photo upload/`GET /applications` (list)/`GET /applications/stats` to admit GATC too? | **No**, deliberately. Evidence photos are optional (`inspections_service.submit()` never requires them), so a GATC inspection is fully completable without them; extending `documents.py`'s `Uploader` role-set would (like the `Reader` case in §8) flip pre-existing `GATC -> 403` RBAC assertions in `test_applications_rbac.py::test_owner_only_endpoints` to `404`. The list/stats endpoints have no per-request id to gate on, so the only options were "flat admit" (wrong — leaks nothing today but is unnecessary surface) or "flat deny" (chosen, matches every pre-existing test, and nothing in this step's requirements needs a GATC work-queue view). |
| D7 | Should `BUSINESS` see `GET /api/gatc/eligible`? | **No.** A business never chooses how its own application is routed (that's the Controller/officer's call per the domain rules); exposing a list of GATC organization names/jurisdictions to an applicant who cannot act on it is a pure information leak with no offsetting benefit. Admin roles are excluded too — they don't schedule, and this is a live operational lookup tied to the act of scheduling, not a reporting surface. |
| D8 | How to keep `GATC -> 403` (not 404) for an unrelated application, while still admitting the one assigned GATC user, on the very same endpoints? | **A purpose-built router dependency that checks the specific path id directly** (§8), not a `scope_applications`-mediated role-set addition. This was the crux of making "reuse the existing endpoints" and "don't break any pre-existing RBAC test" simultaneously true. |
| D9 | JSONB `None` vs. `CHECK ... IS NULL` | **`none_as_null=True`** on `gatc_eligible_category_ids`'s SQLAlchemy type (§3) — without it, a Python `None` is written as `'null'::jsonb`, which fails an `IS NULL` check (both the new `CHECK` constraint and `list_eligible()`'s own filter). Caught immediately by a real `CheckViolation` against local Postgres — exactly the kind of bug `TEST_DATABASE_URL` against a real database (not SQLite/mocks) is meant to surface. |

## 10. Confirmation: this reuses the existing machinery, not a parallel one

- **Checklist/measurements:** `services/inspections.py: patch()`/`submit()` are completely
  unmodified. Their only authorization check, `_require_assigned_officer_not_submitted()`
  (`inspection.assigned_officer_id != user.id`), was already role-agnostic and needed no change to
  work correctly for a `GATC` assignee.
- **Starting an inspection:** `transition()`'s existing `if target == S.INSPECTION and
  application.inspection.assigned_officer_id != user.id: raise Forbidden(...)` check — also already
  keyed on identity, not role — required no change beyond `GATC` joining that edge's `roles` set.
- **Approve/reject:** the existing "any in-scope officer, checklist must be submitted first" logic
  in `transition()` is untouched; `GATC` joining those two edges' `roles` sets, combined with
  `scope_applications`'s new (narrower) GATC branch, is the entire change (§7).
- **Certificate issuance:** completely untouched — still `LM_OFFICER`-only, still triggered the same
  way, regardless of which role ran the inspection that led to `APPROVED`.

The only genuinely new logic is allocation-time: resolving *which* person a schedule should target
(`services/gatc.py`), and the router-level gate that lets that one person reach the otherwise
unmodified endpoints (§8).

## 11. Tests (backend)

New file `tests/test_gatc_eligibility.py` (27 tests, parametrized):
- `GET /api/gatc/eligible`: correct orgs for a category, jurisdiction scoping (a same-state
  different-district org is excluded), role gating (`LM_OFFICER` only), required `category_id`,
  anonymous 401.
- `GET /api/gatc/{organization_id}/users`: active-`GATC`-users-only filtering, 404 for a non-GATC
  org / out-of-jurisdiction org / unknown id.
- **(a)** `test_schedule_self_assigns_lm_officer_unchanged` — explicit regression: omitting
  `gatc_organization_id`/`gatc_user_id` self-assigns exactly as before, `assignee_role=LM_OFFICER`.
- **(b)** `test_schedule_with_eligible_gatc_succeeds` — valid eligible org+user,
  `OFFICE_TEST_CENTRE` application -> success, `assignee_role=GATC`.
- **(c)** `test_schedule_gatc_not_eligible_for_category_is_409`.
- **(d)** `test_schedule_gatc_rejected_for_on_site_application` — rejected even though the org is
  otherwise category-eligible.
- **(e)** `test_schedule_gatc_rejected_without_instrument_category` — an old-style (pre-spec-16,
  no `category_id`) application can't use GATC routing.
- Bad-reference 422s: unknown org, a `BUSINESS` org passed as `gatc_organization_id`,
  out-of-jurisdiction org, unknown user, a user from a *different* org, an inactive user, missing
  pairing, and fields sent on a non-`SCHEDULED` target.
- **(f)** `test_assigned_gatc_can_start_perform_and_approve` /
  `test_assigned_gatc_can_reject` — the assigned GATC user (and only that user — a second,
  unrelated `GATC` user is proven 403 at every step) can view, start (`SCHEDULED -> INSPECTION`),
  fill the checklist/measurements, submit, and approve/reject, entirely via the pre-existing,
  unmodified endpoints.
- **(g)** covered by the jurisdiction-scoping assertion in the `eligible` test above.
- **(h)** the full pre-existing suite (467 tests as of spec 16) passes completely unmodified — see
  §12.

## 12. Acceptance criteria

- [x] `0013_gatc_eligibility` round-trips locally (`downgrade base`, `upgrade head`, and a
  `downgrade -1`/`upgrade head` round-trip), `alembic check` reports no drift. **Not applied to
  Supabase.**
- [x] `organizations.gatc_eligible_category_ids` is nullable, CHECK-constrained to `GATC` orgs, and
  round-trips a real SQL `NULL` (not `'null'::jsonb`) via `none_as_null=True`.
- [x] `inspections.assignee_role` is `NOT NULL`, backfilled `LM_OFFICER` for every pre-existing row.
- [x] `GET /api/gatc/eligible` returns the right orgs for a category, scoped to the caller's
  jurisdiction; `LM_OFFICER`-only.
- [x] `DOCUMENT_REVIEW -> SCHEDULED` self-assigns `LM_OFFICER` exactly as before when no GATC
  fields are sent (explicit regression test).
- [x] A valid, eligible, `OFFICE_TEST_CENTRE` GATC routing succeeds; category-ineligible,
  `ON_SITE`, and no-`category_id` applications are all rejected (409); bad references are rejected
  (422).
- [x] The assigned GATC user — and only that user — can start/perform/approve-or-reject via the
  unmodified inspection endpoints.
- [x] Full backend test suite green: **494 passed** (467 pre-existing + 27 new), zero modifications
  to any pre-existing test file.
- [x] `ruff check`/`ruff format --check` clean.
- [x] `backend/CLAUDE.md` updated: migration table, API block, data-model subsection; root
  `CLAUDE.md`'s "GATC workflow depth" open decision marked resolved.

## 13. Verification record

Backend (`pytest`, local `lm_test` via `TEST_DATABASE_URL`): 494 passed (467 pre-existing + 27 new
in `tests/test_gatc_eligibility.py`). `ruff check .` and `ruff format --check .` both clean.

Migration tested with `alembic downgrade base && alembic upgrade head` (full 13-revision chain),
plus `alembic check` (no drift) and a `downgrade -1`/`upgrade head` round-trip specifically around
`0013`. **Supabase was never touched** — every command ran with `TEST_DATABASE_URL` explicitly
overridden to the local `lm_test` database; `backend/.env` was never read or modified.
