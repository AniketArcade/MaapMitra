# Backend — FastAPI

Project-wide rules are in `../CLAUDE.md`. This file covers the backend only. Per-feature history,
decisions and out-of-scope lists live in `../docs/specs/NN-*.md`; this file keeps rules and invariants.

## Commands

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000  (docs: /docs, schema: /openapi.json)
pytest                               # needs local Postgres DB lm_test (see Testing)
ruff check . && ruff format .
alembic revision --autogenerate -m "msg" --rev-id NNNN
alembic upgrade head
python -m app.seed --password '...'  # demo data (see database/seed/README.md)
python -m app.cli create-superadmin --email you@example.com
python -m app.cli create-bucket      # private documents bucket (once per environment)
```

## Structure

```text
backend/app/
├── main.py        # app factory, CORS, middleware, routers, error handlers
├── core/          # config, security, deps, roles, errors, rate limits, enums/templates, regions, clock
├── db/            # engine, session, base + mixins
├── middleware/    # body_limit.py (upload size, before multipart parsing)
├── models/        # SQLAlchemy models
├── schemas/       # Pydantic request/response models (requests extend StrictModel)
├── services/      # business logic, scoping.py, status transitions, audit
├── routers/       # thin handlers: health auth users instruments applications documents inspections
│                  #   certificates public jobs admin gatc audit organizations
├── storage/       # Storage protocol: SupabaseStorage (REST) + MemoryStorage (tests)
├── email/         # EmailSender protocol: ResendEmail + MemoryEmail (tests)
├── pdf/           # certificate.py — ReportLab PDF + segno QR
├── cli.py  seed.py  seed_files.py
backend/{alembic,tests,requirements.txt,.env.example}
```

## Environment (`.env`)

```env
DATABASE_URL=postgresql+psycopg://...        # Supabase SESSION pooler (port 5432, *.pooler.supabase.com)
JWT_SECRET=...                               # >= 32 chars
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=7
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...                # backend only, NEVER expose
SUPABASE_BUCKET=documents
STORAGE_BACKEND=supabase                     # supabase | memory (memory = tests/local only)
PUBLIC_BASE_URL=https://<app>.vercel.app     # used in QR codes
CORS_ORIGINS=http://localhost:3000,https://<app>.vercel.app
EMAIL_BACKEND=resend                         # resend | memory
RESEND_API_KEY=...
RESEND_FROM_EMAIL=...
CRON_SECRET=...
ENV=development                              # development | test | production (cookie Secure flag, seed guard)
TRUSTED_PROXY_HOPS=0                         # proxies appending X-Forwarded-For; see Rate limits & client IP
APP_TIMEZONE=Asia/Kolkata                    # "today" for scheduling. ASSUMPTION: India deployment
SCHEDULING_MAX_DAYS_AHEAD=180
EXPIRY_REMINDER_30D_DAYS=30                  # ASSUMPTION: not a real Legal Metrology rule
EXPIRY_REMINDER_7D_DAYS=7                    # ASSUMPTION
```

- Load only via `pydantic-settings` in `core/config.py`; never read `os.environ` elsewhere.
- Required at startup: `DATABASE_URL`, `JWT_SECRET`, `CRON_SECRET`; plus Supabase vars when `STORAGE_BACKEND=supabase`, Resend vars when `EMAIL_BACKEND=resend`. Placeholders are rejected. `ConfigError` names fields, never values.
- In `.env`, never put a `# comment` on the same line as an empty value (python-dotenv reads it as the value).
- `SUPABASE_URL` is normalised to its origin. Use the **Session pooler** URL: the direct host is IPv6-only (Render can't reach it) and the transaction pooler (6543) breaks psycopg prepared statements.

## Migrations

`backend/.env` points at **Supabase**. For local work override it: `DATABASE_URL=postgresql+psycopg://localhost/lm_dev`.

1. `alembic revision --autogenerate -m "<name>" --rev-id <NNNN>` against local `lm_dev`.
2. Hand-review. Autogenerate misses enum drops in `downgrade`, sequences and data migrations.
3. Round-trip: `upgrade head` → `downgrade -1` → `upgrade head`, then `alembic check` (no drift).
4. `pytest` (migrates `lm_test` from scratch).
5. **Claude applies it to Supabase** (`alembic upgrade head`), verifies with `alembic current` + `alembic check`, re-runs the (idempotent) seed if needed.
6. Add it to the table below. From then on it is **frozen**: never edit, write a new one.

Never edit tables in the Supabase dashboard. All revisions below are applied to Supabase (head `0013`).

| Rev | Content | Spec |
|---|---|---|
| `0001` | organizations, users, refresh_tokens, audit_logs | 01 |
| `0002` | instruments (+ `instrument_uid_seq`, functional unique index) | 02 |
| `0003` | applications, application_status_history, documents (+ `application_number_seq`) | 03 |
| `0004` | inspections | 05 |
| `0005` | inspection checklist items + measurements, `INSPECTION_EVIDENCE` doc type | 06 |
| `0006` | certificates (+ `certificate_number_seq`) | 08 |
| `0007` | certificate reminder columns (`reminder_30d_sent_at`, `reminder_7d_sent_at`) | 10 |
| `0008` | document review checklist, `DOCUMENTS_DEFICIENT` status | 11 |
| `0009` | `instruments.transportable`, `applications.verification_mode` | 14 |
| `0010` | certificate superseding (`SUPERSEDED`, self-referential FKs) | 13 |
| `0011` | payments (mocked, informational) | 12 |
| `0012` | `instrument_categories` (33 seeded rows), `instruments.category_id/category_values` | 16 |
| `0013` | `organizations.gatc_eligible_category_ids`, `inspections.assignee_role` | 15 |

⚠️ `0012`'s 33 seeded category rows are invented-but-plausible fixture data and have **never been
content-reviewed** (names, fields, options, units). Ask before trusting them in a live demo.

## Layering rules

- **Routers are thin:** parse input, check auth, call a service, return a schema.
- **Services own the logic:** status transitions, org isolation, audit logging, certificate generation.
- Pydantic schemas are separate from SQLAlchemy models; never return ORM objects. **Every request schema extends `StrictModel`** (`extra="forbid"` → unknown fields 422).
- Every new endpoint needs a schema, an RBAC dependency, an audit entry and at least one test. Type hints everywhere; `ruff`.
- Services raise domain errors from `core/errors.py` (`AuthError`, `Forbidden`, `NotFound`, `Conflict`, `Unprocessable`, `RateLimited`), never `HTTPException`. `Unprocessable(msg, field=...)` returns FastAPI's 422 list shape.
- **Every read of org-owned data goes through a `scope_*` helper** in `services/scoping.py`. Out of scope → 404, never 403. Scoping fails closed. Load the row with one scoped query; never load first and check ownership after.
- Lists return `Page[T]` (`{items,total,page,page_size}`) via `PageParams` (page ≥ 1, page_size ≤ 100), stable order (`created_at desc, id`). Bounded reference lists (e.g. state overview) return a bare list.
- **Never let a client aggregate paged data.** Add a server-side stats/count endpoint using the same `scope_*` query (see `GET /applications/stats`).
- Enums, labels, templates live in `core/` (`instrument_types`, `regions`, `application_types`, `verification_types`, `payment_types`, `inspection_templates`, `document_review_templates`) and are served to clients via the `/meta` endpoints. Clients never hard-code them.
- **Row locks re-read:** every `with_for_update()` re-check uses `.execution_options(populate_existing=True)`, otherwise the identity map returns the stale pre-lock copy (this once allowed a double-issue race).
- **Lock order** when a transaction needs both: application row, then instrument row. Lock the instrument with a **bare** `SELECT ... FOR UPDATE`, not `instruments_service.get()` (its joinedload would re-hydrate the just-mutated application from stale DB state).
- **Commit-then-raise:** after a security-relevant write (failed-login audit, token revocation), `db.commit()` before raising. Audit-writing GETs commit in the service (e.g. `DOCUMENT_URL_ISSUED`).
- Audit: `services/audit.log(db, *, actor, action, entity_type, entity_id, organization_id, details, ip)` in the caller's transaction; routers pass `ip=get_client_ip(request)`. `audit_logs` is append-only; `actor=None` is the system actor (expiry job, CLI).
- UUID primary keys everywhere (except `instrument_categories`, smallint 1–33). Human-readable IDs are display-only: `instrument_uid` = `LM-{state}-{district}-{seq:06d}`, `application_number` = `APP-{year}-{seq:06d}`, `certificate_number` = `LM-CERT-{year}-{seq:06d}`.

## Data model (invariants only; columns are in `app/models/`)

Tables: `users`, `organizations`, `refresh_tokens`, `instruments`, `instrument_categories`, `applications`,
`application_status_history`, `documents`, `inspections`, `inspection_checklist_items`,
`inspection_measurements`, `document_review_checklist_items`, `certificates`, `payments`, `audit_logs`.

- `users`: DB checks tie `role` to `organization_id` (BUSINESS/GATC need one, officials must not) and require `state_code`/`district_code` for officials. `refresh_tokens` store a SHA-256 `token_hash` only.
- `instruments`: global unique index on `(lower(manufacturer), serial_number)` is the duplicate check (catch `IntegrityError` → 409); serials stored uppercase. Plain `latitude`/`longitude` (no PostGIS). Delete is blocked (`RESTRICT` → 409) once any application exists.
  - **Locking:** `core/instrument_lock.py: locked_fields(active_status)` is the single source of truth for PATCH checks and `InstrumentOut.locked_fields`. Identity fields (manufacturer, model, serial, capacity, unit, accuracy class, state/district, `transportable`, `category_id`/`category_values`) lock while any non-terminal application exists (DRAFT included); address/lat/lng additionally lock from SCHEDULED/INSPECTION/APPROVED. Lock lifts at REJECTED or CERTIFICATE_ISSUED. Clients disable exactly `locked_fields`.
  - `category_id`/`category_values` are an optional, **paired** (both or neither) richer category system alongside the legacy `instrument_type`/capacity fields. Validation is top-level required-field presence only (`_validate_category`); repeater contents, range ordering and unit membership are deliberately not validated (spec 16).
  - `transportable` (default true) is snapshotted onto `applications.verification_mode` at creation (`true → OFFICE_TEST_CENTRE`, `false → ON_SITE`), never re-derived (spec 14).
- `applications`: one active (non-terminal) per instrument (partial unique index `ux_applications_active_instrument`). `state_code`/`district_code` snapshot the instrument's location. `application_status_history` is append-only and feeds the timeline (businesses can't read `audit_logs`). **Officials never see DRAFT applications or their documents.**
- `documents`: store `storage_path` only (`applications/{application_id}/{document_id}.{pdf|jpg|png}`), **never a URL or the user's filename**. `content_type` is the sniffed type. Max 10 per application (separate cap for inspection evidence photos).
- `inspections`: one per application, created at `DOCUMENT_REVIEW → SCHEDULED`. `assigned_officer_id` is the scheduling `LM_OFFICER` or an explicitly routed `GATC` user; `assignee_role` is denormalised at assignment. `submitted_at` is the single source of truth for "checklist locked". No status column: the application status is the source of truth. Checklist/measurement rows are **snapshotted** from templates when inspection starts; the document-review checklist is snapshotted when the application enters `DOCUMENT_REVIEW` and reset (not recreated) on re-entry.
- `certificates`: one per application (`RESTRICT`), created only by `services/certificates.py: issue()` (never via `transition()`). `snapshot` (JSONB) freezes instrument/business/approver fields at issuance. Validity = issue date + `CERTIFICATE_VALIDITY_YEARS` (default 2, ASSUMPTION). Status `VALID · EXPIRED · REVOKED · SUPERSEDED`: the expiry job is the only writer of `EXPIRED`; `issue()` is the only writer of `SUPERSEDED` (in the same transaction as the new row, with a `db.flush()` between insert and update for FK order); `REVOKED` has no writer yet. `data_hash` is a SHA-256 tamper-evidence fingerprint, not a signature. QR encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}` (never localhost), is regenerated per GET, never stored; the DB is the source of truth.
- `payments`: **purely informational** (spec 12). `POST /applications/{id}/mock-pay` (BUSINESS) lazily creates a `PAID` row; no transition reads or gates on it (`tests/test_payments.py::test_payment_never_gates_the_lifecycle`).

## Application status flow

```
DRAFT → SUBMITTED → DOCUMENT_REVIEW → SCHEDULED → INSPECTION → APPROVED | REJECTED
              ⇄ DOCUMENTS_DEFICIENT                          APPROVED → CERTIFICATE_ISSUED
