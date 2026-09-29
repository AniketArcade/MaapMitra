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
│   ├── main.py            # app factory, CORS, routers
│   ├── core/              # config (pydantic-settings), security, deps
│   ├── db/                # engine, session
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic request/response models
│   ├── services/          # business logic + status transitions
│   ├── routers/           # thin route handlers
│   │   ├── auth.py  instruments.py  applications.py  documents.py
│   │   ├── inspections.py  certificates.py  public.py  jobs.py
│   ├── storage/           # Supabase Storage wrapper
│   ├── pdf/               # ReportLab certificate + QR
│   └── seed.py
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
RESEND_API_KEY=...
CRON_SECRET=...
ENV=development                              # development | test | production (cookie Secure flag, seed guard)
TRUSTED_PROXY_HOPS=0                         # proxies appending X-Forwarded-For; measure on deploy
```

Load it through `pydantic-settings` in `core/config.py`. Never read `os.environ` scattered around the code.

- `DATABASE_URL`, `JWT_SECRET` (≥32 chars) and `CRON_SECRET` are required: the app refuses to start without them.
- With `STORAGE_BACKEND=supabase` (the default), `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are required too; placeholders are rejected at startup. Local commands against `lm_dev`/`lm_test` can set `STORAGE_BACKEND=memory`.
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
- Rules that need the stored row (e.g. PATCH merged-state checks) raise `Unprocessable(msg, field=...)`, which returns FastAPI's 422 list shape.
- Enums, units and regions live in `core/instrument_types.py` and `core/regions.py`; application/document types in `core/application_types.py`. The frontend gets them from `GET /instruments/meta` and `GET /applications/meta`.
- **Row locks re-read:** every `with_for_update()` re-check uses `.execution_options(populate_existing=True)`. Otherwise the identity map returns the stale pre-lock copy.
- **Audit-writing GETs commit in the service** (e.g. `GET /documents/{id}/url` writes `DOCUMENT_URL_ISSUED`).

## Data model

Tables: `users`, `organizations`, `refresh_tokens`, `instruments`, `applications`, `documents`, `inspections`,
`inspection_checklist`, `certificates`, `payments` (mocked), `audit_logs`

- `users`: DB check constraints tie `role` to `organization_id` (BUSINESS/GATC need one, officials must not) and require `state_code`/`district_code` for officials.
- `refresh_tokens`: SHA-256 `token_hash` only, never the raw token.
- `audit_logs`: append-only. Write rows through `services/audit.log(db, *, actor, action, entity_type, entity_id, organization_id, details, ip)` in the caller's transaction. Routers pass `ip=get_client_ip(request)`.
- `instruments` (spec `docs/specs/02-instruments.md`):
  - `instrument_uid` = `LM-{state}-{district}-{nextval('instrument_uid_seq'):06d}`. It's global, so there are gaps. It's permanent, even if the location changes, and never a credential.
  - Global unique index `ix_instruments_mfr_serial` on `(lower(manufacturer), serial_number)`. The index is the duplicate check: catch the `IntegrityError` → 409. Serial numbers are stored uppercased.
  - Delete is blocked by `ON DELETE RESTRICT` once **any** application exists (→ 409). While a non-terminal application exists (DRAFT included), `LOCKED_FIELDS` (identity + state/district) → 409; address/lat/lng stay editable until step 5.
  - `InstrumentOut.active_application` (one LEFT JOIN); reported as `null` to officials while it's a DRAFT.
