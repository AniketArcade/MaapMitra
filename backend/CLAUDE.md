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
| `0008` | document review checklist (`document_review_checklist_items`, `application_status` enum gains `DOCUMENTS_DEFICIENT`) | Applied to Supabase (confirmed live, head at `0013`, `alembic check` clean, as of 2026-10-01; exact apply date not recorded — this row was found already applied, not applied by this workflow) (spec `docs/specs/11-document-review-checklist.md`) |
| `0009` | transportability and verification mode (`instruments.transportable` boolean, NOT NULL, `server_default(true())`; new `verification_mode` enum type; `applications.verification_mode`, nullable) | Applied to Supabase (confirmed live 2026-10-01, see `0008` note) (spec `docs/specs/14-transportability.md`) |
| `0010` | certificate superseding (`certificate_status` enum gains `SUPERSEDED`; `certificates.supersedes_certificate_id` / `superseded_by_certificate_id`, both nullable self-referential FKs, `ON DELETE SET NULL`) | Applied to Supabase (confirmed live 2026-10-01, see `0008` note) (spec `docs/specs/13-certificate-superseding.md`) |
| `0011` | payments (`payments` table: `application_id` unique FK `ON DELETE CASCADE`, `amount` nullable `Numeric(10,2)`, new `payment_status` enum `NOT_PAID`/`PENDING`/`PAID` default `NOT_PAID`, `paid_at` nullable timestamptz) | Applied to Supabase (confirmed live 2026-10-01, see `0008` note; table empty, 0 rows) (spec `docs/specs/12-payments.md`) |
| `0012` | instrument categories (`instrument_categories` table: smallint PK 1-33, `name`, `validity_months`, `field_schema` JSONB, seeded with 33 rows in this same migration; `instruments` gains nullable `category_id` smallint FK `ON DELETE SET NULL` + nullable `category_values` JSONB) | Applied to Supabase (confirmed live 2026-10-01: `instrument_categories` has 33 rows). ⚠️ This was applied **before** the user-review gate this row used to carry was ever confirmed satisfied — the 33 seeded rows are ported from a separate prototype repo's own invented-but-plausible fixture data (see `docs/specs/16-instrument-categories.md`). Content review status: **unconfirmed** — ask before trusting this data in the live demo. |
| `0013` | GATC eligibility (`organizations.gatc_eligible_category_ids`, nullable JSONB array of `instrument_categories.id`, CHECK constrained to `type=GATC` orgs only) + `inspections.assignee_role` (new `inspection_assignee_role` enum, NOT NULL, backfilled `LM_OFFICER` for every pre-existing row) | Applied to Supabase (confirmed live 2026-10-01, see `0008` note) (spec `docs/specs/15-gatc-eligibility.md`) |

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
- Enums, units and regions live in `core/instrument_types.py` and `core/regions.py`; application/document types in `core/application_types.py`; verification mode (spec 14) in its own sibling module `core/verification_types.py` — a routing concept computed from an instrument property but stored on the Application, not a fit for either existing file. The frontend gets them from `GET /instruments/meta` and `GET /applications/meta`.
- **Row locks re-read:** every `with_for_update()` re-check uses `.execution_options(populate_existing=True)`. Otherwise the identity map returns the stale pre-lock copy.
- **Audit-writing GETs commit in the service** (e.g. `GET /documents/{id}/url` writes `DOCUMENT_URL_ISSUED`).

## Data model

Tables: `users`, `organizations`, `refresh_tokens`, `instruments`, `instrument_categories` (step 16,
see below), `applications`, `documents`, `inspections`,
`inspection_checklist_items`, `inspection_measurements`, `document_review_checklist_items`,
`certificates`, `payments` (mocked, informational only — step 12, see below), `audit_logs`

- `users`: DB check constraints tie `role` to `organization_id` (BUSINESS/GATC need one, officials must not) and require `state_code`/`district_code` for officials.
- `organizations`: `gatc_eligible_category_ids` (step 15, migration `0013`): nullable JSONB array of `instrument_categories.id` values, meaningful only for
  `type=GATC` orgs (CHECK-constrained). `none_as_null=True` on the SQLAlchemy type — without it a
  Python `None` writes as `'null'::jsonb`, not SQL `NULL`, which silently fails both the CHECK
  constraint and `services/gatc.py: list_eligible()`'s own `IS NULL` filtering (caught by a real
  Postgres `CheckViolation` in the first test run). No write endpoint exists yet — configured
  directly in the database until a future org-management step (spec `docs/specs/15-gatc-eligibility.md`).
