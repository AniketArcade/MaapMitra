# Spec 12 — Mocked payments, informational only (rev 1)

**Status:** Implemented, tested locally, **not yet applied to Supabase**
**Build order:** Step 12 (post-MVP addition, last of Phase 1's backend specs — after step 11's
document-review checklist, step 14's transportability, and step 13's certificate superseding)
**Depends on:** Spec 03 rev 2 (`Application` model, `services/applications.py: create()`/
`transition()`, the `ALLOWED_TRANSITIONS` map)

## 1. Goal

`../CLAUDE.md`'s **Open decisions** list has carried a single unresolved bullet since the MVP was
scoped: *"Payments: mocked in MVP (`payments` table only)"*. No table, no action, and no answer to
the obvious follow-up question — should payment status ever block anything? — existed until this
step.

**The explicit resolution, decided by the user, not inferred by this step:** add the table and a
mock-pay action so the concept exists and is visible on the application, but make it **purely
informational**. Payment status never gates any existing status transition. This is deliberately
the simplest possible resolution of the long-open decision — not a partial implementation waiting
for a follow-up step.

**This is the single most important thing to understand about this spec.** A future reader who
sees `payments`/`payment_status` in the schema and assumes it must gate something (the way
`document_review_checklist_items` gates `DOCUMENT_REVIEW → SCHEDULED`, or the way the document
checklist gates `DRAFT → SUBMITTED`) would be wrong. It doesn't, on purpose. See §7 D1 for why.

**Out of scope:**
- Any gating of `services/applications.py: ALLOWED_TRANSITIONS`/`transition()` on payment status,
  in either direction. No edge anywhere reads `Payment`.
- A real payment gateway, a fee schedule, or any amount computation. `amount` exists as a nullable
  column with no writer in this step (see §3, §7 D3).
- A dedicated `GET /payments/{id}` (or similar) endpoint. A payment is only ever read nested inside
  `ApplicationDetail` — there's nothing to independently fetch.
- Multiple payments per application, refunds, partial payments, or a payment history/ledger. One
  row per application, exactly like `certificates`/`inspections`.

## 2. Access

No new role beyond what already exists. `POST /api/applications/{id}/mock-pay` is `BUSINESS`
(owner) only — the same `Owner` dependency (`require_roles(Role.BUSINESS)`) the existing
`PATCH`/`DELETE /applications/{id}` endpoints already use. Every other role gets a uniform 403 at
the router, before any scope check ever runs (same precedent as every other single-role-gated
endpoint in this codebase, e.g. `reschedule_inspection`). `ApplicationDetail.payment` is read-only,
computed on every response — no request body ever sets it directly.

## 3. Data model (migration `0011_payments`)

### `payments` (new table)

| column | type | notes |
|---|---|---|
| `id` | UUID PK | `UUIDPk` mixin, same as every other table |
| `application_id` | UUID, NOT NULL, unique FK → `applications.id`, `ON DELETE CASCADE` | one row per application |
| `amount` | `Numeric(10,2)`, nullable | see §7 D3 |
| `status` | enum `payment_status` (`NOT_PAID`, `PENDING`, `PAID`), NOT NULL, default `NOT_PAID` | |
| `paid_at` | timestamptz, nullable | set only once `status` becomes `PAID` |
| `created_at` / `updated_at` | `Timestamps` mixin | |

- **`ON DELETE CASCADE`, not `RESTRICT`** (unlike `certificates`, which uses `RESTRICT`): a
  certificate is only ever issued for a terminal, undeletable application, so `RESTRICT` there is
  defensive-only. A `payments` row can exist while an application is still `DRAFT` (this step adds
  no status-based restriction on when `mock-pay` may be called — see §4), and `DRAFT` applications
  *can* be deleted (`services/applications.py: delete()`). A mocked, informational payment record
  has no independent reason to survive its own application being deleted, so it cascades, the same
  way `documents`/`application_status_history` already do.
