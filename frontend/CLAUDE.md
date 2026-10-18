# Frontend — Next.js

Project-wide rules are in `../CLAUDE.md`. This file covers the web frontend only. The native app
lives in `../mobile/` and shares this app's API contract and rules (see `../mobile/CLAUDE.md`).
Next.js 16: read `node_modules/next/dist/docs/` before using unfamiliar APIs (see `AGENTS.md`).

## Commands

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

- `API_ORIGIN` defaults to localhost and **must** be set on Vercel (the build fails otherwise).
- The browser always calls **same-origin `/api/*`**; `next.config.ts` rewrites it to `API_ORIGIN`, so the refresh cookie is first-party (Vercel and Render are different sites).
- Optional `NEXT_PUBLIC_UPLOAD_ORIGIN` (the Render URL): `uploadDocument()` posts there directly if Vercel caps proxied request bodies.
- No secrets, no Supabase keys, no DB URLs. Avoid `NEXT_PUBLIC_` variables; they're visible to every user.

## Structure

```text
frontend/
├── app/                # (auth)/login|register, official-login, dashboard, instruments, applications,
│                       #   inspections/[id], certificates, admin/*, profile, verify/[certificateNumber] (PUBLIC),
│                       #   how-it-works, support, page.tsx (marketing landing)
├── components/         # ui/ (shadcn, don't hand-edit), admin/, auth/, instruments/, marketing/, verify/, app-shell.tsx
├── lib/                # api.ts (single typed client), auth.ts, meta.ts, scheduling.ts, types.ts, use-async.ts, qr.ts
├── proxy.ts            # Next 16 name for middleware.ts: coarse route guard
└── public/
```

## Rules

- **All data comes from FastAPI through `lib/api.ts`.** No Supabase/DB calls, no `fetch` scattered in components.
- **Never aggregate paged data on the client.** Use a server stats endpoint (`GET /applications/stats`) or the list's `total`.
- **Never hard-code** statuses, application/document types, instrument types, units, accuracy classes, regions, checklist items or measurement points. Load them via `getApplicationMeta()`, `getInstrumentMeta()`, `getInspectionMeta()` (cached, `lib/meta.ts`) and `labelFor()`. The pre-login register form uses `getPublicRegions()` (no auth).
- **Never re-derive locked instrument fields:** disable exactly `Instrument.locked_fields`.
- Status-change buttons come only from `ApplicationDetail.allowed_actions`; Submit is also disabled until required documents are satisfied. **One exception:** Issue certificate (`APPROVED → CERTIFICATE_ISSUED` is system-only in the backend) is gated on `status === "APPROVED" && isOfficer`.
- **Scheduling dates:** compute "today"/max in the backend's timezone (`ApplicationMeta.scheduling.timezone` via `lib/scheduling.ts`), never browser-local `new Date()`.
- **Viewing a document:** `window.open("", "_blank")` synchronously in the click handler, then set its location to the `?disposition=inline` signed URL (close on failure — popup blockers). **Downloading:** fetch `?disposition=attachment` and `window.location.assign()`.
- `lib/api.ts` never sets `Content-Type` for `FormData` bodies.
- Pages behind login use `components/app-shell.tsx` in their `layout.tsx` (auth guard + nav). Nav is role-branched (`NAV`, `OFFICER_NAV`, `GATC_NAV`, `DISTRICT_ADMIN_NAV`, `STATE_ADMIN_NAV`, `SUPER_ADMIN_NAV`) for UX only; the backend enforces everything.
- Role checks in the UI are UX only. TypeScript strict; no `any` without a comment. Server components by default, `"use client"` only for state/effects/handlers. shadcn/ui primitives first; Tailwind only (no CSS files except `globals.css`).
- Every data view handles **loading, empty, error and success**; show an explicit message for 403, not a blank page. Dashboards use independent sections via `lib/use-async.ts`.

## Auth

- Access token in memory only (`lib/api.ts`); the backend keeps the refresh token in the httpOnly `lm_refresh` cookie. **Never put tokens in URLs.**
- `/auth/refresh` goes through a **module-level single-flight** promise (`refreshSession()`); never call it from a component ref (StrictMode and concurrent 401s would race). On 401: await the shared refresh, retry once, else redirect to `/login`. If refresh itself 401s (lost race), retry it once.
- `AuthProvider` calls `refreshSession()` on page load to restore the session.
- `proxy.ts` redirects to `/login` when the `lm_session` flag cookie is missing; `/`, `/login`, `/register`, `/official-login`, `/verify/*`, `/how-it-works`, `/support` stay public. Post-login redirects use `safeNextPath()` (relative only).

## Routes → who (details live in `../docs/specs/`)

| Route | Who |
|---|---|
| `/dashboard` | all logged in; role-aware cards (specs 04/05/20) |
| `/instruments`, `/instruments/new`, `/instruments/[id](/edit)` | Business writes; officials read in jurisdiction (spec 02) |
| `/applications`, `/applications/new`, `/applications/[id]` | Business + officials; all workflow actions on the detail page (specs 03/07/08/11/14/15) |
| `/inspections/[id]` | assigned officer / GATC; read-only otherwise (spec 06) |
| `/certificates`, `/certificates/[id]`, `/certificates/expiring-soon` | list: LM_OFFICER, GATC; detail: business, officials, admins; expiring-soon: LM_OFFICER (specs 08/19/20) |
| `/admin`, `/admin/{applications,certificates,users,lmo,gatc,audit-logs}`, `/admin/certificates/expiring-soon`, `/admin/districts` (STATE_ADMIN only) | SUPER/STATE/DISTRICT admin, each rank sees a narrower dashboard and hides redundant jurisdiction filters (specs 10/17/18/21); only SUPER_ADMIN and STATE_ADMIN get "Create official account" |
| `/verify/[certificateNumber]` | **Public**, no `AppShell`: ✓ VALID / ⚠ EXPIRED / ✕ REVOKED badge + allow-listed fields; never links to the PDF or the app (spec 09). Includes a camera QR scanner (`components/verify/qr-scanner.tsx`) |
| `/profile` | all logged in |

## Officer field inspection (mobile-first)

Flow: Instrument details → Checklist → Measurements → Photos → Remarks → Submit.

- Design for one hand on a phone: large tap targets, one step per screen, sticky bottom action button.
- Photos: `<input type="file" accept="image/*" capture="environment">`, `document_type: "INSPECTION_EVIDENCE"`. Keep photos under the 10 MiB server limit.
- Each Next PATCHes that step (`patchInspection()`) before advancing so a slow network doesn't lose input.
- Confirm before **Submit** (irreversible; locks the checklist, `can_edit` becomes `false`). Approve/Reject happens on `/applications/[id]` afterwards, not in this flow.

## Public verify page

No login, no navigation to private areas, show only what the public API returns, clear "Certificate not found" state, and it must load fast on mobile data (people arrive by QR scan).
