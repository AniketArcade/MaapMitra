# Frontend — Next.js

Project-wide rules are in `../CLAUDE.md`. This file covers the frontend only.

## Commands

> ⚠️ Assumed defaults. Update if the setup differs.

```bash
npm install
npm run dev          # http://localhost:3000
npm run lint
npm run build
npx shadcn@latest add <component>
```

## Environment (`.env.local`, optional locally)

```env
API_ORIGIN=http://localhost:8000     # server-side; where the /api/* rewrite proxies to
```

- The browser always calls **same-origin `/api/*`**. `next.config.ts` rewrites it to `API_ORIGIN`, so the refresh cookie is first-party (Vercel and Render are different sites).
- `API_ORIGIN` defaults to `http://localhost:8000` and **must** be set on Vercel (the build fails otherwise).
- No secrets, no Supabase keys, no DB URLs. Avoid `NEXT_PUBLIC_` variables; they're visible to every user.

## Structure

```text
frontend/
├── app/
│   ├── (auth)/login/  (auth)/register/
│   ├── dashboard/             # role-aware landing
│   ├── instruments/           # list, new, [id]
│   ├── applications/          # list, new, [id]
│   ├── inspections/           # officer: list, [id] (field flow)
│   ├── certificates/          # list, [id]
│   ├── admin/                 # stats, users, audit
│   └── verify/[certificateNumber]/   # PUBLIC, no auth
├── components/
│   ├── ui/                    # shadcn (generated, don't hand-edit)
│   └── ...                    # feature components
├── proxy.ts                   # Next 16 name for middleware.ts: coarse route guard
├── lib/
│   ├── api.ts                 # single typed API client
│   ├── auth.ts                # token handling, current user
│   └── types.ts               # shared types mirroring backend schemas
└── public/
```

## Rules

- **All data comes from the FastAPI backend through `lib/api.ts`.** No direct Supabase or DB calls, and no `fetch` scattered in components.
- TypeScript strict. No `any` without a comment explaining why.
- Server components by default. Use `"use client"` only for state, effects or event handlers.
- Use shadcn/ui primitives first, and add custom components only when needed.
- Tailwind only. No separate CSS files except `globals.css`.
- Role checks in the UI are **for UX only**. The backend enforces permissions.

## Auth

- Access token held in memory only (`lib/api.ts`). The backend keeps the refresh token in the httpOnly `lm_refresh` cookie. **Never put tokens in URLs.**
- `/auth/refresh` goes through a **module-level single-flight** promise (`refreshSession()` in `lib/api.ts`). Never call it from a component ref: StrictMode and concurrent 401s would race.
- On a 401, await the shared refresh and retry once; if that fails, redirect to `/login`. If `/auth/refresh` itself returns 401 (lost race), retry it once.
- On page load, `AuthProvider` calls `refreshSession()` to restore the session.
- **Next.js 16 renamed `middleware.ts` to `proxy.ts`.** `proxy.ts` redirects to `/login` when the `lm_session` flag cookie is missing. Role gating happens in layouts (UX only). `/`, `/login`, `/register` and `/verify/*` stay public.
- Post-login redirects use `safeNextPath()` (relative paths only, no open redirects).

## Key screens

| Route | Who | Notes |
|---|---|---|
| `/dashboard` | all logged in | Role-aware cards and counts |
| `/instruments/new` | Business | Form with serial, type, capacity, location |
| `/applications/new` | Business | Pick instrument → type → upload docs → submit |
| `/applications/[id]` | Business, Officer | Status timeline + documents |
| `/inspections/[id]` | Officer | **Mobile-first** field flow (below) |
| `/certificates/[id]` | Business | Download PDF, show QR |
| `/admin` | Admin | Counts, expiring soon, audit log |
| `/verify/[certificateNumber]` | Public | Big status badge: ✓ VALID / ⚠ EXPIRED / ✕ REVOKED |

## Officer field inspection (mobile-first)

Flow: Instrument details → Checklist → Measurements → Photos → Remarks → Approve/Reject → Submit

- Design it for a phone held in one hand: large tap targets, one step per screen, sticky bottom action button.
- Photo upload uses `<input type="file" accept="image/*" capture="environment">`.
- Confirm before Approve/Reject, since it's irreversible.
- Keep draft progress in component state so a slow network doesn't lose input.

## Public verify page

- No login and no navigation to private areas.
- Show only what the public API returns.
- Handle the not-found state clearly ("Certificate not found").
- It must load fast on mobile data, since people reach it by QR scan.

## UI states

Every data view handles **loading, empty, error and success**. Show an explicit message for a 403, not a blank page.
