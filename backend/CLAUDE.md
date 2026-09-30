# Backend — FastAPI

Project-wide rules are in `../CLAUDE.md`. This file covers the backend only.

## Commands

> ⚠️ Assumed defaults. Update if the setup differs.

```bash
python3.12 -m venv .venv && source .venv/bin/activate   # Python 3.12; Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000  (docs: /docs)
pytest                               # needs local Postgres DB lm_test (see Testing)
ruff check . && ruff format .
alembic revision --autogenerate -m "msg"
alembic upgrade head
python -m app.seed --password '...'  # demo data (see database/seed/README.md)
python -m app.cli create-superadmin --email you@example.com
python -m app.cli create-bucket         # private documents bucket (once per environment)
```

## Structure

```text
backend/
├── app/
│   ├── main.py            # app factory, CORS, middleware, routers, error handlers
│   ├── core/              # config, security, deps, roles, errors, rate limits, enums, regions
│   ├── db/                # engine, session, base + mixins
│   ├── middleware/        # body_limit.py (upload size, before multipart parsing)
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic request/response models (requests extend StrictModel)
│   ├── services/          # business logic, scoping.py, status transitions, audit
│   ├── routers/           # thin route handlers
│   │   ├── health.py  auth.py  users.py  instruments.py  applications.py  documents.py
│   │   ├── inspections.py  # checklist/measurements (step 6)
│   │   ├── certificates.py  # GET {id}, GET {id}/pdf (step 8; POST lives in applications.py)
│   │   ├── public.py  # GET /public/verify/{certificate_number}, no auth (step 9)
│   │   ├── jobs.py  # POST /jobs/expiry-check, X-Cron-Secret only (step 10)
│   │   └── admin.py  # GET /admin/certificates/{stats,expiring-soon}, ADMIN_ROLES (step 10)
│   ├── storage/           # Storage protocol: SupabaseStorage (REST) + MemoryStorage (tests)
│   ├── email/              # EmailSender protocol: ResendEmail (REST) + MemoryEmail (tests), step 10
│   ├── pdf/               # certificate.py — ReportLab PDF + segno QR (step 8)
│   ├── cli.py             # create-superadmin, create-bucket
│   ├── seed.py            # demo data (python -m app.seed --password ...)
│   └── seed_files.py      # tiny generated demo PDF/PNG
├── alembic/
├── tests/
├── requirements.txt
└── .env.example
```

## Environment (`.env`)

```env
DATABASE_URL=postgresql+psycopg://...        # Supabase connection string
JWT_SECRET=...
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=7
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...                # backend only, NEVER expose
SUPABASE_BUCKET=documents
STORAGE_BACKEND=supabase                     # supabase | memory (memory = tests only)
PUBLIC_BASE_URL=https://<app>.vercel.app     # used in QR codes
CORS_ORIGINS=http://localhost:3000,https://<app>.vercel.app
EMAIL_BACKEND=resend                         # resend | memory (memory = local dev/tests, step 10)
RESEND_API_KEY=...
RESEND_FROM_EMAIL=...                        # required when EMAIL_BACKEND=resend
CRON_SECRET=...
ENV=development                              # development | test | production (cookie Secure flag, seed guard)
TRUSTED_PROXY_HOPS=0                         # proxies appending X-Forwarded-For; measure on deploy
APP_TIMEZONE=Asia/Kolkata                    # scheduling "today" (step 5); ASSUMPTION: deployment serves India
SCHEDULING_MAX_DAYS_AHEAD=180                # typo guard on scheduled_date
EXPIRY_REMINDER_30D_DAYS=30                  # step 10, ASSUMPTION: not a real Legal Metrology rule
EXPIRY_REMINDER_7D_DAYS=7                    # step 10, ASSUMPTION: not a real Legal Metrology rule
```

Load it through `pydantic-settings` in `core/config.py`. Never read `os.environ` scattered around the code.

- `DATABASE_URL`, `JWT_SECRET` (≥32 chars) and `CRON_SECRET` are required: the app refuses to start without them.
- With `STORAGE_BACKEND=supabase` (the default), `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are required too; placeholders are rejected at startup. Local commands against `lm_dev`/`lm_test` can set `STORAGE_BACKEND=memory`.
- Same shape for email (step 10): with `EMAIL_BACKEND=resend` (the default), `RESEND_API_KEY` and `RESEND_FROM_EMAIL` are required at startup. Local dev without a real Resend account can set `EMAIL_BACKEND=memory`.
- In `.env`, never put a `# comment` on the same line as an empty value: python-dotenv reads the comment as the value.
- `SUPABASE_URL` is normalised to its origin, so a pasted `…/rest/v1` (Data API) URL still works.
- Configuration errors (`ConfigError`) name the field and reason only, never values.
- `TRUSTED_PROXY_HOPS`: `get_client_ip` (in `core/deps.py`) takes the Nth `X-Forwarded-For` entry from the right. Never trust the leftmost entry. Measure the real hop count (Vercel rewrite → Render) on first deploy.
- Use Supabase's **Session pooler** URL (port 5432, `*.pooler.supabase.com`). The direct host is IPv6-only (Render can't reach it); the transaction pooler (6543) breaks psycopg prepared statements.

## Migrations