```

- Enforced by the `ALLOWED_TRANSITIONS` map in `services/applications.py`: `(from, to) → Edge(roles, enabled)`. The status PATCH never sets an arbitrary status.
- Evaluation order in `PATCH /applications/{id}/status`: out of scope → 404; not an edge → 409 `Invalid status change`; wrong role → 403; not enabled → 409; edge rules → 409/422; apply (row lock, history row, audit row, one transaction).
- Edge rules: `DRAFT→SUBMITTED` (BUSINESS, all required documents present) · `SUBMITTED→DOCUMENT_REVIEW` (LM_OFFICER) · `DOCUMENT_REVIEW→DOCUMENTS_DEFICIENT` / `→REJECTED` (LM_OFFICER, `note` 10–1000 chars) · `DOCUMENTS_DEFICIENT→SUBMITTED` (BUSINESS resubmit; not terminal) · `DOCUMENT_REVIEW→SCHEDULED` (LM_OFFICER, `scheduled_date` required and only allowed here, between `today()` and `+SCHEDULING_MAX_DAYS_AHEAD`; **409 until every document-review checklist row is checked**; optional paired `gatc_organization_id`/`gatc_user_id` routes to a GATC user) · `SCHEDULED→INSPECTION` (assigned LM_OFFICER/GATC only) · `INSPECTION→APPROVED|REJECTED` (any in-scope LM_OFFICER, or the assigned GATC user; **409 until `inspections.submitted_at` is set**).
- `APPROVED → CERTIFICATE_ISSUED` is `Edge(frozenset(), enabled=False)`: system-only. `POST /applications/{id}/certificate` (`issue()`, any in-scope LM_OFFICER) bypasses `transition()`; render PDF and `storage.put()` **before** locking, then lock the application row (`populate_existing=True`), re-check, insert certificate + flip status in one commit. GATC never issues.
- `ApplicationDetail.allowed_actions` lists the enabled edges the caller may take (filtered by the same identity/submitted conditions) so the UI never shows a button that would 409.
- REJECTED and CERTIFICATE_ISSUED are terminal; re-verification is a new application (`RE_VERIFICATION` type).
- `today()` is in `core/clock.py` (built on `now_utc()`, monkeypatch it in tests; no freezegun). A UTC-only check would reject valid IST dates for 5h30m around midnight.

### GATC (spec 15, 20)
- `GATC` is a role with an org; `organizations.gatc_eligible_category_ids` (JSONB, `none_as_null=True` — otherwise Python `None` writes `'null'::jsonb` and breaks the CHECK) says which categories it may test. Routing needs: GATC org in the officer's jurisdiction, instrument category in the org's eligible list, and `verification_mode == OFFICE_TEST_CENTRE`. Bad reference → 422; legit reference blocked by a business rule → 409.
- GATC then uses the **same** inspection machinery as `LM_OFFICER`; `scope_applications()`'s GATC branch is the narrowest of any role (exactly the application(s) they are `assigned_officer_id` of, via a correlated `EXISTS`).

## API

Base `/api`, REST + JSON. OpenAPI at `/openapi.json` is the contract for web and mobile clients.

```http
GET   /health                 # liveness; ?db=true pings DB (503 if down)
POST  /auth/{login,register,refresh,logout}      GET /auth/me
GET   /instruments/meta  /applications/meta  /inspections/meta     # reference data, any logged-in user
GET   /public/regions         # no auth: state/district list for the register form
GET   /public/verify/{certificate_number}        # no auth, 30/min/IP
CRUD  /instruments            # write: BUSINESS own org; read: + officials in jurisdiction; GATC 403
CRUD  /applications           # write: BUSINESS, DRAFT only; read: + officials (non-DRAFT) + GATC (own assignment)
GET   /applications/stats     # {total, by_status}, same scope as list, zero-filled
GET   /applications?sort=created_desc|scheduled_asc&state_code=&district_code=&status=&q=
PATCH /applications/{id}/status  /inspection (reschedule, LM_OFFICER)  /review-checklist (LM_OFFICER)
POST  /applications/{id}/certificate (LM_OFFICER)   /mock-pay (BUSINESS)
POST  /documents  DELETE /documents/{id}  GET /documents/{id}/url?disposition=inline|attachment
GET   /inspections/{id}   PATCH /inspections/{id}   POST /inspections/{id}/submit
GET   /certificates  /certificates/{id}  /certificates/{id}/pdf
GET   /gatc/eligible?category_id=  /gatc/{organization_id}/users            # LM_OFFICER only
GET   /users  POST /users  PATCH /users/{id}     # admin ranks, strictly-lower-rank targets, own jurisdiction
GET   /audit-logs  /organizations?type=GATC  /admin/state-overview  /admin/district-overview
GET   /admin/certificates/{stats,expiring-soon}  # ADMIN_ROLES + LM_OFFICER
POST  /jobs/expiry-check      # X-Cron-Secret header only, no JWT, no rate limit
```

Role-by-endpoint detail: `core/roles.py` (`ADMIN_ROLES`, `OFFICIAL_ROLES`, `ROLE_RANK`) and each router's `require_roles(...)`. Jurisdiction rules for admins are in specs 17/18/21; officer in 19; GATC in 15/20.

- `PublicVerifyOut` is a deliberate allow-list: `certificate_number, status, instrument_type_label, instrument_uid, manufacturer, model, serial_number, valid_from, valid_until, issued_by`. No owner PII, documents, internal IDs, supersede chain, `pdf_path`/`data_hash`, and never a link to the PDF. Check specs 09/13 before adding a field. Status is computed live by `core/certificate_status.effective_status()` (stored `REVOKED` wins, else `valid_until < today` → `EXPIRED`), so it is correct before the expiry job runs; the job uses the same function. No audit row per verify.
- Expiry job (spec 10): scans `VALID` certificates; sends 30-day/7-day reminders to the org's BUSINESS users once each (idempotent via `reminder_*_sent_at`, set only after a successful send), then flips to `EXPIRED`. Per-certificate `try`/`except` and commits; only `CERTIFICATE_EXPIRED` is audited. Triggered daily by GitHub Actions (`.github/workflows/`).
- User management (specs 17/18/21): `users` has no `scope_*` helper, so `services/users.py` enforces jurisdiction itself — a mismatched client `state_code`/`district_code` → 422 (reject, never silently override), a peer-or-higher role filter → 403, `PATCH` target must be strictly lower rank in the actor's jurisdiction, self-deactivation → 409 (checked first). `POST /users` is SUPER_ADMIN and STATE_ADMIN only. Audit-log jurisdiction filtering goes through the actor's `users`/`organizations` columns; system-actor rows are invisible to non-super admins (disclosed gap).
- Case counts ("pending" vs "completed") everywhere use `TERMINAL_STATUSES` (`REJECTED`, `CERTIFICATE_ISSUED`) as the single boundary. When building certificate-count queries on `scope_certificates()`, **never join `Application` again** (it already joins internally).

## Auth and RBAC (spec 01)

- Protect endpoints with `Depends(require_roles(Role.X, ...))` (`core/deps.py`). The role hierarchy never grants permissions: list allowed roles explicitly. `ROLE_RANK` is only for "who may manage whom".
- `get_current_user` reloads the user from the DB per request; rejects inactive users and stale `role`/`org_id` claims. Access token is a short-lived JWT; **re-check ownership in services** regardless of claims.
- Refresh tokens rotate on every call. A revoked token seen again within 10 s is a lost race (401, cookies kept); later, it revokes the user's whole token family.
- **Web clients:** refresh token in the httpOnly `lm_refresh` cookie (`Path=/api/auth`), plus `lm_session=1` presence flag for the Next.js `proxy.ts`.
- **Mobile clients** (`routers/auth.py: _is_mobile`): send header `X-Client: mobile`. Register/login/refresh then return `refresh_token` in the `AuthResponse` JSON and set **no cookies**; `/auth/refresh` and `/auth/logout` take `{"refresh_token": "..."}` (`RefreshRequest`, strict) and ignore cookies entirely. The app keeps the token in secure storage. Web requests (no header) are unchanged: cookies set, `refresh_token` is `null` in the body, the body is ignored. Rotation, reuse grace and audit are the same shared service code. Tests: `tests/test_auth_mobile.py`.
- Passwords: Argon2, one dummy verify on unknown email (timing).
- **Rate limits & client IP:** in-memory (`core/rate_limit.py`): login 5/min per email + 20/min per IP, register 10/hour/IP, public verify 30/min/IP, uploads 60/hour/user. **Production shortcut:** resets on restart, not shared across instances. `get_client_ip` takes the Nth `X-Forwarded-For` entry from the right (`TRUSTED_PROXY_HOPS`); web goes Vercel rewrite → Render, a native app goes straight to Render, so the hop count differs per path — measure on deploy and never trust the leftmost entry.
- CORS (`CORS_ORIGINS`) only matters for direct browser calls; browser traffic normally arrives same-origin through the Next.js `/api/*` rewrite. Native apps ignore CORS.

## Documents and storage

- `SupabaseStorage` talks REST via `httpx2` with the service role key (no SDK); the key is never logged. Bucket is private with bucket-level size/MIME limits (`python -m app.cli create-bucket`). Certificates live in the same bucket (`certificates/{id}.pdf`).
- `BodySizeLimitMiddleware` on `POST /api/documents`: no `Content-Length` → 411; over 10 MiB + 64 KiB → 413 without reading. **Phone photos can exceed this; clients must compress before upload.**
- Upload order: rate limit → scope + DRAFT + count pre-checks → read ≤ 10 MiB + 1 → sniff magic bytes (PDF/PNG/JPEG only, never trust extension) → `storage.put` **outside** any lock (failure → 502) → lock application row, re-check, insert, audit, commit → on failure after `put`, best-effort delete. Rare orphans are an accepted MVP risk.
- Evidence photos reuse this pipeline with `document_type=INSPECTION_EVIDENCE`: actor must be the assigned officer (identity check in `services/documents.py: _check_upload_allowed`), application in `INSPECTION`, not yet submitted. `BUSINESS_DOCUMENT_TYPES` excludes it so it never shows as a business requirement.
- Signed URLs: 300 s, issued only after the ownership/scope check, audited (`DOCUMENT_URL_ISSUED`, `CERTIFICATE_URL_ISSUED`). Default `disposition=inline`; `attachment` adds a sanitized `download=` name.

## Security (non-negotiable)

- Org isolation: every query for business data is scoped by the caller; test it explicitly.
- Uploads: PDF/JPG/PNG only, max 10 MB, real type sniffed server-side. Buckets private.
- Audit row on every create, status change, approve/reject and certificate issue. SQLAlchemy only — no string-built SQL.
- Never log secrets, tokens or passwords.

## Testing

- Tests run against **local Postgres** `lm_test` (override `TEST_DATABASE_URL`); `conftest.py` refuses to run against Supabase. Setup: `brew services start postgresql@15 && createdb lm_test`.
- Each run migrates `lm_test` down and up; each test truncates all tables after. Tests use real commits.
- Priorities: (1) org isolation, (2) RBAC per endpoint, (3) status transitions valid + invalid, (4) public verify for valid/expired/revoked, (5) expiry job idempotency.
- Widening a router's role set can flip other roles' expected 403 → 404 (out-of-scope convention); always run the full suite after touching `require_roles`.
