# Backend — FastAPI

Project-wide rules are in `../CLAUDE.md`. This file covers the backend only.

## Commands

> ⚠️ Assumed defaults. Update if the setup differs.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000  (docs: /docs)
pytest
ruff check . && ruff format .
alembic revision --autogenerate -m "msg"
alembic upgrade head
python -m app.seed                   # demo data
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
PUBLIC_BASE_URL=https://<app>.vercel.app     # used in QR codes
CORS_ORIGINS=http://localhost:3000,https://<app>.vercel.app
RESEND_API_KEY=...
CRON_SECRET=...
```

Load it through `pydantic-settings` in `core/config.py`. Never read `os.environ` scattered around the code.

## Layering rules

- **Routers are thin.** They parse input, check auth, call a service and return a schema.
- **Services own the logic:** status transitions, org isolation, audit logging, certificate generation.
- **Pydantic schemas are separate from SQLAlchemy models.** Never return ORM objects directly.
- Every new endpoint needs a schema, an RBAC dependency, an audit log entry and at least one test.
- Every schema change goes through Alembic. **Never edit tables in the Supabase dashboard.**
- Type hints everywhere. Lint and format with `ruff`.

## Data model

Tables: `users`, `organizations`, `instruments`, `applications`, `documents`, `inspections`,
`inspection_checklist`, `certificates`, `payments` (mocked), `audit_logs`

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

- Enforce it through an `ALLOWED_TRANSITIONS` map in `services/applications.py`.
- The status PATCH endpoint validates against that map and the caller's role. It never sets an arbitrary status.
- **APPROVED → CERTIFICATE_ISSUED happens in the same DB transaction** as certificate creation.
- REJECTED is terminal. Re-verification means a new application.

Certificate status: `VALID` · `EXPIRED` · `REVOKED`

## API

Base `/api`. REST + JSON.

```http
POST  /api/auth/{login,register,refresh,logout}
CRUD  /api/instruments
CRUD  /api/applications          PATCH /api/applications/{id}/status
POST  /api/documents             GET   /api/documents/{id}/url     # signed URL
POST  /api/inspections           POST  /api/inspections/{id}/submit
GET   /api/certificates/{id}     GET   /api/certificates/{id}/pdf
POST  /api/jobs/expiry-check     # requires X-Cron-Secret header
GET   /api/public/verify/{certificate_number}                     # no auth
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

## Testing priorities

1. Org isolation (business A cannot read business B)
2. RBAC per endpoint
3. Status transitions (valid and invalid)
4. Public verify for valid, expired and revoked certificates
5. Expiry job idempotency