- `refresh_tokens`: SHA-256 `token_hash` only, never the raw token.
- `audit_logs`: append-only. Write rows through `services/audit.log(db, *, actor, action, entity_type, entity_id, organization_id, details, ip)` in the caller's transaction. Routers pass `ip=get_client_ip(request)`.
- `instruments` (spec `docs/specs/02-instruments.md`, lock activated by `docs/specs/05-officer-dashboard.md`):
  - `instrument_uid` = `LM-{state}-{district}-{nextval('instrument_uid_seq'):06d}`. It's global, so there are gaps. It's permanent, even if the location changes, and never a credential.
  - Global unique index `ix_instruments_mfr_serial` on `(lower(manufacturer), serial_number)`. The index is the duplicate check: catch the `IntegrityError` → 409. Serial numbers are stored uppercased.
  - Delete is blocked by `ON DELETE RESTRICT` once **any** application exists (→ 409).
  - **Locking:** `core/instrument_lock.py: locked_fields(active_status)` is the single source of truth, used by both the PATCH check and `InstrumentOut.locked_fields` (so the frontend disables exactly what the backend enforces — never re-derive the rule client-side). While a non-terminal application exists (DRAFT included), identity fields (manufacturer, model, serial_number, capacity, capacity_unit, accuracy_class, state_code, district_code) → 409. Once the application reaches SCHEDULED, INSPECTION or APPROVED, address/latitude/longitude lock too (409, a distinct message) — they stay editable through DRAFT/SUBMITTED/DOCUMENT_REVIEW. The lock lifts entirely at REJECTED or CERTIFICATE_ISSUED.
  - `InstrumentOut.active_application` (one LEFT JOIN); reported as `null` to officials while it's a DRAFT.
  - `transportable` (spec `docs/specs/14-transportability.md`, migration `0009`): "Can the instrument be
    transported?" Boolean, NOT NULL, `server_default(true())` (same pattern as `User.is_active`).
    Defaults `true` on `InstrumentCreate` when omitted. Drives `Application.verification_mode`
    (below) and joins `IDENTITY_LOCKED` — same reasoning as `state_code`/`district_code`: it's
    snapshotted onto the Application at creation, so it locks for the same duration to keep the
    instrument's live value from drifting out of sync with an in-progress application's frozen
    snapshot.
  - `category_id` / `category_values` (spec `docs/specs/16-instrument-categories.md`, migration
    `0012`, applied to Supabase, content review of the 33 seeded category rows still pending):
    an additive, optional,
    richer category system that sits **alongside** `instrument_type`/`capacity`/`capacity_unit`/
    `accuracy_class` above, not instead of them — every pre-existing instrument keeps
    `category_id = NULL` and works entirely unaffected. `category_id` (nullable smallint FK ->
    `instrument_categories.id`, `ON DELETE SET NULL`) and `category_values` (nullable JSONB, the
    filled-in values keyed by each category's `field_schema` entry's `key`) are a **paired**
    field: `InstrumentCreate`/`InstrumentUpdate` reject one being set without the other (see
    `schemas/instrument.py: _category_pair_valid`/`category_fields_sent_together`). Both join
    `IDENTITY_LOCKED` for the same "snapshotted, don't let it drift mid-application" reasoning as
    `transportable`. Validation is **top-level required-field-presence only** (deliberate MVP
    scope, see the spec's Decisions): `services/instruments.py: _validate_category()` checks that
    every `field_schema` entry with `required: true` has a corresponding non-null key in
    `category_values` — repeater-row contents, range-band (Qmin < Qt < Qmax) ordering, and
    unit-option membership are explicitly **not** validated.
- `applications` (spec `docs/specs/03-applications.md`):
  - `application_number` = `APP-{UTC year}-{nextval('application_number_seq'):06d}`, display only.
  - One active (non-terminal) application per instrument: partial unique index `ux_applications_active_instrument`.
  - `state_code`/`district_code` are a snapshot of the instrument's location (locked while active).
  - `verification_mode` (spec `docs/specs/14-transportability.md`, migration `0009`): a snapshot of
    `instrument.transportable` taken at creation (`verification_mode_for()`,
    `app/core/verification_types.py`) — `transportable=True → OFFICE_TEST_CENTRE`,
    `False → ON_SITE`. Nullable enum column: frozen once set, never re-derived, and applications
    created before `0009` have no snapshot to backfill (the point of a snapshot is that it can't
    be reconstructed after the fact). Served as the raw enum on `ApplicationDetail` (matching how
    `status`/`application_type` are served); display labels live only in
    `GET /applications/meta`'s `verification_modes`, never hardcoded client-side.
  - `application_status_history` is append-only and feeds the timeline (businesses can't read `audit_logs`).
  - **Officials never see DRAFT applications or their documents** (`scope_applications`).
  - `scheduled_date` on `ApplicationOut`/`ApplicationDetail.inspection` comes from a LEFT JOIN/`contains_eager` on `inspections`, never a per-row query.
- `documents`: `storage_path` = `applications/{application_id}/{document_id}.{pdf|jpg|png}` (never a URL, never the user's filename). `content_type` is the **sniffed** type. Max 10 per application.
- `inspections` (spec `docs/specs/05-officer-dashboard.md`, extended by `docs/specs/06-inspection-checklist.md` and `docs/specs/15-gatc-eligibility.md`): one row per application (`application_id` unique FK), created when `DOCUMENT_REVIEW → SCHEDULED` fires. `scheduled_date` (date only, no time slot — ASSUMPTION), `assigned_officer_id` (self-assign in step 5 — always the officer who scheduled it — **or**, since step 15, a specific `GATC`-role user the scheduling officer explicitly routed to; either way the only person who may start/edit/submit the field inspection, step 6 D1/step 15). `assignee_role` (step 15, migration `0013`): `inspection_assignee_role` enum (`LM_OFFICER`/`GATC`), `NOT NULL`, backfilled `LM_OFFICER` for every pre-existing row (a known fact, not a guess — see the spec's D4) — denormalized so reporting/dashboards never need a join to `users.role`; set once at assignment and never re-validated (safe: no endpoint anywhere ever mutates `users.role` after creation). No `status` column — the application's own `status` stays the single source of truth. Index `(assigned_officer_id, scheduled_date)` doubles as the "my inspections" list: `GET /applications?status=INSPECTION&sort=scheduled_asc`. Step 6 adds `overall_remarks` (text, null), `submitted_at` (timestamptz, null — the single source of truth for "this checklist is locked"), `submitted_by` (FK → users, `ON DELETE RESTRICT`, null).
- `inspection_checklist_items` / `inspection_measurements` (spec `docs/specs/06-inspection-checklist.md`): one row per `CHECKLIST_TEMPLATES`/`MEASUREMENT_TEMPLATES` entry for the instrument's type (`core/inspection_templates.py`, ASSUMPTION — illustrative demo content), **snapshotted** when the inspection starts (`SCHEDULED → INSPECTION`) so a later template edit never changes an in-progress or already-submitted inspection. `inspection_checklist_items.result` is a nullable `checklist_result` enum (`PASS`/`FAIL`/`NA`); `inspection_measurements.expected_value` is `instrument.capacity * fraction` computed at start time, `observed_value` filled by the officer. Both `ON DELETE CASCADE` from `inspections`, unique on `(inspection_id, item_key)` / `(inspection_id, label)`.
- `document_review_checklist_items` (spec `docs/specs/11-document-review-checklist.md`,
  migration `0008`): one row per `DOCUMENT_REVIEW_CHECKLIST_TEMPLATE` entry (`core/document_review_templates.py`,
  ASSUMPTION — illustrative demo content, a single generic list, not per-instrument-type),
  **snapshotted** when the application enters `DOCUMENT_REVIEW` and **reset** (`checked = false`,
  not recreated) on a later re-entry via the `DOCUMENTS_DEFICIENT → SUBMITTED → DOCUMENT_REVIEW`
  loop. `ON DELETE CASCADE` from `applications`, unique on `(application_id, item_key)`.
  `DOCUMENT_REVIEW → SCHEDULED` is blocked (409) until every row's `checked` is `true`.
- `certificates` (spec `docs/specs/08-certificate-pdf-qr.md`): one row per application (`application_id` unique FK, `ON DELETE RESTRICT`), created by `services/certificates.py: issue()` — never through `transition()`. `certificate_number` = `LM-CERT-{UTC year}-{nextval('certificate_number_seq'):06d}`. `snapshot` (JSONB) freezes the instrument/business/approver fields shown on the PDF at issuance time — a deliberate JSONB blob, not relational rows like the checklist (it's one immutable bundle written once and always read whole, the opposite case from spec 06's checklist items), needed because the instrument unlocks (editable again) the moment the application reaches this terminal status. `valid_from`/`valid_until` = issue date + `CERTIFICATE_VALIDITY_YEARS` (Settings field, default 2 — ASSUMPTION, not a real Legal Metrology rule). `status` starts `VALID`; the expiry job (step 10) is the only thing that ever moves it to `EXPIRED`, and `issue()` itself is the only thing that ever moves an *older* certificate to `SUPERSEDED` (step 13, see below) — `REVOKED` has no writer anywhere yet (no revoke action exists). `pdf_path` = `certificates/{id}.pdf`, stored in the same single `SUPABASE_BUCKET` as documents (no new bucket). `data_hash`: SHA-256 hex of a fixed pipe-joined string of the certificate's own fields (`app/services/certificates.py: _data_hash()`) — a tamper-evidence fingerprint, not a cryptographic file signature (root `CLAUDE.md`'s "hash-based in MVP" decision). No `qr_token` column: the QR/public URL encodes `certificate_number` directly (see QR section below). `reminder_30d_sent_at`/`reminder_7d_sent_at` (migration `0007`, nullable `Date`): the expiry job's idempotency mechanism (see Expiry job below) — `NULL` means "not yet sent," never re-derived from a log. `supersedes_certificate_id`/`superseded_by_certificate_id` (migration `0010`, spec `docs/specs/13-certificate-superseding.md`): nullable self-referential FKs, `ON DELETE SET NULL`, both `NULL` for every certificate issued before `0010` (no backfill — same "an honest NULL beats a fabricated value" reasoning as spec 14's `verification_mode`). Set only by `issue()`, in the same transaction as the new row's insert.

- `payments` (spec `docs/specs/12-payments.md`, migration `0011`): one row per application
  (`application_id` unique FK, `ON DELETE CASCADE` — unlike `certificates`' `RESTRICT`, since a
  mocked payment has no independent reason to outlive its application and an application can still
  be deleted while `DRAFT`), created **lazily** by `POST /applications/{id}/mock-pay` — unlike
  `inspections`/`certificates` (created by the lifecycle itself the instant an application reaches
  a given status), most applications never get a `payments` row at all;
  `ApplicationDetail.payment` is `null` until the first mock-pay call, not a zero-value row.
  `amount` (`Numeric(10,2)`, nullable): no real payment gateway or fee schedule exists in this MVP
  (ASSUMPTION), so `mock_pay()` never sets it — left for a real integration to populate later.
  `status` (`payment_status` enum: `NOT_PAID`/`PENDING`/`PAID`, default `NOT_PAID`) and `paid_at`
  (nullable timestamptz, set only once `status` becomes `PAID`). **This table is purely
  informational — deliberately, by explicit user decision, not an oversight:** no status
  transition in `services/applications.py: ALLOWED_TRANSITIONS`/`transition()` reads or checks
  `payments` in any way; an application can reach `CERTIFICATE_ISSUED` with no `payments` row at
  all. `mock_pay()` (`services/payments.py`) creates the row directly with `status=PAID` in a
  single step (no gateway to await, so an intermediate `PENDING` write-then-flip would add a state
  transition with no observable difference) and is idempotent: it locks the parent application row
  first, so two racing calls for the same application can never both insert — the second always
  sees the first's already-committed row. No `scope_payments()` helper exists: a payment is only
  ever reached through its owning application (`applications_service.load()`'s existing scope), the
  same reasoning `scope_certificates()`/`scope_inspections()` already use.

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

### Transportability and verification mode (step 14, spec `docs/specs/14-transportability.md`)
- `instruments.transportable` ("Can the instrument be transported?") defaults `true` on
  `InstrumentCreate` when omitted and joins `IDENTITY_LOCKED` (locked while any non-terminal
  application exists) — same reasoning as `state_code`/`district_code`: it's snapshotted onto the
  Application at creation, so it locks for the same duration.
- `applications.verification_mode` is set once, in `services/applications.py: create()`, via
  `verification_types.verification_mode_for(instrument.transportable)`:
  `transportable=True → OFFICE_TEST_CENTRE`, `False → ON_SITE`. Never re-derived afterward — a
  later `PATCH /instruments/{id}` changing `transportable` (only reachable once the instrument
  unlocks) never touches any existing application's `verification_mode`.
- `GET /applications/meta`'s `verification_modes` (`[{value, label}, ...]`) is the only place the
  display labels are served — `ApplicationDetail.verification_mode` itself is the raw enum,
  matching `status`/`application_type`'s own convention.
- No new endpoint: `transportable` rides the existing `POST/PATCH /instruments` and
  `InstrumentOut`; `verification_mode` rides the existing `ApplicationDetail`/`ApplicationOut`.

### Certificate superseding + expiring-soon (step 13, spec `docs/specs/13-certificate-superseding.md`)
- `services/certificates.py: issue()` now also supersedes the instrument's previous certificate,
  if one exists and isn't already `SUPERSEDED`, in the **same transaction** as the new
  certificate's insert (no second commit): look up the most recent certificate for the same
  `instrument_id` (via the application → instrument join), lock it with `with_for_update(of=
  Certificate)` under the same `populate_existing=True` discipline every other re-check lock in
  this function uses, set its `status = SUPERSEDED` and `superseded_by_certificate_id`, and set
  the new row's `supersedes_certificate_id`. A `db.flush()` runs between `db.add(certificate)` and
  the previous row's update — both FK values are plain client-generated UUIDs, not ORM
  relationships, so SQLAlchemy's unit-of-work won't otherwise order the `INSERT` before the
  `UPDATE`, and Postgres's (non-deferred) FK constraint rejects the reverse order.
- `core/certificate_status.py: is_expiring_soon(status, valid_until, *, today)` — an **additive
  sibling** to `effective_status()`, not a change to it: `True` only when `effective_status()`
  already reads `VALID` and `valid_until <= today + EXPIRY_REMINDER_30D_DAYS`, the same threshold
  `services/admin.py`/`services/certificates.py: expiry_check()` already use. `effective_status()`
  itself does **not** get a `SUPERSEDED`-wins branch — it falls through the same
  "`valid_until < today` → `EXPIRED`" rule every non-`REVOKED` status already gets, exactly as
  before this step; see the spec's D3 for why that was a hard constraint, not an oversight.
- `CertificateOut` gains `supersedes_certificate_id`/`superseded_by_certificate_id` (raw
  `uuid.UUID | None`, not nested refs — this schema already exposes `application_id` the same
  flat way) and `is_expiring_soon: bool`.
- `AdminCertificateStats` (`GET /admin/certificates/stats`) gains a `superseded` count bucket,
  populated from the same grouped-by-status query already backing `valid`/`expired`/`revoked`.
- **`PublicVerifyOut` gains exactly two fields** — `instrument_uid` and `issued_by` (from the
  snapshot's existing `approved_by_name`) — under this step's explicit authorization to deviate
  from spec 09 §5's "complete field set" wording (that schema's own docstring says "never add a
  field here without checking spec 09 §5/§10 D4 first"; this is that check, recorded here and in
  spec 13's own Decisions section). The supersede chain and `is_expiring_soon` were deliberately
  **not** added to the public schema: a superseded certificate's own `status` becoming
  `SUPERSEDED` is already the actionable signal a public verifier needs, and exposing either would
  mean leaking an internal certificate id or a nuance aimed at the certificate holder, not the
  public, for no new information `status` doesn't already carry. See §5 of spec 13 for the full
  reasoning.

Certificate status: `VALID` · `EXPIRED` · `REVOKED` · `SUPERSEDED` (step 13)

### Payments — mocked, informational only (step 12, spec `docs/specs/12-payments.md`)
- Resolves the long-open "Payments: mocked in MVP (`payments` table only)" decision (see
  **Open decisions** below): the table plus a mock-pay action exist so the concept is visible in
  the product, but **payment status gates nothing**. This was an explicit user decision, not
  something left unfinished — `services/applications.py: ALLOWED_TRANSITIONS`/`transition()` is
  untouched by this step; a test (`tests/test_payments.py::test_payment_never_gates_the_lifecycle`)
  proves an application reaches `CERTIFICATE_ISSUED` with no `payments` row ever created.
- `POST /api/applications/{id}/mock-pay` (`app/routers/applications.py`, `Owner` = `BUSINESS`
  only) → `services/payments.py: mock_pay()`. Org scoping is inherited entirely from
  `applications_service.load()` (out-of-org business → 404, never 403, same as every other
  endpoint) — no separate `scope_payments()` helper, since a payment is only ever reached through
  its owning application (same reasoning `scope_certificates()`/`scope_inspections()` use).
- **Create-vs-upsert:** looks up the existing `Payment` row (if any) after locking the parent
  `Application` row, and either inserts a new one or updates it — never both in the same call.
  Idempotent by lock ordering, not a pre-check: two racing mock-pay calls for the same application
  serialize on the application row lock, so the second always sees the first's committed row.
  Already-`PAID` is a safe no-op (`paid_at` is left exactly as first set).
- **Single-step, direct to `PAID`** (not `PENDING` then flipped): no real gateway exists to await,
  so an intermediate write would add a state transition with no observable difference to any
  caller. `PENDING` exists in the enum for a future real integration, but this action never
  produces it.
- **`amount` is left `null`/unset by `mock_pay()`** (ASSUMPTION): no fee schedule or real gateway
  exists in this MVP to derive a number from; the column exists so a future real integration can
  populate it without a schema change.
- `ApplicationDetail.payment: PaymentOut | None` (`app/schemas/payment.py`) is `null` until the
  first mock-pay call (the row is created lazily, not at application creation) — not exposed on
  `ApplicationOut`, no dedicated `GET` endpoint (nothing to fetch independently; it's only ever
  read alongside its application).
- `GET /applications/meta`'s `payment_statuses` (`[{value, label}, ...]`) is the only place the
  display labels are served (`app/core/payment_types.py: PAYMENT_STATUS_LABELS`) — the frontend
  must never hardcode them, same rule every other backend-owned enum here follows.
- Audit action: `PAYMENT_MOCKED` (`entity_type="application"`, `details.status`,
  `details.created`).

### Instrument categories (step 16, spec `docs/specs/16-instrument-categories.md`)

🛑 **Migration `0012` is applied to Supabase, but its seeded category content (names, fields,
options, units) has never been human-reviewed** — see the migration table above and the spec doc
for the full disclaimer. This is content review, not code review, and it's still open: the 33
rows are live in the real database today, unreviewed.

- `instrument_categories` (new table): 33 rows, `id` a **smallint primary key 1-33** (not the
  usual `UUIDPk` — a small, fixed, numbered reference set, mirrored from a separate prototype
  repo's own stable category numbering), `name`, `validity_months` (mock; never used to compute
  real legal validity, same caveat every other mock validity value in this codebase carries),
  `field_schema` (JSONB array of field definitions — see `app/schemas/instrument_category.py:
  CategoryFieldSchema` for the exact snake_case shape: `key, label, type, required, unit,
  unit_options, options, presets, repeater_label, repeater_fields, min, max, help_text`).
  **Seeded directly in migration `0012`** (`op.bulk_insert`), not via `app/seed.py`/
  `database/seed/`: this is reference/taxonomy data the app needs to function in every
  environment (like `app/core/regions.py`'s `REGIONS`, but promoted to a real table), not
  demo-only content — it must not be gated behind `app/seed.py`'s `ENV=production` guard.
- `instruments.category_id` (nullable smallint FK -> `instrument_categories.id`, `ON DELETE SET
  NULL`) / `instruments.category_values` (nullable JSONB, keyed by each category's field
  `key`s): fully **additive** alongside `instrument_type`/`capacity`/`capacity_unit`/
  `accuracy_class` — every pre-`0012` instrument keeps `category_id = NULL` and works entirely
  unaffected; no backfill or mapping from the old enum onto the new categories was attempted.
- **Paired, not independent**: `InstrumentCreate`/`InstrumentUpdate` reject `category_id` being
  set without `category_values` (or vice versa) — `schemas/instrument.py:
  _category_pair_valid()`/`category_fields_sent_together()`. Both are in `NULLABLE_FIELDS`, so an
  explicit `null` on either is allowed and clears the category assignment entirely (both together,
  never one alone).
- **Validation scope — a deliberate MVP simplification, not an oversight**:
  `services/instruments.py: _validate_category()` checks only that every `field_schema` entry
  with `required: true` has a corresponding **non-null top-level key** in `category_values`.
  Repeater-row contents (e.g. at least one weight in category 1's denominations), range-band
  ordering (Qmin < Qt < Qmax, categories 17/26), and unit-option membership (e.g. rejecting a
  `unit` outside a field's `unit_options`) are explicitly **not** validated by this step.
- **`category_id`/`category_values` join `IDENTITY_LOCKED`** (`core/instrument_lock.py`) — same
  reasoning as `transportable` (spec 14): an in-progress application's understanding of "what kind
  of instrument is this" shouldn't have the underlying instrument's category silently change while
  a non-terminal application exists.
- `GET /instruments/meta`'s `categories` entry (`[{id, name, validity_months, field_schema}, ...]`)
  is read live from the `instrument_categories` table (`app/routers/instruments.py: meta()`,
  the one query added to that endpoint), not from a Python constant like `types`/`regions` on the
  same response — the whole point of a real table is that a human can review/edit the category
  content as data, without a code deploy, once this migration is eventually applied. A future
  frontend's `DynamicFieldRenderer` reads this endpoint; it must never import a static category
  list of its own.
- No new endpoint. `category_id`/`category_values` ride the existing `POST/PATCH /instruments`
  request/response schemas, exactly like spec 14's `transportable`.

### GATC eligibility + allocation (step 15, spec `docs/specs/15-gatc-eligibility.md`)

Migration `0013` is applied to Supabase. Resolves the root `CLAUDE.md`'s "GATC workflow
depth: minimal" open decision as **minimal but real**: a `GATC`-role user becomes a genuine,
category-gated `assigned_officer_id` on an `Inspection`, then flows through the exact same
inspection/checklist/measurement/approve-reject machinery `LM_OFFICER` already uses — nothing is
duplicated or forked for GATC.

- `organizations.gatc_eligible_category_ids` / `inspections.assignee_role`: see the Data model
  section above.
- `GET /api/gatc/eligible?category_id=<id>` (`LM_OFFICER` only — the sole role that ever
  schedules): GATC organizations, scoped to the caller's own jurisdiction
  (`services/scoping.py: scope_organizations()`, mirrors `scope_instruments()`'s state/district
  rule applied to `Organization` instead of `Instrument`), whose `gatc_eligible_category_ids`
  contains `category_id`. `BUSINESS` is deliberately excluded (a business never chooses its own
  routing; the list would leak GATC org names/jurisdictions with no action the caller could take)
  and so are admin roles (they don't schedule; this is a live operational lookup, not a reporting
  surface).
- `GET /api/gatc/{organization_id}/users` (`LM_OFFICER` only): the active `GATC`-role users of one
  organization, so the officer can name a specific person, not just an org — mirrors
  `assigned_officer_id`'s existing "a specific person" semantics (spec 06 D1). Out-of-scope/
  non-GATC org → 404, the ordinary GET-by-id convention.
- `DOCUMENT_REVIEW → SCHEDULED` extended: `StatusChange` gains optional, paired
  `gatc_organization_id`/`gatc_user_id`. Omitting both self-assigns the scheduling `LM_OFFICER`,
  **completely unchanged** from before this step. Providing both routes to that specific GATC user
  instead, via `services/gatc.py: resolve_gatc_assignment()`, which enforces (a) the org is
  `type=GATC` and in the officer's own jurisdiction, (b) the application's *instrument* has a
  non-null `category_id` present in that org's `gatc_eligible_category_ids` (an old-style,
  pre-spec-16 application with no category can never use GATC routing), and (c) the application's
  `verification_mode == OFFICE_TEST_CENTRE` (an `ON_SITE` application can never route to a GATC
  test centre). A bad/nonexistent reference (unknown org/user, wrong org type, wrong jurisdiction,
  inactive user, wrong org for that user) → 422; a legitimate reference blocked by a business rule
  (category mismatch, `ON_SITE` mode) → 409 — see the spec's §5 for the full reasoning on this
  split.
- `SCHEDULED → INSPECTION`, `INSPECTION → APPROVED`, `INSPECTION → REJECTED` all gain `GATC` in
  their `ALLOWED_TRANSITIONS` role set — no other change: the existing "must be the assigned
  officer specifically" identity check (keyed on `assigned_officer_id == caller.id`, already
  role-agnostic) and the existing "any in-scope officer may approve/reject once the checklist is
  submitted" logic both generalize to GATC with zero further code changes.
- `scope_applications()` gains a `GATC` branch — deliberately the **narrowest** of any role: not
  jurisdiction-wide like `LM_OFFICER`, not org-wide like `BUSINESS`, but exactly the one
  application (if any) this specific person is the `assigned_officer_id` of
  (`Application.inspection.has(Inspection.assigned_officer_id == user.id)`, a correlated `EXISTS`,
  never a join, so it can't collide with another caller path's own join to `Inspection`). A
  consequence of this narrowness: "any in-scope GATC user" for approve/reject mechanically reduces
  to "the one assigned GATC user" — no extra code enforces that, it falls out of the scoping rule.
- **Router-level plumbing, not a role-set shortcut:** simply adding `GATC` to the existing `Reader`
  dependencies on `GET/PATCH /applications/{id}...`/`GET/PATCH/POST /inspections/{id}...` would flip
  an *unrelated* GATC caller's status from the pre-existing, test-pinned `403` to `404` (since
  `scope_applications`'s "out of scope → 404" convention would then run for a role those endpoints
  hadn't previously admitted at all). Instead, `routers/applications.py:
  _reader_or_assigned_gatc()` and the analogous pair in `routers/inspections.py` check the path's
  own `application_id`/`inspection_id` directly (`services/gatc.py:
  is_assigned_gatc_for_application()`/`is_assigned_gatc_for_inspection()`) before falling through
  to the original `Forbidden`. Every pre-existing role's behavior — and every pre-existing RBAC
  test — is untouched; only the one specifically assigned GATC user is newly admitted, and only for
  that one application/inspection. `GET /applications` (list), `GET /applications/stats`, and
  evidence-photo upload/delete are deliberately left untouched (flat 403 for GATC, unchanged) —
  none has a per-request id to gate on the way the endpoints above do, and evidence photos are
  optional (a GATC inspection completes fully without them).
- `InspectionOut`/`InspectionDetail` gain `assignee_role` (raw enum, no `*_LABELS` dict — same
  precedent `ChecklistResult` already sets) alongside the existing assignee info.
- No new audit action: `INSPECTION_SCHEDULED`'s existing `details` gains `assignee_role` and
  `assigned_officer_id`.

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
GET   /api/instruments/meta      # types, units, accuracy classes, regions, categories (step 16) (any logged-in user)
CRUD  /api/instruments           # write: BUSINESS (own org); read: + officials in jurisdiction; GATC 403
CRUD  /api/applications          PATCH /api/applications/{id}/status
POST  /api/documents             GET   /api/documents/{id}/url     # signed URL
GET   /api/inspections/meta      GET   /api/inspections/{id}
PATCH /api/inspections/{id}      POST  /api/inspections/{id}/submit
GET   /api/certificates/{id}     GET   /api/certificates/{id}/pdf
POST  /api/applications/{id}/certificate   # LM_OFFICER only; issues a certificate while APPROVED
POST  /api/applications/{id}/mock-pay      # BUSINESS (owner) only; mocked, informational-only payment (step 12)
POST  /api/jobs/expiry-check     # requires X-Cron-Secret header, no rate limit (step 10)
GET   /api/admin/certificates/stats            # ADMIN_ROLES; {valid, expiring_soon, expired, revoked, superseded}
GET   /api/admin/certificates/expiring-soon    # ADMIN_ROLES; Page[CertificateOut], valid_until asc
GET   /api/public/verify/{certificate_number}                     # no auth
GET   /api/public/regions          # no auth; state/district list for the pre-login register form (same REGIONS as instruments/meta)
GET   /api/applications/meta       # types, statuses (lifecycle order), document types + requirements, upload limits, scheduling {timezone, max_days_ahead}, document_review_checklist (step 11), verification_modes (step 14), payment_statuses (step 12)
CRUD  /api/applications            # write: BUSINESS, DRAFT only; read: + officials (non-DRAFT, jurisdiction)
GET   /api/applications/stats      # {total, by_status}: same scope_applications as the list, all 9 statuses zero-filled (step 11 adds DOCUMENTS_DEFICIENT)
GET   /api/applications?sort=      # created_desc (default) | scheduled_asc
PATCH /api/applications/{id}/inspection   # LM_OFFICER only; reschedule while SCHEDULED
PATCH /api/applications/{id}/review-checklist   # LM_OFFICER only, DOCUMENT_REVIEW only; toggle document-review checklist items (step 11)
DELETE /api/documents/{id}         # BUSINESS/DRAFT, or assigned LM_OFFICER/INSPECTION evidence (step 6)
GET   /api/gatc/eligible          # LM_OFFICER only; ?category_id=<id>, jurisdiction-scoped GATC orgs (step 15)
GET   /api/gatc/{organization_id}/users   # LM_OFFICER only; active GATC-role users of one org (step 15)
GET   /api/users                  # SUPER_ADMIN + STATE_ADMIN (own state, step 18); official accounts (role in OFFICIAL_ROLES), filters role/state_code/district_code/is_active/q; ?role=LM_OFFICER populates pending_cases/completed_cases per officer (step 17)
POST  /api/users                  # SUPER_ADMIN (any role) + STATE_ADMIN (DISTRICT_ADMIN/LM_OFFICER only, own state) (step 17, extended step 18)
PATCH /api/users/{id}             # SUPER_ADMIN + STATE_ADMIN (own state, strictly lower rank, step 18); body {is_active} only; 409 on self-deactivation (step 17)
GET   /api/audit-logs             # SUPER_ADMIN + STATE_ADMIN (own-state jurisdiction filter, step 18); filters date_from/date_to/actor_user_id/action/entity_type; actor_name null = system actor (step 17)
GET   /api/organizations?type=GATC   # SUPER_ADMIN + STATE_ADMIN (own state, step 18); GATC directory with live pending/completed case counts per org (step 17)
GET   /api/applications?state_code=&district_code=   # additive filters on the existing list, any role (no-op for jurisdiction-locked callers) (step 17)
GET   /admin/state-overview       # ADMIN_ROLES; one row per REGIONS state/UT, zero-filled, never paginated (step 17)
GET   /admin/district-overview    # ADMIN_ROLES; one row per district of one state, zero-filled, never paginated; state_code forced for STATE_ADMIN/DISTRICT_ADMIN, required for SUPER_ADMIN (step 18)
GET   /api/certificates           # same Reader/scope_certificates as every other certificate endpoint; ?status= filter; first certificate list endpoint (step 17)
```

### Public verify (step 9, spec `docs/specs/09-public-verify.md`; field list extended by step 13, spec `docs/specs/13-certificate-superseding.md`)
- `PublicVerifyOut` (`app/schemas/public.py`) field list: `certificate_number`, `status`,
  `instrument_type_label`, `instrument_uid`, `manufacturer`, `model`, `serial_number`,
  `valid_from`, `valid_until`, `issued_by`. The last two spec 09 §5 did not originally include —
  step 13 added them under explicit authorization to deviate from spec 09 §5's "complete field
  set" wording (see that step's spec doc §5 and the "Certificate superseding" subsection above for
  the full reasoning). No owner PII (`organization_name`, `address`), no documents, no internal
  database IDs (`id`, `application_id`, and — deliberately, per step 13 — no supersede-chain
  certificate ids either), no `pdf_path`/`data_hash`. Never link to the certificate PDF from the
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
  independent number, and the same one `core/certificate_status.py: is_expiring_soon()` (step 13)
  reads from settings. `AdminCertificateStats.valid` is **inclusive** of `expiring_soon` (not a
  disjoint bucket): every expiring-soon certificate is still counted as valid.
- `AdminCertificateStats.superseded` (step 13): a `SUPERSEDED`-status count bucket, alongside
  `valid`/`expired`/`revoked`, from the same grouped-by-status query.

### Super Admin (step 17, spec `docs/specs/17-super-admin.md`)

Resolves root `CLAUDE.md`'s "Admin: stats, users, audit logs" role-table line into a real page.
`SUPER_ADMIN`-only for Phase 1 (D1) — the data layer (every `scope_*` helper used below already
has a `SUPER_ADMIN` branch returning the statement unfiltered) would generalize to
`STATE_ADMIN`/`DISTRICT_ADMIN` for free later, but no frontend page does that yet. No new tables
or columns anywhere in this step — every endpoint is a new route/query over data that already
existed.

- **`OFFICIAL_ROLES`** (`core/roles.py`): `ADMIN_ROLES | {LM_OFFICER}` — the role set
  `GET /api/users` lists. `BUSINESS` (self-registers) and `GATC` (listed via the GATC directory
  instead, below) are deliberately excluded (D2).
- **`GET /api/users`** (`services/users.py: list_users()`): no `scope_*` call — `users` has no
  per-row ownership concept the way `applications`/`instruments` do, and this endpoint is already
  `SUPER_ADMIN`-only. `role=LM_OFFICER` triggers a second query (`Inspection.assigned_officer_id`
  joined to `Application`) that buckets each officer's cases by the same `TERMINAL_STATUSES` split
  described below, populating `UserListOut.pending_cases`/`completed_cases`; every other role
  filter leaves those two fields `null` (not `0` — `null` means "not requested"). Only run for the
  officers on the current page, never the whole table.
- **`PATCH /api/users/{id}`** (`services/users.py: set_active()`): body is exactly
  `{is_active: bool}` (`UserActivate`, `StrictModel`, D5). Refuses `user.id == actor.id and not
  is_active` with 409 "Cannot deactivate your own account" — a safety guard beyond the spec's
  literal text, added so a lone Super Admin can't lock themselves out with nobody left to
  re-enable the account. Writes `USER_STATUS_CHANGED` (`entity_type="user"`,
  `details={is_active, role}`).
- **Pending vs completed, the one shared definition reused everywhere a case count is needed**
  (the LMO directory above, the GATC directory and `GET /admin/state-overview` below):
  `completed = status in TERMINAL_STATUSES` (`REJECTED`, `CERTIFICATE_ISSUED`), `pending` =
  everything else reachable through an `Inspection` join (`SCHEDULED`/`INSPECTION`/`APPROVED`) —
  reuses the codebase's own existing terminal/non-terminal boundary rather than inventing a second
  one.
- **`GET /api/organizations?type=GATC`** (new router `routers/organizations.py`,
  `services/organizations.py: gatc_directory()`): `type` is a required `Literal["GATC"]` — the
  only directory this step builds (D3; `GET /api/gatc/eligible` stays the scheduling officer's
  own category-filtered allocation dropdown, untouched). Uses `scope_organizations()` even though
  `SUPER_ADMIN`'s own branch is a no-op today — future-proofed at zero cost. `eligible_categories`
  resolves `Organization.gatc_eligible_category_ids` against `instrument_categories` in one `IN`
  query over the page's id union, never per-row. `GatcDirectoryOut.active` is a **roll-up**
  (`True` iff the org has >=1 active `GATC`-role user) — `Organization` has no `is_active` column
  of its own, so Activate/Deactivate from this directory always targets a specific person
  (`GatcDirectoryUserOut.id`) via the same `PATCH /api/users/{id}`, never the org.
- **`GET /api/audit-logs`** (new router `routers/audit.py`, `services/audit.py: list_audit_logs()`
  alongside the existing `log()` writer): no `scope_*` — `audit_logs` has no jurisdiction column,
  by design a cross-cutting system table. `actor_name` comes from an outer join to `users`; `null`
  means a system actor (`actor_user_id IS NULL`, e.g. the expiry job), not an unknown user.
  `date_to` is inclusive of the whole day (`< date_to + 1 day`, since `created_at` is a
  timestamptz but `date_to` is a bare date).
- **`GET /admin/state-overview`** (`services/admin.py: state_overview()`): one row per `REGIONS`
  key (~36, always present, zero-filled), three `GROUP BY` queries
  (`scope_instruments`/`scope_applications`/`scope_certificates`) merged in Python — the Phase 1
  substitute for the brief's India map (root `CLAUDE.md`'s Deferred list names Leaflet maps
  explicitly). Reuses the existing `Admin = require_roles(*ADMIN_ROLES)` dependency on
  `routers/admin.py` (matching that router's own convention) rather than a `SUPER_ADMIN`-only one
  — the frontend still only renders this for `SUPER_ADMIN`. Returns a bare `list[...]`, never
  `Page[...]`: bounded to `len(REGIONS)` rows always, so pagination would be decoration. **Do not**
  add a second `.join(Application, ...)` when building the certificate-count query here —
  `scope_certificates()` already joins `Certificate -> Application` internally; a duplicate join
  on top of it is a real bug this step hit once during implementation.
- **`GET /api/applications?state_code=&district_code=`**: additive filters, no role restriction —
  harmless no-op for a jurisdiction-locked caller (their own scope already excludes everything
  outside their jurisdiction; a mismatched filter on top just returns an empty page, never
  403/404). `Application` already carries its own `state_code`/`district_code` snapshot columns,
  index-backed by the existing `ix_applications_region_status` composite index.
- **`GET /api/certificates`** (`services/certificates.py: list_certificates()`,
  `routers/certificates.py`): no certificate list endpoint existed before this step (only
  get-by-id and `.../pdf`). Reuses the router's existing `Reader` role set and `scope_certificates`
  unchanged — not `SUPER_ADMIN`-only, since every other certificate endpoint already admits
  `BUSINESS`/`LM_OFFICER`/`*_ADMIN` and there's no reason this one should be narrower. Declared
  before `GET /{certificate_id}` in the router file for readability (no actual path collision risk
  between a bare `""` and a dynamic `/{id}` segment, unlike `/meta`-vs-`/{id}` elsewhere).
- Out of scope, recorded in the spec's §9, not built here: an enforcement/violations module (no
  data model, no named legal source), an India map, a CSV/PDF export engine, trend charts, a
  dynamic state/district editor (`REGIONS` stays a code constant), editing a user's
  email/role/jurisdiction after creation, and extending this page to `STATE_ADMIN`/`DISTRICT_ADMIN`.

### State Admin (step 18, spec `docs/specs/18-state-admin.md`)

Turns the data layer's existing `STATE_ADMIN` support (every `scope_*` helper already had a
branch for it) into an actual page, one rank down from spec 17. No migration — every endpoint is
new routes/service logic over columns that already existed.

- Most of the surface needed **zero backend change**: `GET /api/applications`,
  `GET /api/applications/stats`, `GET /api/instruments`, `GET /api/certificates`,
  `GET /admin/certificates/{stats,expiring-soon}` already admitted `STATE_ADMIN` and were already
  correctly scoped to the caller's own state via `scope_applications`/`scope_instruments`/
  `scope_certificates`. This step's job for those was purely a new frontend.
- **`GET /api/organizations?type=GATC`**: router dependency widened to
  `require_roles(Role.SUPER_ADMIN, Role.STATE_ADMIN)` — **zero service change**.
  `services/organizations.py: gatc_directory()` already calls `scope_organizations(select(...),
  user)`, which already had the `STATE_ADMIN` branch; its own docstring anticipated exactly this
  reuse. A `STATE_ADMIN`-sent `state_code` filter that mismatches their own simply ANDs to an
  empty page (no reject) — `scope_organizations()` already floors the query.
- **`GET /api/users`**, **`POST /api/users`**, **`PATCH /api/users/{id}`**: unlike organizations,
  `users` has no `scope_*` helper of its own (it's permission-gated, not row-owned-by-org data),
  so widening the router dependency alone would have let a `STATE_ADMIN` query another state's
  officials — the one real risk in this step. `services/users.py` gained explicit actor-aware
  checks instead:
  - `list_users(db, actor, ...)` (actor is now a required param): for a `STATE_ADMIN` caller, a
    client-sent `state_code` that mismatches their own → `422 Unprocessable` (reject, never
    silently override — a wrong-but-"successful" query is worse than a visible error); otherwise
    `state_code` is forced to `actor.state_code`. An explicit `role` filter for a peer-or-above
    rank (`ROLE_RANK[role] >= ROLE_RANK[actor.role]`) → `403`; omitting `role` implicitly narrows
    the base query to `{DISTRICT_ADMIN, LM_OFFICER}` (not an error) — this is `ROLE_RANK`'s
    (`core/roles.py`) first real use anywhere in the codebase.
  - `create_user()`: a `STATE_ADMIN` actor may only create `role in {DISTRICT_ADMIN, LM_OFFICER}`
    (`422` field `role` otherwise — `UserCreate.role`'s schema-level `Literal` still admits
    `STATE_ADMIN` too, for `SUPER_ADMIN` callers; this is a narrower service-level check, not a
    schema change) and `state_code` must equal their own (`422` field `state_code` otherwise).
  - `set_active()`: a `STATE_ADMIN` actor may only target `user.state_code == actor.state_code`
    **and** `ROLE_RANK[user.role] < ROLE_RANK[actor.role]` (`403` otherwise). Checked **after**
    the existing unconditional self-deactivation `409` guard — ordering matters, since
    `ROLE_RANK[self.role] < ROLE_RANK[self.role]` is false and would otherwise let the rank check
    mask the more specific self-deactivation error.
- **`GET /api/audit-logs`** — the one genuinely hard piece: `audit_logs` has no jurisdiction
  column (by design, a cross-cutting system table). `list_audit_logs(db, actor, ...)` resolves a
  `STATE_ADMIN` actor's own-state floor via two outer joins —
  `AuditLog.actor_user_id -> users.state_code` (covers official actors) OR
  `users.organization_id -> organizations.state_code` (covers `BUSINESS`/`GATC` actors, whose own
  `state_code` column is `NULL`). Because both are outer joins, a system-actor row
  (`actor_user_id IS NULL`, e.g. the expiry job's `CERTIFICATE_EXPIRED`) has `NULL` on both sides
  and is excluded by the same `WHERE` — a **disclosed Phase-1 gap** (system rows are invisible to
  a `STATE_ADMIN`), not a silent one. Resolving it properly needs an `entity_type`-specific join
  (certificate -> application -> state_code) not built here.
- **`GET /admin/district-overview`** (new, `app/schemas/admin.py: DistrictOverviewRow`,
  `app/services/admin.py: district_overview()`): a direct structural copy of `state_overview()`
  one level down — same 3-query `GROUP BY` pattern over `scope_instruments`/`scope_applications`/
  `scope_certificates`, same "`scope_certificates()` already joins `Certificate -> Application`
  internally — never join it again" warning. For `STATE_ADMIN`/`DISTRICT_ADMIN`, any client-sent
  `state_code` is **overridden**, not rejected — this is read-only aggregate data already
  scope-floored, unlike the user-identity endpoints above. `SUPER_ADMIN` must supply one (`422` if
  missing, `404` if not a real state) to drill into one state from the existing state-wise table.
  Reuses the router's existing `Admin = require_roles(*ADMIN_ROLES)` — no new dependency, so
  `DISTRICT_ADMIN` can call it too (harmless; no frontend page uses it for that role yet).
- `STATE_ADMIN` only for Phase 1 (same sequencing spec 17 used for `SUPER_ADMIN`): `DISTRICT_ADMIN`
  keeps today's plain `ExpiryDashboard`, completely untouched by this step — the data layer
  already generalizes to it for free, just no frontend page built yet.
- Out of scope, recorded in the spec's §9: an enforcement module, notification center, CSV/PDF
  export, trend charts, "Average Scrutiny Time" (needs an `application_status_history`
  timestamp-diff aggregation that doesn't exist), Instrument-Type/assignee filters on
  `/admin/applications` (real new joins, not a free reuse), editing a user's
  email/role/jurisdiction after creation, and extending this page's data layer to `DISTRICT_ADMIN`.

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