`backend/.env` points at **Supabase**. For local work, override it: `DATABASE_URL=postgresql+psycopg://localhost/lm_dev` (env vars beat `.env`).

Workflow for every schema change:
1. `alembic revision --autogenerate -m "<name>" --rev-id <NNNN>` against local `lm_dev`.
2. Hand-review it. Autogenerate misses enum drops in `downgrade`, sequences (create and drop) and data migrations.
3. Round-trip locally: `upgrade head` → `downgrade -1` → `upgrade head`, then `alembic check` (no drift).
4. `pytest` (migrates `lm_test` from scratch).
5. **Claude applies it to Supabase** (`alembic upgrade head` with the default `.env`), verifies with `alembic current` and `alembic check`, then re-runs the seed if needed. The seed is idempotent.
6. Record it in the table below. From then on the migration is **frozen**: never edit it, write a new one.

| Revision | Name | Applied to Supabase |
|---|---|---|
| `0001` | auth (organizations, users, refresh_tokens, audit_logs) | 2026-09-30 (demo seed run the same day) |
| `0002` | instruments (+ `instrument_uid_seq`, 3 enums, functional unique index) | 2026-09-30 (seed: `OTH-0001`) |
| `0003` | applications, application_status_history, documents (+ `application_number_seq`, 3 enums, partial unique index) | 2026-09-30 (bucket `documents` created; seed: `APP-2026-000001` for `OTH-0001`) |
| `0004` | inspections (+ `ix_inspections_officer_date`) | 2026-09-30 (no seed changes; scheduling is driven live in the demo) |
| `0005` | inspection checklist (`inspection_checklist_items`, `inspection_measurements`, 3 new `inspections` columns, `checklist_result` enum, `document_type` gains `INSPECTION_EVIDENCE`) | 2026-09-30 (no seed changes; the field-inspection flow is driven live in the demo) |
| `0006` | certificates (+ `certificate_number_seq`, `certificate_status` enum) | 2026-09-30 (no seed changes; issuance is driven live in the demo) |
| `0007` | certificate reminders (`reminder_30d_sent_at`, `reminder_7d_sent_at`, both nullable `Date`) | 2026-09-30 (no seed changes; the expiry job is driven live in the demo) |
| `0008` | document review checklist (`document_review_checklist_items`, `application_status` enum gains `DOCUMENTS_DEFICIENT`) | **NOT YET APPLIED to Supabase** — written and tested locally against `lm_test` only (spec `docs/specs/11-document-review-checklist.md`) |

## Layering rules

- **Routers are thin.** They parse input, check auth, call a service and return a schema.
- **Services own the logic:** status transitions, org isolation, audit logging, certificate generation.
- **Pydantic schemas are separate from SQLAlchemy models.** Never return ORM objects directly.
- Every new endpoint needs a schema, an RBAC dependency, an audit log entry and at least one test.
- Every schema change goes through Alembic. **Never edit tables in the Supabase dashboard.**
- Type hints everywhere. Lint and format with `ruff`.
- **Every request schema extends `StrictModel`** (`schemas/common.py`, `extra="forbid"`): unknown fields → 422.
- **Every read of org-owned data goes through a `scope_*` helper** in `services/scoping.py` (`scope_instruments` today). Out of scope → 404 (`NotFound`), never 403. Scoping fails closed. Load the row with one scoped query; never load first and check ownership afterwards.
- Lists return `Page[T]` (`{items, total, page, page_size}`) with `Annotated[PageParams, Depends()]` (page ≥1, page_size ≤100) and a stable order (`created_at desc, id`).
- **Never let a client aggregate paged data itself** (counting `items` from a large `page_size` fetch is wrong past one page). Add a server-side stats/count endpoint that runs the same `scope_*` query grouped/counted in SQL — see `GET /applications/stats`.
- Rules that need the stored row (e.g. PATCH merged-state checks) raise `Unprocessable(msg, field=...)`, which returns FastAPI's 422 list shape.
- Enums, units and regions live in `core/instrument_types.py` and `core/regions.py`; application/document types in `core/application_types.py`. The frontend gets them from `GET /instruments/meta` and `GET /applications/meta`.
- **Row locks re-read:** every `with_for_update()` re-check uses `.execution_options(populate_existing=True)`. Otherwise the identity map returns the stale pre-lock copy.
- **Audit-writing GETs commit in the service** (e.g. `GET /documents/{id}/url` writes `DOCUMENT_URL_ISSUED`).

## Data model

Tables: `users`, `organizations`, `refresh_tokens`, `instruments`, `applications`, `documents`, `inspections`,
`inspection_checklist_items`, `inspection_measurements`, `document_review_checklist_items`,
`certificates`, `payments` (mocked), `audit_logs`

