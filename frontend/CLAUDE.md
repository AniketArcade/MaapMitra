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

- Optional `NEXT_PUBLIC_UPLOAD_ORIGIN` (public, non-secret, e.g. the Render URL): if set, `uploadDocument()` posts uploads there directly instead of through the rewrite. It's the fallback if Vercel caps proxied request bodies.
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
│   ├── admin/                 # certificate expiry counts + expiring-soon list (step 10)
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
- **Never aggregate paged data on the client.** Counting or summing `items` from a large `page_size` fetch is wrong once there's more than one page. Use a server endpoint that returns the aggregate (e.g. `GET /applications/stats`) or the `total` field a list endpoint already returns.
- **Never hard-code application statuses, application types or document types either:** use `getApplicationMeta()` (`GET /applications/meta`) and `labelFor()`.
- Status-change buttons come only from `ApplicationDetail.allowed_actions`. Submit is also disabled until every required document is satisfied. **One documented exception:** Issue certificate (step 8) — `APPROVED -> CERTIFICATE_ISSUED` is `Edge(frozenset(), enabled=False)` in the backend (system-only, bypasses `transition()` entirely via `POST /applications/{id}/certificate`), so the button is gated on `app.status === "APPROVED" && isOfficer` instead.
- **Viewing a document:** call `window.open("", "_blank")` synchronously in the click handler, then set its location to the `?disposition=inline` URL; close it on failure (popup blockers). **Downloading:** fetch `?disposition=attachment` and `window.location.assign()` it.
- `lib/api.ts` never sets `Content-Type` for `FormData` bodies.
- **Never hard-code instrument types, units, accuracy classes or regions.** Load them with `getInstrumentMeta()` (`lib/meta.ts`, cached `GET /instruments/meta`). Show names, send codes. The pre-login register form can't call that (auth-gated) — it uses `getPublicRegions()` (cached `GET /public/regions`, no auth) for the same state → district cascading selects instead.
- **Never re-derive which instrument fields are locked.** Disable exactly `Instrument.locked_fields` (from the API); don't recompute the rule client-side from application status.
- **Never hard-code checklist items or measurement points.** Load them with `getInspectionMeta()` (`lib/meta.ts`, cached `GET /inspections/meta`); the actual per-inspection rows (with any answers already given) come from `InspectionDetail`.
- **Scheduling dates:** always compute "today" and the max date in the backend's timezone (`ApplicationMeta.scheduling.timezone`, via `lib/scheduling.ts`'s `todayInTimezone`/`addDaysToIsoDate`), never `new Date()`'s browser-local date. The server still validates independently.
- Pages behind login use `components/app-shell.tsx` in their `layout.tsx` (auth guard + header nav).
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
| `/dashboard` | all logged in | Role-aware cards, each an independent-sections layout via `lib/use-async.ts` (own loading/error+retry/empty per section). Business: instruments, applications total + status chips (`GET /applications/stats`), needs-attention DRAFTs, recent. Officer: instruments, stats, needs-attention (SUBMITTED → start review, DOCUMENT_REVIEW → schedule, INSPECTION → continue inspection), upcoming inspections (`sort=scheduled_asc`), recent |
| `/instruments` | Business, officials | List + search + paging; officials read-only (jurisdiction) |
| `/instruments/new` | Business | Form: type → unit dropdown filtered by type; state → district |
| `/instruments/[id]` | Business, officials | Detail; business gets Edit + Delete (confirm dialog). 404 = "Instrument not found" |
| `/instruments/[id]/edit` | Business | Same form; type is read-only; fields in `locked_fields` disabled; PATCH sends only changed fields |
| `/applications` | Business, officials | List + status filter (URL-driven `?status=`) + search + `sort`; officials never see drafts |
| `/applications/new?instrument_id=` | Business | Instrument without an active application → type → notes → Create draft |
| `/applications/[id]` | Business, officials | Requirements checklist, per-type upload (draft), View/Remove, Submit / Start review / Reject / **Schedule inspection** (dialog, date input) timeline; while SCHEDULED, officer gets **Change date** (no dialog); assigned officer gets **Start inspection** (no dialog, direct transition + navigate) once SCHEDULED, then **Continue inspection** (link to `/inspections/[id]`) while INSPECTION; once the inspection is submitted, any in-scope officer sees the checklist's PASS/FAIL/NA summary and **Approve** / **Reject** (step 7, optional-note / required-note dialogs), and the inspection link relabels to **View inspection**; once `APPROVED`, an officer sees **Issue certificate** (step 8, no dialog); once `CERTIFICATE_ISSUED`, a summary (number, validity) and a **View certificate** link to `/certificates/[id]` |
| `/inspections/[id]` | Officer | **Mobile-first** field flow (below); read-only (`can_edit: false`) for a non-assigned officer or once submitted |
| `/certificates/[id]` | Business, officials, admins | Certificate details, QR (from `qr_code_data_uri`), **View PDF** / **Download** (signed URL, same pattern as documents) |
| `/admin` | `ADMIN_ROLES` (`SUPER_ADMIN`/`STATE_ADMIN`/`DISTRICT_ADMIN`) | Four count cards (valid/expiring soon/expired/revoked, `AdminCertificateStats`) + an expiring-soon table (`GET /admin/certificates/expiring-soon`), jurisdiction-scoped. Linked from the dashboard's admin card. Deliberately just the expiry slice, not a full user-management or audit-log-browsing UI — neither is built anywhere (step 10, spec `docs/specs/10-expiry-job.md` §10 D1). |
| `/verify/[certificateNumber]` | Public | No `AppShell`, own `layout.tsx` (centered card, same shape as `(auth)/layout.tsx`). Big status badge: ✓ VALID (green) / ⚠ EXPIRED (amber) / ✕ REVOKED (red), `instrument_type_label` + manufacturer/model/serial, `valid_from`–`valid_until`. Never links to the PDF or anywhere else in the app (step 9). |

## Officer field inspection (mobile-first)

Flow: Instrument details → Checklist → Measurements → Photos → Remarks → Submit (step 6). Approve/Reject
is not part of this flow — once submitted, it renders directly on `/applications/[id]` (Approve/Reject
buttons plus a checklist summary line, gated on `allowed_actions`, open to any in-scope officer — not
just the one who ran the inspection, step 7 D1).

- Design it for a phone held in one hand: large tap targets, one step per screen, sticky bottom action button.
- Photo upload uses `<input type="file" accept="image/*" capture="environment">`, `document_type: "INSPECTION_EVIDENCE"`.
- Confirm before **Submit**, since it's irreversible (locks the checklist server-side, `can_edit` becomes `false`).
- Checklist/measurement templates come from `GET /inspections/meta` (`getInspectionMeta()`) and the
  per-inspection snapshot in `InspectionDetail` — never hard-coded, same rule as instrument/application meta.
- Each step's Next button PATCHes that step's data before advancing (`patchInspection()`), so a slow
  network doesn't lose input already saved; the page's own component state carries the in-progress edit
  between PATCHes.

## Public verify page

- No login and no navigation to private areas.
- Show only what the public API returns.
- Handle the not-found state clearly ("Certificate not found").
- It must load fast on mobile data, since people reach it by QR scan.

## UI states

Every data view handles **loading, empty, error and success**. Show an explicit message for a 403, not a blank page.
