# Spec 13 — Certificate superseding + expiring-soon (rev 1)

**Status:** Implemented, tested locally, **not yet applied to Supabase**
**Build order:** Step 13 (post-MVP addition, after step 11's document-review checklist and step
14's transportability — this task was assigned on top of both)
**Depends on:** Spec 08 rev 1 (`Certificate` model, `services/certificates.py: issue()`'s
double-issue-race lock ordering), Spec 09 rev 1 (`core/certificate_status.py: effective_status()`,
`PublicVerifyOut`'s "complete field set" contract), Spec 10 rev 1 (`GET
/admin/certificates/stats`, the `EXPIRY_REMINDER_30D_DAYS` threshold)

## 1. Goal

Two gaps existed around certificate lifecycle:

1. **No superseding concept.** When a re-verification issues a new certificate for an instrument
   that already has one, the old certificate just sits there, still `VALID`, with no link to the
   certificate that replaced it. A viewer (or the public verify page) has no way to know "this
   isn't current anymore, here's the one that is."
2. **"Expiring soon" only existed inside the reminder job.** `services/certificates.py:
   expiry_check()` and `services/admin.py: certificate_stats()`/`expiring_soon()` each
   independently compute "VALID and `valid_until` within `EXPIRY_REMINDER_30D_DAYS`," but nothing
   on `CertificateOut` itself told a consumer (e.g. the business portal's own certificate detail
   view) that a specific certificate is in that window, without re-implementing the threshold
   check client-side or hitting an admin-only endpoint.

This step adds both: a `SUPERSEDED` certificate status plus a `supersedes_certificate_id` /
`superseded_by_certificate_id` self-referential chain, set automatically by `issue()` whenever a
new certificate is issued for an instrument that already has one; and an `is_expiring_soon`
computed field, backed by a new `core/certificate_status.py: is_expiring_soon()` sibling function
to the existing `effective_status()`.

**Out of scope:**
- Any new endpoint. Superseding happens automatically inside the existing `POST
  /applications/{id}/certificate`; `is_expiring_soon` rides the existing `CertificateOut`.
- A revoke action (still not built, same as spec 08/09/10 left it).
- Backfilling `supersedes_certificate_id`/`superseded_by_certificate_id` for certificates issued
  before this migration. Nothing in the pre-existing data establishes which certificate replaced
  which (there was no snapshot of "the instrument's previous certificate" until now), so those
  columns are simply `NULL` for every pre-migration row — the same "an honest `NULL` beats a
  fabricated value" reasoning spec 14 D2 already used for `verification_mode`.
- Changing `effective_status()`'s existing REVOKED-wins/EXPIRED contract in any way, including for
  `SUPERSEDED` — see §4 D3 below. This was an explicit constraint on the task, not just a
  convenience.

## 2. Access

No new role or endpoint. Superseding is entirely internal to `services/certificates.py: issue()`
(`LM_OFFICER`-only, unchanged from spec 08). `is_expiring_soon` is read-only, computed on every
`CertificateOut.from_model()` call — no request body ever sets it.

## 3. Data model (migration `0010_certificate_superseding`)

### `certificate_status` (enum, altered)
Gains `SUPERSEDED`. Existing values (`VALID`, `EXPIRED`, `REVOKED`) unchanged.

### `certificates.supersedes_certificate_id` / `certificates.superseded_by_certificate_id` (new columns)
| column | type | notes |
|---|---|---|
| `supersedes_certificate_id` | UUID, nullable | FK → `certificates.id`, `ON DELETE SET NULL` |
| `superseded_by_certificate_id` | UUID, nullable | FK → `certificates.id`, `ON DELETE SET NULL` |

- **`ON DELETE SET NULL`, not `RESTRICT` or `CASCADE`:** nothing in this codebase hard-deletes a
  `Certificate` row today (spec 08's own model docstring: "created once ... and never altered
  afterward except by the expiry job ... or a revoke action"), so this is defensive rather than
  load-bearing — but a self-referential chain should never be the thing that blocks or cascades a
  future delete of a certificate row, so `SET NULL` was chosen over `RESTRICT`/`CASCADE` even
  though no code path exercises it yet.
- **Enum-add pattern mirrors `0005`/`0008`** (`ALTER TYPE certificate_status ADD VALUE IF NOT
  EXISTS 'SUPERSEDED'`, combined with the column adds in one migration/transaction): the new value
  is never inserted, defaulted, or compared within this same migration — the two `ADD COLUMN`
  statements reference `certificates.id`, never `certificate_status` — so the same safety
  reasoning `0008`'s own comment documents (and `backend/CLAUDE.md`'s migration section doesn't
  contradict) applies here too. `0009`'s enum situation doesn't apply — that was a *brand-new*
  type needing an explicit `CREATE TYPE`; `certificate_status` already exists, so this is a value
  add like `0005`/`0008`, not a type create like `0009`.
- **FKs added via `add_column` + a named `create_foreign_key`**, mirroring `0005`'s
  `inspections.submitted_by` pattern: `Table.create()` auto-issues FK constraints as part of
  `CREATE TABLE`, but a bare `op.add_column` on an existing table does not, so the constraint must
  be created explicitly. The naming convention (`fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`,
  `app/db/base.py: NAMING_CONVENTION`) already includes the column name, so the two
  self-referential FKs (`certificates` → `certificates` twice, once per column) get distinct
  constraint names (`fk_certificates_supersedes_certificate_id_certificates` and
  `fk_certificates_superseded_by_certificate_id_certificates`) without a collision.
- Downgrade drops both FKs/columns but — same documented limitation as `0005`/`0008` — leaves the
  `SUPERSEDED` enum value in place (Postgres has no `ALTER TYPE ... DROP VALUE`); `downgrade -1`
  after this revision does not fully reverse the enum change.

## 4. Backend implementation

```
app/models/certificate.py           CertificateStatus.SUPERSEDED; Certificate gains
                                     supersedes_certificate_id / superseded_by_certificate_id
app/core/certificate_status.py      + is_expiring_soon() (additive sibling to effective_status())
app/services/certificates.py        issue(): supersede lookup + lock + flip, in the same
                                     transaction as the new certificate's insert
app/schemas/certificate.py          CertificateOut gains supersedes_certificate_id,
                                     superseded_by_certificate_id, is_expiring_soon
app/schemas/public.py               PublicVerifyOut gains instrument_uid, issued_by
app/schemas/admin.py                AdminCertificateStats gains superseded
alembic/versions/0010_certificate_superseding.py
```

### `services/certificates.py: issue()` — the supersede step

Inside the existing lock/re-check block (the one spec 08 §4 already documents for the double-issue
race guard), immediately after re-confirming the application is still `APPROVED`:

1. Look up the instrument's **most recent certificate of any status** — `join(Application,
   Application.id == Certificate.application_id).where(Application.instrument_id ==
   locked.instrument_id).order_by(Certificate.created_at.desc()).limit(1)`, locked with
   `.with_for_update(of=Certificate)` (the joined `Application` row is already locked by the
   outer `with_for_update()` above; `of=Certificate` avoids re-locking it redundantly) and the
   same `execution_options(populate_existing=True)` discipline every re-check lock in this
   codebase uses.
2. If one exists **and its status is not already `SUPERSEDED`**: the new certificate's
   `supersedes_certificate_id` is set to it; after the new row is inserted (see the flush-ordering
   note below), the previous row's `status` flips to `SUPERSEDED` and its
   `superseded_by_certificate_id` is set to the new certificate's id.
3. If no previous certificate exists, or the most recent one is already `SUPERSEDED` (a state that
   shouldn't arise through this code path alone, since the most recently issued certificate for an
   instrument should never itself be `SUPERSEDED` — but defensively checked anyway, see §7 D5):
   `supersedes_certificate_id` stays `NULL` and no other row is touched.
4. All of this happens in the **same transaction** as the existing insert — no second `db.commit()`
   was added. The `except BaseException: db.rollback(); ...; raise` block already wrapping the
   insert now also covers the supersede flip.

**Flush-ordering detail (discovered while testing, not in the original task brief):** both
`certificate_id` (the new row's PK) and the previous row's `superseded_by_certificate_id` value
are plain Python `uuid.UUID`s assigned directly to columns — not an ORM relationship — so
SQLAlchemy's unit-of-work has no dependency graph to infer that the previous row's `UPDATE` must
follow the new row's `INSERT`. Without an explicit `db.flush()` between `db.add(certificate)` and
setting `previous.superseded_by_certificate_id = certificate_id`, SQLAlchemy could emit the
`UPDATE` before the `INSERT`, which Postgres's (non-deferred) FK constraint correctly rejects —
this was caught by the new tests, not anticipated up front. The fix is a single `db.flush()` right
after `db.add(certificate)`, guarded so it only runs when there's actually a previous certificate
to supersede (no wasted round-trip on every first-ever issuance).

### `core/certificate_status.py: is_expiring_soon()`

```python
def is_expiring_soon(status: CertificateStatus, valid_until: date, *, today: date) -> bool:
    if effective_status(status, valid_until, today=today) != CertificateStatus.VALID:
        return False
    return valid_until <= today + timedelta(days=get_settings().EXPIRY_REMINDER_30D_DAYS)
```

Added **alongside** `effective_status()`, not inside it — `effective_status()`'s own body is
byte-for-byte unchanged except for an explanatory docstring addition (see §4 D3). Reuses the exact
threshold `services/admin.py: certificate_stats()`/`expiring_soon()` and
`services/certificates.py: expiry_check()` already use, so there is exactly one place that
threshold is read from settings for any "is this expiring soon" check anywhere in the codebase.

## 5. Schemas

### `CertificateOut` (authenticated certificate detail/list — `GET /certificates/{id}`, admin
`expiring-soon`)

Gains:
- `supersedes_certificate_id: uuid.UUID | None`
- `superseded_by_certificate_id: uuid.UUID | None`
- `is_expiring_soon: bool`

**Decision: raw FK ids, not nested refs.** The task brief offered both options and pointed at
`InstrumentOut.active_application` (`ActiveApplicationRef`, a small nested `{id,
application_number, status}` object) as the precedent to check. Looked at it, and chose the
opposite for this schema specifically: `CertificateOut` **already** exposes `application_id` as a
bare `uuid.UUID`, with no `ApplicationRef` nesting it, even though the same "give the frontend a
display label + status without a second fetch" argument could apply there too. `ActiveApplicationRef`
exists because `InstrumentOut` needs to show *a different entity type's* number/status inline on
the instrument screen; `CertificateOut`'s own convention for referencing *anything* — including
its own parent application — is a flat id. A same-type certificate → certificate link fits that
existing flat convention better than introducing the first nested ref this schema has ever had,
and the frontend already has `GET /certificates/{id}` to resolve the linked certificate's own
details when it actually needs them (exactly how it would resolve `application_id` today).

### `PublicVerifyOut` (`app/schemas/public.py`)

Gains exactly two fields, per the task's explicit authorization to deviate from spec 09 §5's
"complete field set" wording:

- **`instrument_uid: str`** — the instrument's permanent public identifier (spec 02). Not owner
  PII, not an internal database id: it's already printed on the certificate PDF, which anyone
  holding the certificate number can already reach via the very fact that they're looking this
  certificate number up. Useful for a verifier cross-checking the instrument's own marking against
  the certificate.
- **`issued_by: str`** — a display label for the approving officer, read from
  `Certificate.snapshot["approved_by_name"]` — a field spec 08 already computes and stores at
  issuance time (`services/certificates.py: _snapshot()`), not invented fresh for this schema.
  Falls back to `""` if absent (defensive only; `issue()` always populates it since a certificate
  can't be issued from a non-`APPROVED` application, which by definition has an `APPROVED` history
  entry).

**Deliberately NOT added:** `supersedes_certificate_id`, `superseded_by_certificate_id`,
`is_expiring_soon`. Reasoning, per field:
- **Chain fields:** exposing them on the public endpoint would mean leaking another certificate's
  internal id — a kind of reference `PublicVerifyOut` has never exposed (it doesn't even expose
  its *own* `id`, only `certificate_number`) — purely to restate information the certificate's own
  `status` field already carries. A superseded certificate's public page already shows `status:
  "SUPERSEDED"` (via `effective_status()`, unchanged); that's the actionable signal a verifier
  needs ("don't trust this one, ask for the current certificate"), not the specific id of whatever
  replaced it. Adding "here's the certificate that replaced this one" as a clickable/copyable
  reference is a plausible future feature, but it's a product decision about how much of the chain
  to expose publicly, not something this step should silently add under the "extend
  `PublicVerifyOut`" banner.
- **`is_expiring_soon`:** this is a `VALID`-only nuance aimed at the certificate holder (the
  business), who already gets the 30-day and 7-day reminder emails from the expiry job (spec 10)
  and can see it live once it rides `CertificateOut` in their own portal. A public verifier's
  relevant question is binary — "is this certificate currently valid?" — which `status` (via
  `effective_status()`) already answers precisely with `VALID`/`EXPIRED`/`REVOKED`/`SUPERSEDED`.
  "Valid but expiring in 12 days" and "valid with two years left" both read as `VALID` to a public
  verifier today, and that's an intentional level of detail, not an oversight this step should fix
  in passing.

This reasoning is recorded here **and** in `PublicVerifyOut`'s own docstring and in
`backend/CLAUDE.md`'s public-verify subsection, so spec 09 §5's "never add a field here without
checking spec 09 §5/§10 D4 first" instruction has a paper trail explaining the deviation rather
than being silently overridden.

### `AdminCertificateStats` (`app/schemas/admin.py`)

Gains `superseded: int`, populated the same way `revoked`/`expired` already are — a
`by_status.get(CertificateStatus.SUPERSEDED, 0)` lookup against the existing grouped-count query
in `services/admin.py: certificate_stats()`. No service-layer change was needed there: the query
already groups by whatever `Certificate.status` values exist, so `SUPERSEDED` rows fall into their
own bucket automatically once the enum value and the schema field both exist.

## 6. Tests (backend)

New file `tests/test_certificate_superseding.py`:
- First-ever certificate for an instrument: both link fields `null`, `is_expiring_soon` `false`.
- Second certificate for the same instrument: `supersedes_certificate_id` points at the first;
  the first flips to `SUPERSEDED` with `superseded_by_certificate_id` pointing at the second;
  `is_expiring_soon` on the now-superseded first certificate is `false` regardless of its
  `valid_until`; the `CERTIFICATE_ISSUED` audit row's `details.supersedes_certificate_id` matches.
- Third certificate: chains off the second (most recently issued), not the first; the first's own
  `superseded_by_certificate_id` is untouched by the third issuance.
- The literal "not already SUPERSEDED" guard: forces a certificate into `SUPERSEDED` directly
  (bypassing `issue()`, simulating an edge case the normal flow shouldn't produce) and confirms a
  subsequent issuance doesn't try to re-link it.
- **Atomicity:** monkeypatches `audit.log` to raise after the supersede flip and the new row are
  staged but before `db.commit()`, then confirms the previous certificate's `status`/
  `superseded_by_certificate_id` are unchanged and the new certificate row was never persisted —
  mirroring the rollback discipline `tests/test_certificates.py:
  test_issue_certificate_double_issue_race` already exercises for the pre-existing double-issue
  guard.
- `is_expiring_soon` via the live API surface at the `EXPIRY_REMINDER_30D_DAYS` boundary (unit-level
  boundary coverage lives in the new `tests/test_certificate_status.py`, see below).

New file `tests/test_certificate_status.py` — pure unit tests, no DB:
- `effective_status()`: every existing case (`VALID` far out, `VALID` exactly on the due date,
  `VALID` past due → `EXPIRED`, already-`EXPIRED` stays `EXPIRED`, `REVOKED` wins even when not
  past due, `REVOKED` wins even when *also* past due) plus one new case pinning that `SUPERSEDED`
  is deliberately **not** special-cased (falls through the same date rule as any other non-`REVOKED`
  status) — the explicit regression check that step 13 didn't alter this function's existing
  contract.
- `is_expiring_soon()`: `false` well outside the window, `true` exactly at the
  `EXPIRY_REMINDER_30D_DAYS` boundary, `true` one day inside it, `false` one day outside it,
  `false` for `EXPIRED`/`REVOKED`/`SUPERSEDED` even when `valid_until` is technically inside the
  window (since `effective_status()` wouldn't call any of those `VALID`).

Extended existing files:
- `tests/test_public_verify.py`: `FIELDS` gains `instrument_uid`/`issued_by`; the success test
  asserts their values; a new `test_public_verify_superseded_status` confirms a `SUPERSEDED`
  certificate's public `status` reads `SUPERSEDED` and the field set stays exactly `FIELDS` (no
  chain/expiring-soon leakage).
- `tests/test_admin_certificates.py`: the zero-filled/inclusive stats test now issues a fifth
  certificate, forces it to `SUPERSEDED`, and asserts the new `superseded` bucket in both the
  empty and populated responses.

## 7. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | `certificate_status` enum add: combined with the column adds in one migration, or split? | **Combined**, mirroring `0005`/`0008`'s own precedent (the enum-add's "new value never used within this transaction" safety condition holds here — the new columns reference `certificates.id`, never `certificate_status`). See §3. |
| D2 | `CertificateOut`'s new id fields: raw ids or nested refs (`ActiveApplicationRef`-style)? | **Raw ids.** `CertificateOut` already exposes `application_id` flatly with no nested ref; a same-type self-link fits that existing convention better than introducing this schema's first nested ref. See §5. |
| D3 | Does `effective_status()` need a `SUPERSEDED`-wins branch (parallel to `REVOKED`-wins)? | **No — explicitly out of scope.** The task required `effective_status()`'s existing contract to be provably unchanged; adding any new branch, even one that only affects `SUPERSEDED` certificates, would change its return value for the (superseded-and-past-due) case it currently maps to `EXPIRED`. `is_expiring_soon()` was added as a strictly additive sibling instead, and a direct unit test now pins that `SUPERSEDED` falls through the ordinary date rule unchanged. |
| D4 | `PublicVerifyOut`: exactly which fields, and why not the chain/expiring-soon too? | **`instrument_uid` and `issued_by` only**, per the task's explicit authorization. Both are non-PII, already-computed values (spec 02's public instrument id; spec 08's `approved_by_name` snapshot). The supersede chain and `is_expiring_soon` were judged to add no actionable information a public verifier doesn't already get from `status` alone, at the cost of exposing an internal certificate id this endpoint has never exposed. See §5. |
| D5 | What if the instrument's most-recently-issued certificate is somehow already `SUPERSEDED` when a new one is issued? | **Skip linking it — the new certificate's `supersedes_certificate_id` stays `NULL`.** This shouldn't arise through `issue()` alone (each issuance only ever supersedes the single most-recent row, so that row should never itself be `SUPERSEDED` at the moment it's "most recent"), but the task's literal wording ("if one exists and its status is not already SUPERSEDED") was implemented as a defensive check rather than assumed away, and a test forces the state directly to exercise it. |
| D6 | Flush ordering between the new certificate's `INSERT` and the previous certificate's `UPDATE`. | **Explicit `db.flush()`** after `db.add(certificate)`, only when there's a previous row to supersede. Both FK values involved are plain client-generated UUIDs, not ORM relationships, so SQLAlchemy's unit-of-work has no dependency graph to order them correctly on its own — discovered via the new atomicity/chaining tests failing with a `ForeignKeyViolation`, not anticipated in the original design. See §4. |

## 8. Acceptance criteria

- [x] `0010_certificate_superseding` round-trips locally (`downgrade base`, `upgrade head`, and a
  `downgrade -1`/`upgrade head` round-trip specifically around `0010`), `alembic check` reports no
  drift. **Not applied to Supabase** — an explicit later step.
- [x] Issuing a second certificate for an instrument that already has one supersedes it: both link
  fields set correctly, the old row's status flips, all in one transaction (proven atomic via a
  simulated mid-transaction failure).
- [x] Issuing a certificate for an instrument with no prior certificate leaves both link fields
  `null` and does not error.
- [x] `is_expiring_soon` is correct at the `EXPIRY_REMINDER_30D_DAYS` boundary and is `false` for
  `EXPIRED`/`REVOKED`/`SUPERSEDED` certificates even when `valid_until` is technically inside the
  window.
- [x] `effective_status()`'s existing REVOKED-wins/EXPIRED contract is provably unchanged (direct
  unit tests covering every pre-existing case, all passing unmodified).
- [x] `PublicVerifyOut` gains exactly `instrument_uid` and `issued_by`; does not leak the
  supersede chain or `is_expiring_soon`.
- [x] `GET /admin/certificates/stats` includes a `superseded` bucket.
- [x] `ruff check`/`ruff format --check` clean; full backend test suite green (441, up from 420:
  420 pre-existing + 21 new across `tests/test_certificate_superseding.py` (11) and
  `tests/test_certificate_status.py` (15) minus overlap, plus the extensions to
  `tests/test_public_verify.py`/`tests/test_admin_certificates.py` — see the task's final report
  for the exact breakdown).
- [x] `backend/CLAUDE.md` updated: migration table (`0010`, explicitly marked not-yet-applied to
  Supabase), data model section (`certificates` entry gains the chain fields and `SUPERSEDED`),
  certificate status line, a new "Certificate superseding + expiring-soon" subsection, and the
  public-verify subsection's field list plus an explicit note on the spec 09 §5 deviation.

## 9. Verification record

Backend (`pytest`, local `lm_test` via `TEST_DATABASE_URL`): 441 passed (420 pre-existing + 21
new/changed). `ruff check .` and `ruff format --check .` both clean.

Migration tested with `alembic downgrade base && alembic upgrade head` (full chain) against
`lm_test`, plus `alembic check` (no drift) and a `downgrade -1`/`upgrade head` round-trip
specifically around `0010`. **Supabase was never touched** — no command in this step ran against
`backend/.env`'s `DATABASE_URL`; applying `0010` to Supabase is an explicit, separate, later step
per the task brief's safety rule.
