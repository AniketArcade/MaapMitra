# Deployment Guide

Three services, deployed in this order: **Supabase → Render (backend) → Vercel (frontend)**.
Deploy in this order because each later step needs values (URLs, keys) from the one before it.

> Architecture reminder (`CLAUDE.md`): frontend never talks to Supabase directly. Everything goes
> Frontend → FastAPI (Render) → Supabase.

---

## 0. Prerequisites

- GitHub repo pushed (Render/Vercel both deploy from Git)
- Accounts: [Supabase](https://supabase.com), [Render](https://render.com), [Vercel](https://vercel.com), [Resend](https://resend.com)
- Local Python 3.12 + Node (for running migrations/build locally before deploying, if needed)

---

## 1. Supabase (Postgres + Storage)

1. Create a new Supabase project. Note the **project ref** and **DB password** you set.
2. **Get the connection string** — Dashboard → Connect → **Session pooler** (port `5432`,
   `*.pooler.supabase.com`).
   - ⚠️ Do **not** use the direct host (IPv6-only, Render can't reach it) or the transaction
     pooler on port `6543` (breaks psycopg prepared statements).
3. **Get the service role key** — Dashboard → Project Settings → API → `service_role` secret.
   Never expose this to the frontend.
4. Storage bucket (`documents`) is created **by the backend CLI**, not the dashboard — see step 2.6
   below. Do nothing here yet.
5. You will run Alembic migrations against this DB from your machine in step 2.5 (root `CLAUDE.md`:
   Claude applies migrations directly to Supabase — never edit tables via the dashboard).

Collect for later:
```
DATABASE_URL   = postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
SUPABASE_URL   = https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY = <service_role secret>
```

---

## 2. Backend → Render

### 2.1 Create the Web Service
- Render Dashboard → New → Web Service → connect the repo.
- **Root directory:** `backend`
- **Runtime:** Python 3.12
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 2.2 Get a Resend API key
- [resend.com](https://resend.com) → create API key, verify a sending domain (or use their test
  domain for the demo). Note the key and the "from" address.

### 2.3 Set environment variables on Render
```env
DATABASE_URL=<Supabase session pooler string from step 1>
JWT_SECRET=<random string, 32+ chars>            # e.g. `openssl rand -hex 32`
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=7
SUPABASE_URL=<from step 1>
SUPABASE_SERVICE_ROLE_KEY=<from step 1>
SUPABASE_BUCKET=documents
STORAGE_BACKEND=supabase
PUBLIC_BASE_URL=https://<your-app>.vercel.app    # placeholder now, fix after step 3
CORS_ORIGINS=http://localhost:3000,https://<your-app>.vercel.app
EMAIL_BACKEND=resend
RESEND_API_KEY=<from step 2.2>
RESEND_FROM_EMAIL=<verified sender from step 2.2>
CRON_SECRET=<random string>                      # e.g. `openssl rand -hex 32`
ENV=production
TRUSTED_PROXY_HOPS=0                              # revisit after first deploy, see 2.7
APP_TIMEZONE=Asia/Kolkata
SCHEDULING_MAX_DAYS_AHEAD=180
EXPIRY_REMINDER_30D_DAYS=30
EXPIRY_REMINDER_7D_DAYS=7
```
`DATABASE_URL`, `JWT_SECRET`, `CRON_SECRET` are required or the app refuses to start.

Deploy the service. It will fail on first boot if `SUPABASE_*` or `RESEND_*` are placeholders —
that's intentional (startup config validation).

### 2.4 Run migrations against Supabase (from your machine)
```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL="<same Supabase session pooler string>" alembic upgrade head
DATABASE_URL="<same string>" alembic current       # verify
DATABASE_URL="<same string>" alembic check          # verify no drift
```

### 2.5 Create the storage bucket
```bash
DATABASE_URL="<Supabase string>" \
SUPABASE_URL="<from step 1>" \
SUPABASE_SERVICE_ROLE_KEY="<from step 1>" \
python -m app.cli create-bucket
```

### 2.6 Seed demo data (optional, for the ABC Traders demo story)
```bash
DATABASE_URL="<Supabase string>" \
SUPABASE_URL="<from step 1>" \
SUPABASE_SERVICE_ROLE_KEY="<from step 1>" \
python -m app.seed --password '<demo password>'
```
Idempotent — safe to re-run.

### 2.7 Create your first SUPER_ADMIN
```bash
DATABASE_URL="<Supabase string>" python -m app.cli create-superadmin --email you@example.com
```

### 2.8 Verify the backend is up
```bash
curl https://<your-render-app>.onrender.com/api/health
curl https://<your-render-app>.onrender.com/api/health?db=true   # pings DB
```

### 2.9 Measure `TRUSTED_PROXY_HOPS`
After the frontend is deployed (step 3) and a real request flows Vercel rewrite → Render, check
what `X-Forwarded-For` looks like in a log line and set `TRUSTED_PROXY_HOPS` accordingly
(`core/deps.py: get_client_ip`). Wrong value = rate limiting reads the wrong IP.

Note the Render URL — you need it next: `https://<your-render-app>.onrender.com`

---

## 3. Frontend → Vercel

### 3.1 Import the project
- Vercel Dashboard → Add New → Project → import the repo.
- **Root directory:** `frontend`
- Framework preset: Next.js (auto-detected).

### 3.2 Set environment variables on Vercel
```env
API_ORIGIN=https://<your-render-app>.onrender.com
```
This is **required** — the build fails without it. No secrets, no Supabase keys, no DB URLs go
here (frontend never touches Supabase directly).

Optional, only if Vercel caps proxied upload body size in practice:
```env
NEXT_PUBLIC_UPLOAD_ORIGIN=https://<your-render-app>.onrender.com
```

### 3.3 Deploy
Vercel builds and deploys automatically on push to `main` once linked.

### 3.4 Fix up cross-references
Now that you have the real Vercel URL, go back and update on **Render**:
```env
PUBLIC_BASE_URL=https://<your-real-app>.vercel.app     # used to build QR codes
CORS_ORIGINS=http://localhost:3000,https://<your-real-app>.vercel.app
```
Redeploy the backend after changing these.

---

## 4. Daily expiry job (cron)

`POST /api/jobs/expiry-check` needs the `X-Cron-Secret` header (value = `CRON_SECRET` from step
2.3). Pick one runner (open decision in root `CLAUDE.md` — Render Cron vs GitHub Actions):

**Option A — Render Cron Job** (separate from the web service):
- New → Cron Job → command: `curl -X POST -H "X-Cron-Secret: $CRON_SECRET" https://<your-render-app>.onrender.com/api/jobs/expiry-check`
- Schedule: daily, e.g. `0 3 * * *` (adjust for `Asia/Kolkata`).

**Option B — GitHub Actions**, `.github/workflows/expiry-check.yml`:
```yaml
on:
  schedule:
    - cron: "30 21 * * *"   # 03:00 IST
jobs:
  expiry-check:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -f -X POST -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            https://<your-render-app>.onrender.com/api/jobs/expiry-check
```
Add `CRON_SECRET` as a GitHub Actions repo secret.

Either way — pick one, don't run both (double-sends reminders would be idempotent per-certificate,
but there's no reason to run it twice).

---

## 5. Post-deploy smoke test (the demo story)

1. Log in as the seeded ABC Traders business user (or the SUPER_ADMIN you created).
2. Confirm the weighing scale instrument (`XYZ12345`) and its application appear.
3. Walk one application through: submit → officer review → schedule → inspect → approve →
   issue certificate.
4. Open `/certificates/[id]`, confirm the QR renders and **View PDF** works (signed URL from
   Supabase Storage).
5. Scan or open `/verify/<certificate_number>` in an incognito tab (no login) — confirms
   `PUBLIC_BASE_URL` was set correctly and shows ✓ VALID.
6. Check `/admin` (as an admin role) shows certificate counts.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Backend won't boot | Placeholder `SUPABASE_*`/`RESEND_*` values, or `DATABASE_URL`/`JWT_SECRET`/`CRON_SECRET` missing |
| 500s connecting to DB | Used the direct host or transaction pooler instead of the session pooler (port 5432) |
| Login works but refresh cookie doesn't persist | `CORS_ORIGINS` missing the real Vercel URL, or `API_ORIGIN` wrong on Vercel (cookie must stay first-party through the `/api/*` rewrite) |
| QR points to `localhost` | `PUBLIC_BASE_URL` not updated after the Vercel URL was known (step 3.4) |
| Rate limiting looks wrong / blocks the wrong users | `TRUSTED_PROXY_HOPS` not measured for the real Vercel→Render hop count (step 2.9) |
| Uploads fail | Bucket not created (`python -m app.cli create-bucket`), or file >10 MB / wrong type |
| Cron job 401s | `X-Cron-Secret` header missing or doesn't match `CRON_SECRET` |

## Notes / open decisions (see root `CLAUDE.md`)

- Cron runner choice (Render Cron vs GitHub Actions) is still open — pick one in §4 and update
  `CLAUDE.md`.
- Digital signature is hash-based only in this MVP (no government e-sign).
- Rate limiting is in-memory on the backend — resets on restart, not shared across multiple Render
  instances. Fine for a single-instance MVP; flag before scaling out.
