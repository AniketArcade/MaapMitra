# Legal Metrology Verification & Digital Certification Platform

Hackathon MVP. A digital lifecycle for Legal Metrology instrument verification:

```
Register instrument → Apply → Document review → Schedule → Field inspection
→ Approve/Reject → Certificate + QR → Public QR verification → Expiry → Re-verification
```

Physical verification stays a field activity. We digitize the workflow around it.

## Monorepo layout

```text
/
├── CLAUDE.md          ← you are here (project-wide rules)
├── frontend/          ← Next.js app       → see frontend/CLAUDE.md
├── backend/           ← FastAPI service   → see backend/CLAUDE.md
├── database/seed/     ← demo seed data
└── docs/
```

Work inside the relevant folder. Each folder's CLAUDE.md holds its own conventions and commands.

## Stack (decided)

| Layer | Choice | Host |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | Vercel |
| Backend | FastAPI + Pydantic + SQLAlchemy + Alembic | Render |
| Database | Supabase Postgres | Supabase |
| Files | Supabase Storage (private buckets, signed URLs) | Supabase |
| Auth | Own JWT + RBAC in FastAPI | — |
| Email | Resend | — |
| Expiry job | Daily cron calling a protected endpoint | Render Cron / GitHub Actions |

**Three deployments total:** Vercel, Render, Supabase.

### Architecture rules
- Frontend → FastAPI → Supabase. **The frontend never touches the database or Supabase directly.**
- Supabase is used for Postgres + Storage **only**. No Supabase Auth, no auto REST API, no client-side Supabase queries.
- All business logic, auth and RBAC live in FastAPI.
- No Celery/Redis, no native app, no PostGIS, no pgvector in the MVP.

### Deferred (do not add unless asked)
PostGIS · Leaflet maps · pgvector/RAG · OCR · Celery/Redis · native mobile app

## Roles

`SUPER_ADMIN > STATE_ADMIN > DISTRICT_ADMIN > LM_OFFICER > GATC > BUSINESS > PUBLIC`

- **Business:** instruments, applications, documents, status, certificates
- **LM Officer:** review, inspect, checklist, evidence, approve/reject
- **GATC:** assigned verifications (minimal in MVP)
- **Admin:** stats, users, audit logs
- **Public:** QR verification only

**Org isolation is absolute:** a business never sees another business's data.

## MVP build order

1. Login + RBAC ✅ (spec `docs/specs/01-login-rbac.md`)
2. Instrument registration ✅ (spec `docs/specs/02-instruments.md`)
3. Application + document upload ✅ (spec `docs/specs/03-applications.md`)
4. Business dashboard ✅ (spec `docs/specs/04-business-dashboard.md`)
5. Officer dashboard ✅ (spec `docs/specs/05-officer-dashboard.md`)
6. Inspection checklist + measurements ✅ (spec `docs/specs/06-inspection-checklist.md`)
7. Approve/reject workflow ✅ (spec `docs/specs/07-approve-reject.md`)
8. Certificate PDF + QR ✅ (spec `docs/specs/08-certificate-pdf-qr.md`)
9. Public QR verify page ✅ (spec `docs/specs/09-public-verify.md`)
10. Expiry dashboard + daily job ✅ (spec `docs/specs/10-expiry-job.md`)

Finish the full flow end to end before any Good-to-Have (email polish, GPS, charts, GATC, OCR).

## Demo story (seed data must support it)

ABC Traders registers a weighing scale (Serial `XYZ12345`, 500 kg, Dhanbad) → applies with documents →
the officer inspects and approves → `CERT-2026-000123` with QR is issued → a consumer scans it and sees ✓ VALID → expiry is tracked.

## Instructions for Claude

- **Challenge weak reasoning.** If a request conflicts with these rules (security, RBAC, status flow, stack), say so before coding.
- Pick the simplest thing that works for the MVP. Flag production shortcuts.
- Never add a deferred technology or a new service without asking.
- Never invent legal or regulatory facts. Mark unknowns as `ASSUMPTION`.
- Never commit or edit `.env*` files without asking.
- **Claude applies migrations and runs the demo seed on Supabase itself**, once local tests pass (workflow in `backend/CLAUDE.md` → Migrations). Never edit an already-applied migration (write a new one), and ask before changing *what* the seed data contains.
- When the schema, API or status flow changes, update the relevant CLAUDE.md.
- Style: terse, decision-flagging, copy-pasteable code.

## Git

- Branches: `feat/…`, `fix/…`, `chore/…`. Conventional commits (`feat: add QR verify endpoint`).
- Small PRs. Never commit `.env`, uploads, or generated PDFs.

## Open decisions

- [x] Payments: **resolved (step 12, `docs/specs/12-payments.md`).** A `payments` table
  plus a `POST /api/applications/{id}/mock-pay` action (BUSINESS only) exist so the concept is
  visible in the product, but — an explicit user decision, not an oversight — payment status is
  **purely informational**: no application status transition in
  `backend/app/services/applications.py: ALLOWED_TRANSITIONS`/`transition()` reads or gates on it
  in any way. An application can reach `CERTIFICATE_ISSUED` with no `payments` row ever created
  (proven by `backend/tests/test_payments.py::test_payment_never_gates_the_lifecycle`). See
  `backend/CLAUDE.md`'s "Payments — mocked, informational only" subsection for the full
  implementation.
- [x] GATC workflow depth: **resolved (step 15, `docs/specs/15-gatc-eligibility.md`) as "minimal
  but real."** A `GATC`-role user is a genuine, category-gated `assigned_officer_id` on an
  `Inspection` — `organizations.gatc_eligible_category_ids` (which `instrument_categories` a GATC
  org is approved to test) plus a new `GET /api/gatc/eligible` allocation lookup let a scheduling
  `LM_OFFICER` route a `DOCUMENT_REVIEW → SCHEDULED` transition to a specific GATC user instead of
  always self-assigning — gated on the org being category-eligible **and** the application's
  `verification_mode == OFFICE_TEST_CENTRE` (spec 14; an `ON_SITE` application can never go to a
  GATC test centre). Once assigned, that GATC user flows through the **exact same, unmodified**
  inspection/checklist/measurement/approve-reject machinery an `LM_OFFICER` already uses — no
  parallel GATC-specific workflow was built. GATC still never stamps or issues a certificate (that
  stays `LM_OFFICER`-only, unchanged). See `backend/CLAUDE.md`'s "GATC eligibility + allocation"
  subsection for the full implementation, including why this required new per-request router
  dependencies (not just adding `GATC` to existing role-sets) to avoid changing any pre-existing
  RBAC test's expected status code for an unrelated GATC caller.
- [ ] Cron runner: Render Cron vs GitHub Actions
- [ ] Digital signature: hash-based in MVP, government e-sign later