- **Brand-new enum type (`payment_status`), created together with its owning table in one
  `CREATE TABLE`.** This is the simplest of the three enum-migration patterns this codebase now
  has precedent for: `0001`-`0003`/`0006` create a type as part of `CREATE TABLE` (SQLAlchemy
  auto-issues `CREATE TYPE` as a DDL event attached to `Table.create()`); `0009` creates a
  brand-new type via a bare `ADD COLUMN` on an *existing* table (needing an explicit
  `Enum(...).create()` first, since a bare `add_column` doesn't trigger the DDL event);
  `0005`/`0008`/`0010` add a *value* to an *existing* type (`ALTER TYPE ... ADD VALUE`, with its
  own transactional caveats). `payments` is a brand-new table *and* a brand-new type together, so
  it's the `0001`-`0003`/`0006` case: no explicit `CREATE TYPE` step needed, the whole migration
  stays one `CREATE TABLE` call, one transaction.
- No index beyond the unique constraint on `application_id` — every read of a `payments` row is a
  single-row lookup by that column, reached only through its owning application (see §5).

## 4. `services/payments.py: mock_pay()`

```
def mock_pay(db, user, application_id, *, ip) -> Application:
    application = applications_service.load(db, user, application_id, for_update=True)
    if user.role != Role.BUSINESS:            # belt-and-suspenders; router already blocks this
        raise Forbidden(...)
    payment = db.scalar(select(Payment).where(Payment.application_id == application.id))
    if payment is None:
        payment = Payment(application_id=application.id, status=PAID, paid_at=now())
        db.add(payment)
    elif payment.status != PAID:
        payment.status, payment.paid_at = PAID, now()
    audit.log(..., action="PAYMENT_MOCKED", details={"status": ..., "created": ...})
    db.commit()
    return application
```

- **No status precondition.** Unlike every other mutating action in `services/applications.py`
  (which check `application.status` before proceeding), `mock_pay()` never checks the
  application's current status. It can be called on a `DRAFT` application, a `CERTIFICATE_ISSUED`
  one, or anything in between — consistent with "purely informational": if payment status doesn't
  gate a transition, there's also no reason to gate *when* the mock-pay action itself may run.
- **Scoping:** entirely inherited from `applications_service.load()`. Out-of-org business → 404
  (never 403), exactly like every other endpoint. No `scope_payments()` helper was added to
  `services/scoping.py` — a payment is only ever reached through its owning application, the same
  reasoning `scope_certificates()`/`scope_inspections()` already document for themselves (both
  simply `.join(Application, ...)` onto `scope_applications()` rather than defining an independent
  rule). Since this step adds no `GET /payments/{id}`, there is no place such a helper would even
  be called from.
- **Locking discipline:** the parent `Application` row is locked (`for_update=True`) *before* the
  `Payment` row is looked up. This is what makes the whole action idempotent under a race, without
  needing a second `with_for_update()` on `Payment` itself: two concurrent mock-pay calls for the
  same application serialize on the application row lock, so whichever acquires it second always
  sees the first caller's already-committed `Payment` row when it runs its own `select()` —
  eliminating the insert race entirely, rather than merely catching an `IntegrityError` from the
  unique constraint after the fact.

## 5. Schemas

- `app/schemas/payment.py: PaymentOut` — `{status, amount, paid_at}`. No `id`/`application_id`:
  unlike `CertificateOut`/`InspectionOut` (each independently fetchable via their own `GET
  .../{id}`, so a flat `id` is useful), `PaymentOut` is nested inside `ApplicationDetail` only and
  has nothing to flatly reference.
- `ApplicationDetail.payment: PaymentOut | None` — `null` until the first `mock-pay` call (the row
  doesn't exist yet), not a zero-value `{status: "NOT_PAID", ...}` object. **Not** added to
  `ApplicationOut` (the list/summary schema) — matches how `certificate`/`inspection` detail are
  also `ApplicationDetail`-only, not surfaced on the list view.
- `app/core/payment_types.py: PaymentStatus` (`NOT_PAID`/`PENDING`/`PAID`) and
  `PAYMENT_STATUS_LABELS` — a new sibling module, same reasoning spec 14 §4/§9 D3 already used for
  `verification_mode`: this enum needs a labels dict for `GET /applications/meta`'s
  `payment_statuses` (the frontend must never hardcode it), which rules out following
  `certificate.py`'s own precedent of defining `CertificateStatus` directly on the model with no
  labels dict at all. It isn't a property of `Application` or `Instrument` either, so
  `core/application_types.py`/`core/instrument_types.py` aren't a fit.
- `ApplicationMeta.payment_statuses: list[LabelledValue]` — built the same way
  `verification_modes`/`statuses` already are.

## 6. Backend implementation

```
app/core/payment_types.py           PaymentStatus, PAYMENT_STATUS_LABELS
app/models/payment.py               Payment (application_id unique FK CASCADE, amount, status, paid_at)
app/models/application.py           + payment: Mapped["Payment | None"] relationship (lazy="raise")
app/models/__init__.py              registers Payment for Alembic autogenerate
app/services/payments.py            mock_pay()
app/services/applications.py        _scoped(): + joinedload(Application.payment)
app/schemas/payment.py              PaymentOut
app/schemas/application.py          ApplicationDetail.payment; ApplicationMeta.payment_statuses
app/routers/applications.py         POST /applications/{id}/mock-pay (Owner = BUSINESS only)
alembic/versions/0011_payments.py
```

No changes to `services/applications.py: ALLOWED_TRANSITIONS`/`transition()` — see §1 and §7 D1.

## 7. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Should payment status gate any existing transition (e.g. `Accept`, `Schedule`, `Certificate issue`)? | **No — explicit user decision, not an oversight.** This is the one deliberate constraint the task brief called out by name: `ALLOWED_TRANSITIONS`/`transition()` are untouched. `tests/test_payments.py::test_payment_never_gates_the_lifecycle` drives an application all the way to `CERTIFICATE_ISSUED` with zero `payments` rows ever created, proving this in code rather than only in a doc comment. |
| D2 | Create-vs-upsert for `mock_pay()`: always insert a fresh row, or look up and update an existing one? | **Look up first, then insert-or-update** — never both. A `payments` row is created once, lazily, on the first mock-pay call; every subsequent call for the same application updates that same row (or, since it's already `PAID`, no-ops). Idempotent via lock ordering (§4): locking the parent `Application` row before the `Payment` lookup means two racing calls can never both try to insert, so the unique `application_id` constraint is a backstop, not the primary idempotency mechanism. |
| D3 | Does `mock_pay()` accept or compute an `amount`? | **No — left `null`/unset.** No real payment gateway or fee schedule exists anywhere in this codebase to derive a number from (**ASSUMPTION**, same caveat every invented MVP value in this codebase carries). The column exists (nullable) so a future real integration can populate it without a schema change, but this step's mock action has nothing meaningful to put there. |
| D4 | Single-step direct-to-`PAID`, or `PENDING` first then flipped to `PAID` in the same call? | **Single step, direct to `PAID`.** There is no real payment gateway to await a response from, so writing `PENDING` and then immediately overwriting it with `PAID` in the same request would add a state transition with no observable difference to any caller — unnecessary complexity for an MVP mock. `PENDING` stays in the enum (for a plausible future real integration) but this action never produces it. |
| D5 | `payments.application_id`'s `ON DELETE` behavior: `CASCADE`, `RESTRICT`, or `SET NULL`? | **`CASCADE`**, unlike `certificates`' `RESTRICT`. A certificate is only ever issued for a terminal, undeletable application (`RESTRICT` there is purely defensive); a `payments` row can exist against a still-`DRAFT` application, which *can* be deleted, and a mocked/informational payment has no reason to outlive it — same behavior `documents`/`application_status_history` already have via cascade. |
| D6 | Enum home for `PaymentStatus`: on the `Payment` model directly (`CertificateStatus`'s precedent), or a `core/*_types.py` sibling module (`VerificationMode`'s precedent)? | **Sibling module** (`core/payment_types.py`), because this step needs a `*_LABELS` dict for `GET /applications/meta`'s `payment_statuses` entry — a requirement `CertificateStatus` never had (nothing exposes certificate-status labels via meta), which is what makes `VerificationMode`'s precedent the closer fit despite `Payment` otherwise resembling `Certificate` (both: one row per application, own status enum). |
| D7 | Should a `scope_payments()` helper be added to `services/scoping.py`? | **No.** This step adds no endpoint that reads a `Payment` row independently of its application — `mock_pay()` reaches it exclusively through `applications_service.load()`'s existing scope, and `ApplicationDetail.payment` rides the same already-scoped query every other nested field (`certificate`, `inspection`) does. A `scope_payments()` helper would have no caller. |

## 8. Tests (backend)

New file `tests/test_payments.py`:
- **(a)** `test_mock_pay_success` / `test_application_detail_payment_null_before_mock_pay`: the
  owning `BUSINESS` user can call mock-pay; the application's `payment.status` becomes `PAID` with
  `paid_at` set; before the call, `ApplicationDetail.payment` is `null` (not a zero-value object).
- **(b)** `test_mock_pay_wrong_org_is_404`: a different `BUSINESS` org gets 404, and no `Payment`
  row is created.
- **(c)** `test_mock_pay_non_business_roles_forbidden`: every non-`BUSINESS` role
  (`LM_OFFICER`/`GATC`/`DISTRICT_ADMIN`/`STATE_ADMIN`/`SUPER_ADMIN`) gets 403.
- **(d)** `test_mock_pay_twice_is_idempotent`: a second call is a 200 no-op — same `PAID` status,
  same `paid_at` (compared as parsed datetimes, not raw strings, since a value read back through a
  fresh session can print with a different UTC offset than the one just written in-process) — and
  exactly one `payments` row exists throughout, proven with a direct DB count.
- **(e)** `test_meta_includes_payment_statuses`: `GET /applications/meta` serves
  `payment_statuses` matching `PAYMENT_STATUS_LABELS` exactly.
- **(f)** `test_payment_never_gates_the_lifecycle`: an `APPROVED` application (built without ever
  calling mock-pay) is issued a certificate via the existing `POST
  /applications/{id}/certificate` endpoint and reaches `CERTIFICATE_ISSUED` — `payment` stays
  `null` and zero `payments` rows exist throughout. This is the direct proof of §1/§7 D1's
  "informational only" constraint holding in code, not just documented as intent.

## 9. Acceptance criteria

- [x] `0011_payments` round-trips locally (`downgrade base`, `upgrade head`, and a
  `downgrade -1`/`upgrade head` round-trip specifically around `0011`), `alembic check` reports no
  drift. **Not applied to Supabase** — an explicit later step.
- [x] `POST /api/applications/{id}/mock-pay`: owner succeeds, non-owner business 404s, every
  non-`BUSINESS` role 403s, calling it twice is safe and idempotent (one row, same `paid_at`).
- [x] `GET /applications/meta` serves `payment_statuses`; nothing hardcodes the labels
  client-side.
- [x] `services/applications.py: ALLOWED_TRANSITIONS`/`transition()` are byte-for-byte unchanged
  by this step (verified by inspection, and by the full pre-existing suite passing unmodified).
- [x] An application can reach `CERTIFICATE_ISSUED` with `payment` `null`/untouched the entire
  time — proven by a dedicated test, not just asserted in prose.
- [x] `ruff check`/`ruff format --check` clean; full backend test suite green (448, up from 441:
  441 pre-existing + 7 new in `tests/test_payments.py`).
- [x] `../CLAUDE.md`'s "Payments" open-decision bullet marked resolved (not deleted), describing
  what was built and stating explicitly that it's informational-only by user decision.
  `backend/CLAUDE.md` updated: migration table (`0011`, explicitly marked not-yet-applied to
  Supabase), data model section (`payments` entry), a new "Payments — mocked, informational only"
  subsection, and the API block.

## 10. Verification record

Backend (`pytest`, local `lm_test` via `DATABASE_URL`/`TEST_DATABASE_URL` both pointed at
`postgresql+psycopg://localhost/lm_test`): 448 passed (441 pre-existing + 7 new in
`tests/test_payments.py`). `ruff check .` and `ruff format --check .` both clean.

Migration tested with `alembic downgrade base && alembic upgrade head` (full chain), plus
`alembic check` (no drift) and a `downgrade -1`/`upgrade head` round-trip specifically around
`0011`. **Supabase was never touched** — every command in this step ran with `DATABASE_URL`
explicitly overridden to the local `lm_test` database (env vars beat `.env`); `backend/.env` was
never read or modified. Applying `0011` to Supabase is an explicit, separate, later step per the
task brief's safety rule.
