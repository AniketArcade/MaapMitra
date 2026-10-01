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
- Pages behind login use `components/app-shell.tsx` in their `layout.tsx` (auth guard + header nav). The sidebar nav is role-branched (UX only, backend still enforces everything): `SUPER_ADMIN` gets a fuller flat list (`SUPER_ADMIN_NAV`, step 17), `STATE_ADMIN` gets its own one-rank-down flat list (`STATE_ADMIN_NAV`, step 18, adds a "Districts" link neither other nav has), `LM_OFFICER` gets its own `OFFICER_NAV` (step 19, adds Certificates/Expiring soon links), `GATC` gets its own narrower `GATC_NAV` (step 20, adds a Certificates link but not Instruments — `scope_instruments` has no `GATC` branch — or Expiring soon — not jurisdiction-scoped for this role) rather than sharing the base `NAV` with `BUSINESS` (who has no certificate list page of its own), `DISTRICT_ADMIN` is the only role still falling through to the generic `[...NAV, {Admin link}]` form.
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
| `/dashboard` | all logged in | Role-aware cards, each an independent-sections layout via `lib/use-async.ts` (own loading/error+retry/empty per section). Business: instruments, applications total + status chips (`GET /applications/stats`), needs-attention DRAFTs, recent. Officer: instruments, stats, a "Certificates expiring soon" count (`GET /admin/certificates/stats`, step 19), needs-attention (SUBMITTED → start review, DOCUMENT_REVIEW → schedule, INSPECTION → continue inspection), upcoming inspections (`sort=scheduled_asc`), recent. GATC: stats, needs-attention (SCHEDULED → start verification, INSPECTION → continue inspection — only these two, never SUBMITTED/DOCUMENT_REVIEW), recent (step 20 — replaces the old static stub) |
| `/instruments` | Business, officials | List + search + paging; officials read-only (jurisdiction) |
| `/instruments/new` | Business | Form: type → unit dropdown filtered by type; state → district |
| `/instruments/[id]` | Business, officials | Detail; business gets Edit + Delete (confirm dialog). 404 = "Instrument not found" |
| `/instruments/[id]/edit` | Business | Same form; type is read-only; fields in `locked_fields` disabled; PATCH sends only changed fields |
| `/applications` | Business, officials | List + status filter (URL-driven `?status=`) + search + `sort`; officials never see drafts |
| `/applications/new?instrument_id=` | Business | Instrument without an active application → type → notes → Create draft |
| `/applications/[id]` | Business, officials | Requirements checklist, per-type upload (draft), View/Remove, Submit / Start review / Reject / **Schedule inspection** (dialog, date input) timeline; while SCHEDULED, officer gets **Change date** (no dialog); assigned officer gets **Start inspection** (no dialog, direct transition + navigate) once SCHEDULED, then **Continue inspection** (link to `/inspections/[id]`) while INSPECTION; once the inspection is submitted, any in-scope officer sees the checklist's PASS/FAIL/NA summary and **Approve** / **Reject** (step 7, optional-note / required-note dialogs), and the inspection link relabels to **View inspection**; once `APPROVED`, an officer sees **Issue certificate** (step 8, no dialog); once `CERTIFICATE_ISSUED`, a summary (number, validity) and a **View certificate** link to `/certificates/[id]` |
| `/inspections/[id]` | Officer | **Mobile-first** field flow (below); read-only (`can_edit: false`) for a non-assigned officer or once submitted |
| `/certificates` | `LM_OFFICER`, `GATC` | Certificate directory, role-aware subtitle ("Every certificate in your district." / "Every certificate you've tested."). `GET /api/certificates` already admitted `LM_OFFICER` since step 17 and `GATC` since step 20 — status filter, paginated, links to `/certificates/[id]` (step 19, extended step 20) |
| `/certificates/expiring-soon` | `LM_OFFICER` | Same `ExpiryDashboard` component `ADMIN_ROLES` see at `/admin/certificates/expiring-soon`, reused verbatim at a non-`/admin` path (an officer has no `/admin` page at all) (step 19) |
| `/certificates/[id]` | Business, officials, admins | Certificate details, QR (from `qr_code_data_uri`), **View PDF** / **Download** (signed URL, same pattern as documents) |
| `/admin` | `DISTRICT_ADMIN`: unchanged expiry dashboard (below). `STATE_ADMIN`: state dashboard (step 18). `SUPER_ADMIN`: national dashboard (step 17) | `DISTRICT_ADMIN` gets the original "Expiry dashboard" (four count cards + expiring-soon table, `components/admin/expiry-dashboard.tsx`, jurisdiction-scoped). `STATE_ADMIN` gets `components/admin/state-admin-dashboard.tsx`: the same KPI-card/verification-overview/recent-activity sections as the Super Admin dashboard (already state-scoped server-side), but a district-wise table (`DistrictOverviewTable`, `GET /admin/district-overview`) instead of the national state-wise one. Spec `docs/specs/18-state-admin.md`. `SUPER_ADMIN` gets `components/admin/super-admin-dashboard.tsx`: national KPI cards (instruments, applications, certificate buckets, active LMOs/GATCs), a verification-status chip row, the state-wise table, 5 most recent audit-log rows, quick-action links. Spec `docs/specs/17-super-admin.md`. |
| `/admin/certificates/expiring-soon` | `ADMIN_ROLES` | Same `ExpiryDashboard` component as `/admin`'s `DISTRICT_ADMIN` view, reachable directly from the `SUPER_ADMIN`/`STATE_ADMIN` sidebar's "Expiring soon" link (step 17) |
| `/admin/districts` | `STATE_ADMIN` | `DistrictOverviewTable` as a standalone page — no bespoke district-detail page; "View" affordances live on the district-filterable pages below instead (step 18) |
| `/admin/applications` | `SUPER_ADMIN`, `STATE_ADMIN` | Same table as `/applications`, cloned (not parameterized) — unconditionally unfiltered by jurisdiction for `SUPER_ADMIN` (State/District columns + cascading state→district filters, step 17), state-scoped automatically for `STATE_ADMIN` (District filter only, State column/filter hidden — redundant for a single-state view, step 18) |
| `/admin/certificates` | `SUPER_ADMIN`, `STATE_ADMIN` | The general certificate directory (`GET /api/certificates`, new in step 17 — no list endpoint existed before; already open to `STATE_ADMIN` since that endpoint was never `SUPER_ADMIN`-only); status filter, paginated, links to `/certificates/[id]` |
| `/admin/gatc` | `SUPER_ADMIN`, `STATE_ADMIN` | Read-only GATC org directory (`GET /api/organizations?type=GATC`): name, state/district, eligible categories, pending/completed cases, a nested per-user table with Activate/Deactivate (step 17). State filter hidden for a `STATE_ADMIN` viewer (step 18, UX consistency — `scope_organizations()` already floors results to their own state, so a mismatched filter would just silently return nothing rather than error) |
| `/admin/lmo` | `SUPER_ADMIN`, `STATE_ADMIN` | Read-only LMO directory, one row per officer (`GET /api/users?role=LM_OFFICER`), with pending/completed cases and Activate/Deactivate (step 17). State filter hidden for a `STATE_ADMIN` viewer (step 18) — this one **is** a correctness fix, not just polish: `GET /api/users` rejects (422) a mismatched `state_code` rather than silently returning nothing |
| `/admin/users` | `SUPER_ADMIN`, `STATE_ADMIN` | Official-account directory (`GET /api/users`, officials only — never BUSINESS/GATC) + **Create official account** (dialog, `components/admin/user-create-form.tsx`, same role restriction as `POST /api/users`: `STATE_ADMIN`/`DISTRICT_ADMIN`/`LM_OFFICER` for a `SUPER_ADMIN` creator) + per-row Activate/Deactivate (step 17). For a `STATE_ADMIN` viewer (step 18): State filter hidden, role filter restricted to `{DISTRICT_ADMIN, LM_OFFICER}` (matches `GET /api/users`' own `ROLE_RANK` rejection of a peer-or-above filter), and `UserCreateForm` locks the State select to the creator's own state and drops `STATE_ADMIN` from its role options |
| `/admin/audit-logs` | `SUPER_ADMIN`, `STATE_ADMIN` | `GET /api/audit-logs`, filterable (date range, action, entity type), **View details** opens a `Dialog` with the raw `details` JSON pretty-printed (no collapsible-row primitive exists in this codebase) (step 17). For a `STATE_ADMIN` viewer, the backend's own-state jurisdiction filter applies (step 18) — no frontend change needed here beyond the role gate |
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