- `users`: DB check constraints tie `role` to `organization_id` (BUSINESS/GATC need one, officials must not) and require `state_code`/`district_code` for officials.
- `refresh_tokens`: SHA-256 `token_hash` only, never the raw token.
- `audit_logs`: append-only. Write rows through `services/audit.log(db, *, actor, action, entity_type, entity_id, organization_id, details, ip)` in the caller's transaction. Routers pass `ip=get_client_ip(request)`.
- `instruments` (spec `docs/specs/02-instruments.md`, lock activated by `docs/specs/05-officer-dashboard.md`):
  - `instrument_uid` = `LM-{state}-{district}-{nextval('instrument_uid_seq'):06d}`. It's global, so there are gaps. It's permanent, even if the location changes, and never a credential.
  - Global unique index `ix_instruments_mfr_serial` on `(lower(manufacturer), serial_number)`. The index is the duplicate check: catch the `IntegrityError` → 409. Serial numbers are stored uppercased.
  - Delete is blocked by `ON DELETE RESTRICT` once **any** application exists (→ 409).
  - **Locking:** `core/instrument_lock.py: locked_fields(active_status)` is the single source of truth, used by both the PATCH check and `InstrumentOut.locked_fields` (so the frontend disables exactly what the backend enforces — never re-derive the rule client-side). While a non-terminal application exists (DRAFT included), identity fields (manufacturer, model, serial_number, capacity, capacity_unit, accuracy_class, state_code, district_code) → 409. Once the application reaches SCHEDULED, INSPECTION or APPROVED, address/latitude/longitude lock too (409, a distinct message) — they stay editable through DRAFT/SUBMITTED/DOCUMENT_REVIEW. The lock lifts entirely at REJECTED or CERTIFICATE_ISSUED.
  - `InstrumentOut.active_application` (one LEFT JOIN); reported as `null` to officials while it's a DRAFT.
