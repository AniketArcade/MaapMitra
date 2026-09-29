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

## Environment (`.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- **Only `NEXT_PUBLIC_API_URL` belongs here.** No secrets, no Supabase keys, no DB URLs.
- Anything prefixed `NEXT_PUBLIC_` is visible to every user.

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

- Access token held in memory. Refresh token in an httpOnly cookie if the backend sets one, otherwise follow the backend's contract. **Never put tokens in URLs.**
- On a 401, try one refresh, then redirect to `/login`.
- Route protection by role in `middleware.ts` or a layout guard. `/verify/*` stays public.

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
