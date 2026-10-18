# MaapMitra — Legal Metrology Verification & Digital Certification Platform

Portfolio/CV flagship. A digital lifecycle for Legal Metrology instrument verification, on web **and**
a native mobile app, for every role:

```
Register instrument → Apply → Document review → Schedule → Field inspection
→ Approve/Reject → Certificate + QR → Public QR verification → Expiry → Re-verification
```

Physical verification stays a field activity. We digitize the workflow around it.

## Monorepo layout

```text
/
├── CLAUDE.md          ← you are here (project-wide rules)
├── frontend/          ← Next.js web app        → frontend/CLAUDE.md
├── backend/           ← FastAPI service        → backend/CLAUDE.md
├── mobile/            ← Expo React Native app (planned) → mobile/CLAUDE.md
├── database/seed/     ← demo seed data + accounts (README.md)
├── docs/specs/        ← one spec per feature (01–21): decisions, scope, out-of-scope lists
└── .github/workflows/ ← daily expiry-check cron
```

Work inside the relevant folder. Each folder's CLAUDE.md holds its own conventions and commands.

## Stack (decided)

| Layer | Choice | Host |
|---|---|---|
| Web | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | Vercel |
| Mobile | Expo (React Native) + TypeScript + expo-router, EAS Build | Expo / stores |
| Backend | FastAPI + Pydantic + SQLAlchemy + Alembic | Render |
| Database | Supabase Postgres | Supabase |
| Files | Supabase Storage (private bucket, signed URLs) | Supabase |
| Auth | Own JWT + RBAC in FastAPI | — |
| Email | Resend | — |
| Expiry job | Daily GitHub Actions cron → protected endpoint | GitHub |

### Architecture rules
- Web and mobile → FastAPI → Supabase. **No client ever touches the database or Supabase directly.**
- Supabase is Postgres + Storage **only**. No Supabase Auth, no auto REST API, no client-side Supabase queries.
- All business logic, auth and RBAC live in FastAPI; client role checks are UX only.
- The FastAPI OpenAPI schema (`/openapi.json`) is the single API contract for web and mobile.
- No Celery/Redis, no PostGIS, no pgvector.

### Deferred (do not add unless asked)
PostGIS · Leaflet maps · pgvector/RAG · OCR · Celery/Redis · push notifications (needs a new table + Expo push, ask first)

## Roles

`SUPER_ADMIN > STATE_ADMIN > DISTRICT_ADMIN > LM_OFFICER > GATC > BUSINESS > PUBLIC`

- **Business:** instruments, applications, documents, status, certificates
- **LM Officer:** review, schedule/route, inspect, checklist, evidence, approve/reject, issue certificate
- **GATC:** only inspections an LM Officer routed to them; same inspection/approve machinery; never issues
- **Admins:** stats, users, audit logs, jurisdiction-scoped (state / district)
- **Public:** QR verification only

**Org isolation is absolute:** a business never sees another business's data.

## Status

Build steps 1–21 are done (login/RBAC → instruments → applications → dashboards → inspection →
approve/reject → certificate+QR → public verify → expiry job → document review → payments (mocked) →
superseding → transportability → GATC → categories → Super/State/LMO/GATC/District admin frontends).
Details: `docs/specs/NN-*.md`.

**Done:** backend mobile auth (`X-Client: mobile` → refresh token in body, no cookies).
**Next:** shared API types from OpenAPI → Expo app (auth + shell → public QR verify →
Business → Officer/GATC field inspection → admin dashboards) → password reset + account deletion.

## Demo story (seed data must support it)

ABC Traders registers a weighing scale (Serial `XYZ12345`, 500 kg, Dhanbad) → applies with documents →
the officer inspects and approves → `LM-CERT-2026-000123` with QR is issued → a consumer scans it and
sees ✓ VALID → expiry is tracked.

## Instructions for Claude

- **Challenge weak reasoning.** If a request conflicts with these rules (security, RBAC, status flow, stack), say so before coding.
- Pick the simplest thing that works. Flag production shortcuts.
- Never add a deferred technology or a new service without asking.
- Never invent legal or regulatory facts. Mark unknowns as `ASSUMPTION`.
- Never commit or edit `.env*` files without asking.
- **Claude applies migrations and runs the demo seed on Supabase itself**, once local tests pass (workflow in `backend/CLAUDE.md` → Migrations). Never edit an already-applied migration; ask before changing *what* the seed data contains.
- When the schema, API or status flow changes, update the relevant CLAUDE.md. Keep CLAUDE.md files to rules, commands, architecture and gotchas; put feature history and decisions in `docs/specs/`.
- Style: terse, decision-flagging, copy-pasteable code.

## Git

- Branches: `feat/…`, `fix/…`, `chore/…`. Conventional commits (`feat: add QR verify endpoint`).
- Small PRs. Never commit `.env`, uploads, or generated PDFs.

## Open decisions

- [x] Payments: mocked and **informational only** by explicit decision (spec 12). No status transition reads or gates on it.
- [x] GATC depth: "minimal but real" (spec 15/20) — category-gated routing from an LM Officer, then the unmodified inspection machinery.
- [x] Cron runner: GitHub Actions (`.github/workflows/expiry-check.yml`, 03:00 IST).
- [ ] Digital signature: hash-based today (`certificates.data_hash`); government e-sign later.
- [ ] Mobile extras: password reset, account deletion (store requirement), min-app-version gate, push notifications, offline inspection drafts — design each with the user before building.
- [ ] Instrument category content (migration `0012`, 33 rows) has never been content-reviewed.