- `applications` (spec `docs/specs/03-applications.md`):
  - `application_number` = `APP-{UTC year}-{nextval('application_number_seq'):06d}`, display only.
  - One active (non-terminal) application per instrument: partial unique index `ux_applications_active_instrument`.
  - `state_code`/`district_code` are a snapshot of the instrument's location (locked while active).
  - `application_status_history` is append-only and feeds the timeline (businesses can't read `audit_logs`).
  - **Officials never see DRAFT applications or their documents** (`scope_applications`).
  - `scheduled_date` on `ApplicationOut`/`ApplicationDetail.inspection` comes from a LEFT JOIN/`contains_eager` on `inspections`, never a per-row query.
- `documents`: `storage_path` = `applications/{application_id}/{document_id}.{pdf|jpg|png}` (never a URL, never the user's filename). `content_type` is the **sniffed** type. Max 10 per application.
- `inspections` (spec `docs/specs/05-officer-dashboard.md`, extended by `docs/specs/06-inspection-checklist.md`): one row per application (`application_id` unique FK), created when `DOCUMENT_REVIEW → SCHEDULED` fires. `scheduled_date` (date only, no time slot — ASSUMPTION), `assigned_officer_id` (self-assign only in step 5: always the officer who scheduled it; also the only officer who may start/edit/submit the field inspection, step 6 D1). No `status` column — the application's own `status` stays the single source of truth. Index `(assigned_officer_id, scheduled_date)` doubles as the "my inspections" list: `GET /applications?status=INSPECTION&sort=scheduled_asc`. Step 6 adds `overall_remarks` (text, null), `submitted_at` (timestamptz, null — the single source of truth for "this checklist is locked"), `submitted_by` (FK → users, `ON DELETE RESTRICT`, null).
- `inspection_checklist_items` / `inspection_measurements` (spec `docs/specs/06-inspection-checklist.md`): one row per `CHECKLIST_TEMPLATES`/`MEASUREMENT_TEMPLATES` entry for the instrument's type (`core/inspection_templates.py`, ASSUMPTION — illustrative demo content), **snapshotted** when the inspection starts (`SCHEDULED → INSPECTION`) so a later template edit never changes an in-progress or already-submitted inspection. `inspection_checklist_items.result` is a nullable `checklist_result` enum (`PASS`/`FAIL`/`NA`); `inspection_measurements.expected_value` is `instrument.capacity * fraction` computed at start time, `observed_value` filled by the officer. Both `ON DELETE CASCADE` from `inspections`, unique on `(inspection_id, item_key)` / `(inspection_id, label)`.
- `document_review_checklist_items` (spec `docs/specs/11-document-review-checklist.md`,
  migration `0008`): one row per `DOCUMENT_REVIEW_CHECKLIST_TEMPLATE` entry (`core/document_review_templates.py`,
  ASSUMPTION — illustrative demo content, a single generic list, not per-instrument-type),
  **snapshotted** when the application enters `DOCUMENT_REVIEW` and **reset** (`checked = false`,
  not recreated) on a later re-entry via the `DOCUMENTS_DEFICIENT → SUBMITTED → DOCUMENT_REVIEW`
  loop. `ON DELETE CASCADE` from `applications`, unique on `(application_id, item_key)`.
  `DOCUMENT_REVIEW → SCHEDULED` is blocked (409) until every row's `checked` is `true`.
- `certificates` (spec `docs/specs/08-certificate-pdf-qr.md`): one row per application (`application_id` unique FK, `ON DELETE RESTRICT`), created by `services/certificates.py: issue()` — never through `transition()`. `certificate_number` = `LM-CERT-{UTC year}-{nextval('certificate_number_seq'):06d}`. `snapshot` (JSONB) freezes the instrument/business/approver fields shown on the PDF at issuance time — a deliberate JSONB blob, not relational rows like the checklist (it's one immutable bundle written once and always read whole, the opposite case from spec 06's checklist items), needed because the instrument unlocks (editable again) the moment the application reaches this terminal status. `valid_from`/`valid_until` = issue date + `CERTIFICATE_VALIDITY_YEARS` (Settings field, default 2 — ASSUMPTION, not a real Legal Metrology rule). `status` starts `VALID`; the expiry job (step 10) is the only thing that ever moves it, and only to `EXPIRED` — `REVOKED` has no writer anywhere yet (no revoke action exists). `pdf_path` = `certificates/{id}.pdf`, stored in the same single `SUPABASE_BUCKET` as documents (no new bucket). `data_hash`: SHA-256 hex of a fixed pipe-joined string of the certificate's own fields (`app/services/certificates.py: _data_hash()`) — a tamper-evidence fingerprint, not a cryptographic file signature (root `CLAUDE.md`'s "hash-based in MVP" decision). No `qr_token` column: the QR/public URL encodes `certificate_number` directly (see QR section below). `reminder_30d_sent_at`/`reminder_7d_sent_at` (migration `0007`, nullable `Date`): the expiry job's idempotency mechanism (see Expiry job below) — `NULL` means "not yet sent," never re-derived from a log.

- UUID primary keys everywhere. Human-readable IDs are for display only:
  - instrument `instrument_uid`: `LM-JH-DHN-000123`
  - certificate `certificate_number`: `LM-CERT-2026-000123`
- `instruments`: plain `latitude` / `longitude` columns (no PostGIS).
- `documents`: store `storage_path` only. **Never store public URLs.**

## Application status flow

```
DRAFT → SUBMITTED → DOCUMENT_REVIEW → SCHEDULED → INSPECTION
                  ⇄ DOCUMENTS_DEFICIENT       → APPROVED | REJECTED → CERTIFICATE_ISSUED
```

- Enforce it through an `ALLOWED_TRANSITIONS` map in `services/applications.py`: `(from, to) → Edge(roles, enabled)`. Later steps flip `enabled`.
- Enabled in step 3: DRAFT → SUBMITTED (BUSINESS, all required documents present), SUBMITTED → DOCUMENT_REVIEW (LM_OFFICER), DOCUMENT_REVIEW → REJECTED (LM_OFFICER, `note` 10–1000 chars).
- Enabled in step 5: DOCUMENT_REVIEW → SCHEDULED (LM_OFFICER, requires `scheduled_date`; §"Scheduling" below).
- Enabled in step 6: SCHEDULED → INSPECTION (LM_OFFICER, **and only the assigned officer** — `Edge(roles, enabled)` alone can't express that identity check, so `transition()` adds it explicitly; §"Field inspection" below).
- Enabled in step 7: INSPECTION → APPROVED / REJECTED (any in-scope LM_OFFICER, **not** assigned-officer-locked — unlike the checklist itself, deliberately, since it's frozen by then; gated on `inspections.submitted_at` being set; §"Approve/Reject" below).
- Enabled in step 11: DOCUMENT_REVIEW → DOCUMENTS_DEFICIENT (LM_OFFICER, `note` 10–1000 chars, same length rule as REJECTED's own `REJECT_NOTE_MIN` but a sibling `DEFICIENCY_NOTE_MIN` constant), DOCUMENTS_DEFICIENT → SUBMITTED (BUSINESS, the resubmit action — no extra validation). DOCUMENTS_DEFICIENT is **not terminal**; §"Document review checklist" below.
- `PATCH /applications/{id}/status` evaluation order: out of scope → 404; not an edge → 409 `Invalid status change`; wrong role → 403; not enabled → 409 `This action is not available yet`; edge rules → 409/422; apply (row lock, history row, audit row, one transaction).
- `ApplicationDetail.allowed_actions` lists the enabled edges the caller's role may take (requirements not considered).
- The status PATCH endpoint validates against that map and the caller's role. It never sets an arbitrary status.
- **APPROVED → CERTIFICATE_ISSUED happens in the same DB transaction** as certificate creation.
- REJECTED is terminal. Re-verification means a new application. DOCUMENTS_DEFICIENT is the one
  non-terminal "dead end" fix: the business resubmits into SUBMITTED, not a new application.

### Document review checklist (step 11, spec `docs/specs/11-document-review-checklist.md`)
- `document_review_checklist_items` (`app/models/document_review_checklist.py`, ASSUMPTION —
  illustrative demo content, `core/document_review_templates.py`): one row per
  `DOCUMENT_REVIEW_CHECKLIST_TEMPLATE` entry (a single generic 8-item list, not per-`InstrumentType`
  like the inspection checklist — document review checks the submission as a whole), unique on
  `(application_id, item_key)`.
- **Snapshotted when the application enters `DOCUMENT_REVIEW`** (`transition()`, mirroring spec 06's
  inspection-checklist snapshot timing): rows are created once; if the application later cycles
  `DOCUMENTS_DEFICIENT → SUBMITTED → DOCUMENT_REVIEW` again, the existing rows are **reset**
  (`checked = false`), never recreated — `item_key`/`label` stay snapshotted from the first pass
  (a later template edit never changes an application already under review), but the officer must
  re-verify every item against the resubmission.
- `PATCH /api/applications/{id}/review-checklist` (LM_OFFICER only, application must be
  `DOCUMENT_REVIEW`; 409 otherwise) toggles individual items — same partial-save shape as
  `PATCH /api/inspections/{id}` (unknown `item_key` → 422, no audit row per call).
- **`DOCUMENT_REVIEW → SCHEDULED` is additionally gated**: 409 `"Document review checklist
  incomplete: …"` unless every row for the application has `checked = true` — mirrors the "all
  required documents present" gate on `DRAFT → SUBMITTED`.
- `ApplicationDetail.review_checklist` and `GET /applications/meta`'s
  `document_review_checklist` (the template) follow the existing checklist-template meta pattern
  (`GET /inspections/meta`'s `checklist_templates`) — the frontend never hardcodes the list.
- Audit action: `DOCUMENT_REVIEW_STARTED` (`details.checklist_item_count`, `details.reset`).

Certificate status: `VALID` · `EXPIRED` · `REVOKED`

### Scheduling (step 5, spec `docs/specs/05-officer-dashboard.md`)
- `today()` in `core/clock.py` is the current date in `APP_TIMEZONE` (default `Asia/Kolkata`, ASSUMPTION), built on a separate `now_utc()` so tests can freeze time via `monkeypatch.setattr(clock, "now_utc", ...)` — there's no freezegun dependency. A UTC-only check would reject valid IST dates for up to 5h30m around midnight.
- `scheduled_date` on `StatusChange` is required for, and only allowed for, target `SCHEDULED`; must be between `today()` and `today() + SCHEDULING_MAX_DAYS_AHEAD` (default 180, a typo guard).
- **Lock order when a transaction needs both:** application row, then instrument row. The scheduling transition locks the instrument with a **bare** `SELECT ... FOR UPDATE` (not `instruments_service.get()`): that function's query joinedloads `Instrument.active_application` — the very `Application` row just mutated — and `for_update`'s `populate_existing=True` would re-hydrate it from its still-stale (pre-commit) DB value, silently reverting the in-memory status change. Whenever you add a second lock inside a transition, re-check this interaction rather than assuming eager-loaded service helpers are safe to reuse for a lock-only call.
- `PATCH /applications/{id}/inspection` (LM_OFFICER only, body `{scheduled_date}`) reschedules — only while SCHEDULED, same date is a no-op (no audit row), `assigned_officer_id` never changes.
- Audit actions: `INSPECTION_SCHEDULED`, `INSPECTION_RESCHEDULED`.
- `GET /applications` accepts `sort: "created_desc" | "scheduled_asc"` (422 on anything else); `scheduled_asc` needs an explicit `.outerjoin(Application.inspection)` + `contains_eager`, not `joinedload`, since ordering requires referencing that join directly.

### Field inspection (step 6, spec `docs/specs/06-inspection-checklist.md`)
- Starting (`SCHEDULED → INSPECTION`), editing (`PATCH /inspections/{id}`), evidence upload/delete and submitting are all gated to `inspections.assigned_officer_id == caller` — a stricter check than role/scope, since `scope_applications` already lets any in-jurisdiction officer read a non-DRAFT application. A non-assigned in-scope officer gets 403 `"Only the assigned officer can do this"`.
- Starting bulk-inserts one `inspection_checklist_items` row per `CHECKLIST_TEMPLATES[instrument.instrument_type]` entry and one `inspection_measurements` row per `MEASUREMENT_TEMPLATES[instrument.instrument_type]` fraction (`core/inspection_templates.py`), reading the instrument's `capacity`/`capacity_unit` under the same "application, then instrument" lock order as scheduling — a bare `SELECT ... FOR UPDATE`, never `instruments_service.get()`.
- `PATCH /inspections/{id}` applies only the checklist items/measurements named in the request body (partial saves); an `item_key`/`label` that doesn't match an existing row → 422. Locked (409) once `submitted_at` is set.
- `POST /inspections/{id}/submit`: 422 if any checklist item's `result` or measurement's `observed_value` is still null. Sets `submitted_at`/`submitted_by`; **does not** change `application.status` — it stays `INSPECTION` until step 7's Approve/Reject.
- Evidence photos reuse the `documents` upload/delete pipeline with `document_type=INSPECTION_EVIDENCE`, under different rules than a business document (`services/documents.py: _check_upload_allowed`): actor must be the assigned officer, application status must be `INSPECTION`, not yet submitted. Counted against a separate `MAX_EVIDENCE_PHOTOS` cap (`_count(..., evidence=True)`), independent of `MAX_DOCUMENTS`. `routers/documents.py`'s upload/delete dependency now admits `LM_OFFICER` as well as `BUSINESS` — the service enforces which actor may touch which `document_type`, since the router alone can no longer imply it.
- `BUSINESS_DOCUMENT_TYPES` (`core/application_types.py`) excludes `INSPECTION_EVIDENCE`: `ApplicationDetail.requirements` and `ApplicationMeta.document_types` iterate it instead of the full `DocumentType` enum, so evidence photos never appear as a business-facing document requirement.
- Audit actions: `INSPECTION_STARTED`, `INSPECTION_SUBMITTED` (`details.checklist_summary` = counts of PASS/FAIL/NA, computed by `core/inspection_templates.py: checklist_summary_counts()`, reused by step 7).

### Approve/Reject (step 7, spec `docs/specs/07-approve-reject.md`)
- Open to **any in-scope `LM_OFFICER`**, not just the officer who ran the inspection — safe because
  the checklist is already frozen (`inspections.submitted_at`) before a decision is ever possible.
- `transition()` refuses `INSPECTION → APPROVED`/`REJECTED` with **409** `"The inspection checklist
  must be submitted before approving or rejecting"` while `inspections.submitted_at is None`.
  `allowed_actions()` filters both out of the list under the same condition, so the UI never offers a
  button that would immediately 409 (mirrors the identity check's client/server pairing from step 6).
- `REJECTED`'s existing `REJECT_NOTE_MIN = 10` rule (step 3) applies unchanged, since it already keys
  off the target status, not the source. `APPROVED` takes an optional note, like every other
  non-`REJECTED` transition.
- No new audit action: the existing generic `APPLICATION_STATUS_CHANGED` row gains
  `details.checklist_summary` (via `inspections_service.checklist_summary(db, inspection_id)`) only for
  this pair, so the decision's audit trail carries the numbers the officer saw.
- `ApplicationDetail.inspection` (`InspectionOut`) gains `submitted_at` and `checklist_summary`
  (`{passed, failed, na}`, `null` until submitted) so `/applications/[id]` can show the checklist result
  inline before the officer decides, without a separate inspection fetch.
- Instrument location lock is unchanged by this step: `LOCATION_LOCK_STATUSES` already includes
  `APPROVED`, so the instrument stays locked until step 8 issues a certificate; `REJECTED` already falls
  outside it and unlocks immediately.

### Certificate issuance (step 8, spec `docs/specs/08-certificate-pdf-qr.md`)
- `APPROVED → CERTIFICATE_ISSUED` is `Edge(frozenset(), enabled=False)` in `ALLOWED_TRANSITIONS` —
  **system-only**, structurally unreachable through `transition()`/`PATCH .../status` for any role
  (empty `roles` frozenset). `POST /api/applications/{id}/certificate`
  (`services/certificates.py: issue()`) bypasses `transition()` entirely and does its own
  scope/role/status checks, open to **any in-scope `LM_OFFICER`** (spec 07 D1's reasoning again).
- Evaluation order matters here too: `applications_service.load()` (scope 404) runs **before** the
  role check, but in practice the router's `Officer` dependency (`require_roles(Role.LM_OFFICER)`)
  already rejects every non-officer with 403 before the handler body runs at all — the same behavior
  every other single-role-gated endpoint has (e.g. `reschedule_inspection`). Only an in-role,
  out-of-jurisdiction officer reaches the service's own scope check and gets 404.
- Mirrors `documents.py: upload()`'s lock ordering: the PDF is rendered and `storage.put()` happens
  **before** any row lock; the application row is then locked
  (`.with_for_update().execution_options(populate_existing=True)` — **do not** drop
  `populate_existing`, or a concurrent double-issue race silently inserts two `Certificate` rows,
  since the identity map would return the stale pre-lock `APPROVED` status to the second caller),
  re-checked, and the `Certificate` insert + status flip commit together.
- `applications_service.apply_certificate_issued(db, application, user, ip=ip)` (new, small) sets the
  status, writes the `ApplicationStatusHistory` row and the generic `APPLICATION_STATUS_CHANGED` audit
  row — kept in `services/applications.py` so the timeline UI and audit convention stay uniform.
  `services/certificates.py` separately writes a specific `CERTIFICATE_ISSUED` audit row
  (`entity_type="certificate"`, `details={certificate_number, valid_until, data_hash}`) — the same
  generic-plus-specific pairing `transition()` already uses for `INSPECTION_SCHEDULED`/`INSPECTION_STARTED`.
- `ApplicationDetail.certificate` (`CertificateOut | None`) mirrors `.inspection`: eager-loaded via
  `Application.certificate` (`lazy="raise"`, joinedloaded in `_scoped()`), so `/applications/[id]`
  shows the certificate summary without a second fetch once issued.
- `app/pdf/certificate.py`: `render()` (ReportLab, one page, in-memory `BytesIO`) and
  `qr_code_data_uri()`/`qr_png_bytes()` (`segno`, encoding the fixed QR URL below) — content list only,
  not a mandated legal layout (ASSUMPTION, same caveat `core/inspection_templates.py` carries).
  `CertificateOut.qr_code_data_uri` is regenerated fresh on every `GET`, from `certificate_number`
  alone (deterministic) — **never stored**, per the QR section below.
- Audit actions: `CERTIFICATE_ISSUED`, `CERTIFICATE_URL_ISSUED` (the latter on `GET
  /certificates/{id}/pdf`, mirrors `DOCUMENT_URL_ISSUED`, committed in the service).

## API

Base `/api`. REST + JSON.

```http
GET   /api/health                # liveness; ?db=true also pings DB (503 if down)
POST  /api/auth/{login,register,refresh,logout}   GET /api/auth/me
POST  /api/users                 # SUPER_ADMIN only; creates officials
GET   /api/instruments/meta      # types, units, accuracy classes, regions (any logged-in user)
CRUD  /api/instruments           # write: BUSINESS (own org); read: + officials in jurisdiction; GATC 403
CRUD  /api/applications          PATCH /api/applications/{id}/status
POST  /api/documents             GET   /api/documents/{id}/url     # signed URL
GET   /api/inspections/meta      GET   /api/inspections/{id}
PATCH /api/inspections/{id}      POST  /api/inspections/{id}/submit
GET   /api/certificates/{id}     GET   /api/certificates/{id}/pdf
POST  /api/applications/{id}/certificate   # LM_OFFICER only; issues a certificate while APPROVED
POST  /api/jobs/expiry-check     # requires X-Cron-Secret header, no rate limit (step 10)
GET   /api/admin/certificates/stats            # ADMIN_ROLES; {valid, expiring_soon, expired, revoked}
GET   /api/admin/certificates/expiring-soon    # ADMIN_ROLES; Page[CertificateOut], valid_until asc
GET   /api/public/verify/{certificate_number}                     # no auth
GET   /api/applications/meta       # types, statuses (lifecycle order), document types + requirements, upload limits, scheduling {timezone, max_days_ahead}, document_review_checklist (step 11)
CRUD  /api/applications            # write: BUSINESS, DRAFT only; read: + officials (non-DRAFT, jurisdiction)
GET   /api/applications/stats      # {total, by_status}: same scope_applications as the list, all 9 statuses zero-filled (step 11 adds DOCUMENTS_DEFICIENT)
GET   /api/applications?sort=      # created_desc (default) | scheduled_asc
PATCH /api/applications/{id}/inspection   # LM_OFFICER only; reschedule while SCHEDULED
PATCH /api/applications/{id}/review-checklist   # LM_OFFICER only, DOCUMENT_REVIEW only; toggle document-review checklist items (step 11)
DELETE /api/documents/{id}         # BUSINESS/DRAFT, or assigned LM_OFFICER/INSPECTION evidence (step 6)
```

### Public verify (step 9, spec `docs/specs/09-public-verify.md`)
- `PublicVerifyOut` (`app/schemas/public.py`) is the **complete** field list: `certificate_number`,
  `status`, `instrument_type_label`, `manufacturer`, `model`, `serial_number`, `valid_from`,
  `valid_until`. No owner PII (`organization_name`, `address`), no documents, no internal IDs
  (`id`, `application_id`), no `pdf_path`/`data_hash`. Never link to the certificate PDF from the
  public page either — the PDF's snapshot carries exactly the fields this endpoint withholds.
- `instrument_type_label` is resolved server-side from `TYPE_LABELS` (`core/instrument_types.py`,
  same dict `app/pdf/certificate.py` already uses) instead of a raw `InstrumentType` code, since the
  caller has no session and can't resolve a label via the auth-gated `GET /instruments/meta`.
- Computes status **live** via `core/certificate_status.py: effective_status(status, valid_until,
  today=...)`: `REVOKED` (stored) always wins, else `valid_until < today` → `EXPIRED`, else the stored
  status. This is why a certificate shows `EXPIRED` correctly even before the expiry job (step 10)
  next runs. `services/certificates.py: expiry_check()` calls the same function to decide what to
  persist, so the two are structurally guaranteed to agree — never re-derived separately.
- `services/certificates.py: public_verify()` — one indexed `certificate_number` lookup, no scope
  check (deliberately public), no joins (every field already lives in `certificates.snapshot`).
  404 `"Certificate not found"` if no row matches; exact string match, no normalization.
- No audit row written per verify (anonymous, high-volume, non-mutating — doesn't fit `audit_logs`'
  actor-centric shape).
- Rate-limited: `@limiter.limit("30/minute")` per IP (`core/rate_limit.py`'s existing `slowapi`
  `limiter`) — not just abuse prevention, `certificate_number`'s sequential format is enumerable.

### QR
- Encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`. Never localhost.
- The DB is the source of truth, never the PDF or QR.

### Expiry job (step 10, spec `docs/specs/10-expiry-job.md`)
- `POST /api/jobs/expiry-check`: no user, no JWT — authenticated by a shared secret header
  (`X-Cron-Secret`, `core/deps.py: require_cron_secret()`, `secrets.compare_digest` against
  `CRON_SECRET`) since it's called by an external scheduler (Render Cron / GitHub Actions — root
  `CLAUDE.md`'s own still-open decision on which one), not a person.
- `services/certificates.py: expiry_check()` scans every `VALID` certificate (one unbounded query —
  sized for the MVP, not batched/paginated) and, per certificate: sends the 30-day reminder if
  `valid_until <= today + EXPIRY_REMINDER_30D_DAYS` **and** `reminder_30d_sent_at is None`; same for
  the 7-day ("urgent") reminder against its own column; then flips `status` to `EXPIRED` via
  `effective_status()` (above) if it now evaluates to that.
- **Idempotent by construction, not by a log:** a `reminder_*_sent_at` column is only set once the
  send actually succeeds. Re-running the job the same day is a no-op for anything already sent; a job
  that's late by weeks still sends both reminders (whichever are still outstanding) and expires the
  certificate in one catch-up run, in that order — reminder before expiry.
- Each certificate is processed independently (own `try`/`except`, own commits): one certificate's
  email failure (or any other error) never blocks another's, and never blocks its own status flip —
  the flip and the email are independent outcomes. A failed send simply leaves its `sent_at` column
  `NULL` for the next run to retry.
- Recipients: every `BUSINESS` user in the certificate's `organization_id` (ordinarily one; not
  DB-enforced, so zero or several are both tolerated — zero is counted as `skipped_no_recipient`,
  never a crash).
- `CERTIFICATE_EXPIRED` is the only audit row this job writes (`actor=None`, the same "system actor"
  precedent `cli.py: create_superadmin()`'s own `USER_CREATED` row already uses) — reminder sends are
  **not** audited (anonymous-adjacent, high-volume, and `reminder_*_sent_at` is already their own
  record of what happened).
- Not rate-limited (see the API block above) — a daily scheduler isn't the kind of traffic
  `/auth/login`/`/public/verify`'s limits exist for.

### Admin (step 10, spec `docs/specs/10-expiry-job.md`)
- `GET /admin/certificates/{stats,expiring-soon}` are `ADMIN_ROLES`-only (`core/roles.py`, reused here
  for its first read endpoint) and jurisdiction-scoped through the existing `scope_certificates` — no
  new scoping helper. This is deliberately **just** the expiry slice, not the fuller "users, audit
  log" admin console root `CLAUDE.md`'s role table and this file's own `/admin` structure-tree comment
  once gestured at — neither was ever actually built; see spec 10 §1/§10 D1.
- `expiring_soon` in both responses means `status == VALID and valid_until <= today +
  EXPIRY_REMINDER_30D_DAYS` — the same threshold the reminder job itself uses, not a second
  independent number. `AdminCertificateStats.valid` is **inclusive** of `expiring_soon` (not a
  disjoint bucket): every expiring-soon certificate is still counted as valid.

## Auth and RBAC (spec: `docs/specs/01-login-rbac.md`)

- Protect endpoints with `Depends(require_roles(Role.X, ...))` from `core/deps.py`. The role hierarchy never grants permissions: list the allowed roles explicitly.
- `get_current_user` reloads the user from the DB on every request. It rejects inactive users and tokens whose `role`/`org_id` claims are stale.
- Services raise domain errors from `core/errors.py` (`AuthError`, `Forbidden`, `NotFound`, `Conflict`, `RateLimited`), never `HTTPException`.
- **Commit-then-raise:** after a security-relevant write (failed-login audit, token revocation), `db.commit()` before raising.
- Cookies: `lm_refresh` (httpOnly, `Path=/api/auth`) holds the refresh token; `lm_session=1` (httpOnly, `Path=/`) is a presence flag for the frontend `proxy.ts`.
- Refresh rotates on every call. A revoked token seen again within 10 s is a lost race (401, cookies kept); after that it revokes the user's whole token family.
- Rate limits are in-memory (`core/rate_limit.py`): login 5/min per email + 20/min per IP, register 10/hour per IP, public verify 30/min per IP (step 9). **Production shortcut:** resets on restart, not shared across instances.
- CORS: browser traffic normally arrives same-origin through the Next.js `/api/*` rewrite. CORS only matters for direct calls.

## Documents and storage

- `app/storage/`: `Storage` protocol; `SupabaseStorage` (REST via `httpx2`, service role key, no SDK) and `MemoryStorage` (tests). `get_storage()` picks one by `STORAGE_BACKEND`. The key is never logged (errors log the operation and status only).
- `BodySizeLimitMiddleware` (`app/middleware/body_limit.py`) runs before multipart parsing on `POST /api/documents`: no `Content-Length` → 411; over 10 MiB + 64 KiB → 413 without reading; streamed overflow → 413.
- Upload order: rate limit (60/hour/user) → scope + DRAFT + count pre-checks → read ≤10 MiB + 1 → sniff magic bytes (PDF/PNG/JPEG only) → `storage.put` **outside** any lock (failure → 502) → lock the application row, re-check DRAFT and count, insert, audit, commit → on any failure after `put`, best-effort delete of the object. Rare orphans are an accepted MVP risk.
- Signed URLs: 300 s, audited as `DOCUMENT_URL_ISSUED`. `GET /documents/{id}/url?disposition=inline` (default, View) has no `download=`, so browsers display it; `?disposition=attachment` adds `download=<sanitized filename>`.
- The bucket is private, with bucket-level size and MIME limits (`python -m app.cli create-bucket`).

## Security (non-negotiable)

- Hash passwords with Argon2 (`argon2-cffi` or `passlib[argon2]`).
- Short-lived access JWT + refresh token. Put role and `organization_id` in the claims, but **re-check ownership in services**.
- **Org isolation:** every query for business data filters by the caller's `organization_id`. Test this explicitly.
- Uploads: allow only PDF/JPG/PNG, max 10 MB, and check the real type server-side (not just the extension).
- Storage buckets are private. Signed URLs expire in 5 minutes or less and are issued only after an ownership check.
- CORS is restricted to `CORS_ORIGINS`.
- Rate-limit `/auth/login` and `/public/verify`.
- Write an `audit_logs` row on every create, status change, approve/reject and certificate issue.
- Use SQLAlchemy only. No string-built SQL.
- Never log secrets, tokens or passwords.

## Testing

- Tests run against a **local Postgres** database (`lm_test`, override with `TEST_DATABASE_URL`). `conftest.py` refuses to run against Supabase.
- Setup: `brew services start postgresql@15 && createdb lm_test`.
- Each test run migrates `lm_test` down and up, and each test truncates all tables afterwards. Tests use real commits.

## Testing priorities

1. Org isolation (business A cannot read business B)
2. RBAC per endpoint
3. Status transitions (valid and invalid)
4. Public verify for valid, expired and revoked certificates
5. Expiry job idempotency