- `applications` (spec `docs/specs/03-applications.md`):
  - `application_number` = `APP-{UTC year}-{nextval('application_number_seq'):06d}`, display only.
  - One active (non-terminal) application per instrument: partial unique index `ux_applications_active_instrument`.
  - `state_code`/`district_code` are a snapshot of the instrument's location (locked while active).
  - `application_status_history` is append-only and feeds the timeline (businesses can't read `audit_logs`).
  - **Officials never see DRAFT applications or their documents** (`scope_applications`).
- `documents`: `storage_path` = `applications/{application_id}/{document_id}.{pdf|jpg|png}` (never a URL, never the user's filename). `content_type` is the **sniffed** type. Max 10 per application.

- UUID primary keys everywhere. Human-readable IDs are for display only:
  - instrument `instrument_uid`: `LM-JH-DHN-000123`
  - certificate `certificate_number`: `LM-CERT-2026-001245`
- `instruments`: plain `latitude` / `longitude` columns (no PostGIS).
- `documents`: store `storage_path` only. **Never store public URLs.**
- `certificates`: `valid_from`, `valid_until`, `status`, `pdf_path`, `qr_token`, `data_hash` (SHA-256 of the certificate fields).

## Application status flow

```
DRAFT → SUBMITTED → DOCUMENT_REVIEW → SCHEDULED → INSPECTION
      → APPROVED | REJECTED → CERTIFICATE_ISSUED
```

- Enforce it through an `ALLOWED_TRANSITIONS` map in `services/applications.py`: `(from, to) → Edge(roles, enabled)`. Later steps flip `enabled`.
- Enabled in step 3: DRAFT → SUBMITTED (BUSINESS, all required documents present), SUBMITTED → DOCUMENT_REVIEW (LM_OFFICER), DOCUMENT_REVIEW → REJECTED (LM_OFFICER, `note` 10–1000 chars).
- `PATCH /applications/{id}/status` evaluation order: out of scope → 404; not an edge → 409 `Invalid status change`; wrong role → 403; not enabled → 409 `This action is not available yet`; edge rules → 409/422; apply (row lock, history row, audit row, one transaction).
- `ApplicationDetail.allowed_actions` lists the enabled edges the caller's role may take (requirements not considered).
- The status PATCH endpoint validates against that map and the caller's role. It never sets an arbitrary status.
- **APPROVED → CERTIFICATE_ISSUED happens in the same DB transaction** as certificate creation.
- REJECTED is terminal. Re-verification means a new application.

Certificate status: `VALID` · `EXPIRED` · `REVOKED`

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
POST  /api/inspections           POST  /api/inspections/{id}/submit
GET   /api/certificates/{id}     GET   /api/certificates/{id}/pdf
POST  /api/jobs/expiry-check     # requires X-Cron-Secret header
GET   /api/public/verify/{certificate_number}                     # no auth
GET   /api/applications/meta       # types, statuses, document types + requirements, upload limits
CRUD  /api/applications            # write: BUSINESS, DRAFT only; read: + officials (non-DRAFT, jurisdiction)
DELETE /api/documents/{id}         # BUSINESS, DRAFT only
```

### Public verify
- Returns **only** certificate number, instrument type/model/serial, `valid_until` and status.
- No owner PII, no documents, no internal IDs.
- Computes status **live**: if `valid_until < today`, return EXPIRED even if the cron hasn't run yet.
- Rate-limited.

### QR
- Encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`. Never localhost.
- The DB is the source of truth, never the PDF or QR.

### Expiry job
- 30 days before expiry → reminder. 7 days before → urgent reminder. Past expiry → set `EXPIRED`.
- Must be idempotent: running it twice in one day sends no duplicate emails.

## Auth and RBAC (spec: `docs/specs/01-login-rbac.md`)

- Protect endpoints with `Depends(require_roles(Role.X, ...))` from `core/deps.py`. The role hierarchy never grants permissions: list the allowed roles explicitly.
- `get_current_user` reloads the user from the DB on every request. It rejects inactive users and tokens whose `role`/`org_id` claims are stale.
- Services raise domain errors from `core/errors.py` (`AuthError`, `Forbidden`, `NotFound`, `Conflict`, `RateLimited`), never `HTTPException`.
- **Commit-then-raise:** after a security-relevant write (failed-login audit, token revocation), `db.commit()` before raising.
- Cookies: `lm_refresh` (httpOnly, `Path=/api/auth`) holds the refresh token; `lm_session=1` (httpOnly, `Path=/`) is a presence flag for the frontend `proxy.ts`.
- Refresh rotates on every call. A revoked token seen again within 10 s is a lost race (401, cookies kept); after that it revokes the user's whole token family.
- Rate limits are in-memory (`core/rate_limit.py`): login 5/min per email + 20/min per IP, register 10/hour per IP. **Production shortcut:** resets on restart, not shared across instances.
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
