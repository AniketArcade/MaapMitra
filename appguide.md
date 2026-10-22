# MaapMitra — App Guide (what to do next)

Goal: a native Expo (React Native) app for **four audiences only**: the **Public** (anonymous QR
verification), **Merchants** (`BUSINESS` role), **LM Officers** (`LM_OFFICER`) and **GATC test centres**
(`GATC`), on the same FastAPI backend as the website.
**Admins (District / State / Super) are web-only**; no admin screens in the app. The backend still enforces
every permission, so an admin who logs into the app just gets a "use the website" message.
Rules for the app live in `mobile/CLAUDE.md`; project rules in `CLAUDE.md`.

## Where you are

- ✅ Web app + backend, all 21 specs done, 627 backend tests passing.
- ✅ Backend mobile auth: send `X-Client: mobile` → refresh token comes back in the JSON body, no cookies
  (`backend/app/routers/auth.py`, tests in `backend/tests/test_auth_mobile.py`).
- ✅ Phase 0 done: pushed to `main`; work continues on `feat/mobile-app`.
- ✅ Phase 1 done: production login with `X-Client: mobile` returns `refresh_token` in the body, no `Set-Cookie`,
  logout 204. Client-IP decision: accept inexact IPs for the app path in the MVP (see `backend/CLAUDE.md`).
- ✅ Phase 2 done: `packages/api-types` (generated from OpenAPI), `frontend/lib/types.ts` re-exports it.
- ✅ Phase 3 done: `mobile/` scaffolded (Expo SDK 58, strict TS, `@api-types` alias, iOS bundle builds).
- ✅ Phase 4 done: API client, secure session restore, login/register, Merchant/Officer/GATC tab shell, admin block (verified on the Android emulator).
- ✅ Phase 5 done: public QR verify (`app/verify.tsx`): camera scanner + manual entry, VALID/EXPIRED/SUPERSEDED/REVOKED badge, not-found/error states. Manual entry verified on the emulator; a real QR scan still needs a physical phone.
- ✅ Phase 6 done (Merchant):  **6a done**: Merchant dashboard and Instruments. **6b done**: Applications (list with status filter + search, create draft, detail with per-type uploads compressed on-device, view via signed URL, remove, submit/resubmit gated on `allowed_actions`, status history). **6c done**: Certificates tab (status filter), certificate detail with QR, view/share PDF, supersede links, informational mock payment on the application. PDF open/share verified only against a local test PDF server (local storage is in-memory).
- ⬜ Not yet: Phases 7-8, password reset, account deletion, store release.

Each phase below ends with a **Done when** check. Don't start the next phase until it passes.
Work on a branch per phase (`feat/...`) and keep PRs small.

---

## Phase 0 — Commit what exists (10 min)

```bash
git checkout -b feat/mobile-auth
git add backend CLAUDE.md frontend/CLAUDE.md mobile/CLAUDE.md appguide.md
git commit -m "feat: mobile auth transport (X-Client: mobile) and CLAUDE.md overhaul"
git push -u origin feat/mobile-auth   # open a PR, merge to main
```

Leave `docs/PROJECT_OVERVIEW.docx` out unless you want it in the repo.
**Done when:** `main` contains the backend mobile-auth change and the new CLAUDE.md files.

## Phase 1 — Deploy the auth change and measure the proxy hops (30 min)

1. Merge → Render redeploys the backend.
2. Test against production:
   ```bash
   curl -s -X POST https://maapmitra.onrender.com/api/auth/login \
     -H 'Content-Type: application/json' -H 'X-Client: mobile' \
     -d '{"email":"owner@abctraders.demo","password":"<demo password>"}'
   ```
   The response must contain `refresh_token` and no `Set-Cookie` header (`-i` to see headers).
3. **Client IP / rate limits:** the website goes Vercel → Render, the app goes straight to Render, so
   `TRUSTED_PROXY_HOPS` can't be right for both. Measure first: call any endpoint directly, then through the
   Vercel site, and compare the `X-Forwarded-For` the backend sees (log it temporarily, locally or on a
   throwaway deploy; remove the log after).
   Then pick one: (a) accept slightly-off IPs for one path in the MVP and document it in
   `backend/CLAUDE.md`, or (b) have the Next.js rewrite send a marker header and branch in `get_client_ip`.
   Decide with Claude before changing `core/deps.py`; it affects rate limits and audit logs.

**Done when:** mobile login works against the deployed API and the hop-count decision is written down.

## Phase 2 — Shared API types (1–2 h)

Stop hand-copying `frontend/lib/types.ts`; generate from FastAPI's schema.

1. Create `packages/api-types/` (or `shared/`) with a script:
   ```bash
   npx openapi-typescript http://localhost:8000/openapi.json -o packages/api-types/schema.d.ts
   ```
   Add it as an npm script (`npm run gen:types`) and commit the generated file.
2. Migrate `frontend/lib/types.ts` to re-export / alias the generated types incrementally (don't rewrite every
   file in one go; the web app must keep building).
3. Add a CI check later that regenerating produces no diff.

**Done when:** `npm run build` and `npm run lint` pass in `frontend/`, and the same generated types can be
imported from a second folder.

## Phase 3 — Scaffold the Expo app (1–2 h)

```bash
cd /Users/aniket/MaapMitra
npx create-expo-app@latest mobile --template default   # keep mobile/CLAUDE.md (don't overwrite it)
cd mobile
npx expo install expo-secure-store expo-camera expo-image-picker expo-image-manipulator \
  expo-file-system expo-sharing expo-router
```

1. TypeScript strict (`"strict": true` in `tsconfig.json`).
2. `.env`: `EXPO_PUBLIC_API_ORIGIN=http://<your-mac-LAN-ip>:8000` (a phone can't reach `localhost`).
3. Run the backend reachable on your network:
   ```bash
   cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0
   ```
4. `npx expo start`; open in the iOS Simulator (`i`) or Expo Go on your phone.
5. Add `mobile/node_modules`, `.expo/`, and `.env*` to `.gitignore` if the template didn't.

**Done when:** the app boots on the simulator showing a placeholder screen.

## Phase 4 — API client + auth + role shell (1–2 days)

Mirror `frontend/lib/api.ts` and `frontend/lib/auth.ts`:

1. `lib/api.ts`: base URL from `EXPO_PUBLIC_API_ORIGIN`, always send `X-Client: mobile`, `Authorization: Bearer`,
   same ApiError shape (422 → field errors), **single-flight refresh**, retry once on 401, then log out.
2. `lib/auth.tsx`: access token in memory; refresh token in `expo-secure-store`; on app start call
   `POST /auth/refresh` with `{refresh_token}` to restore the session; on logout call `POST /auth/logout`
   with the body, then clear storage. Never log tokens.
3. Screens: login, register (Business self-registration; officials use login only), loading splash.
4. Role shell with expo-router: after login branch on `user.role` to a tab layout (mirror the `NAV`,
   `OFFICER_NAV` and `GATC_NAV` lists in `frontend/components/app-shell.tsx`): **Merchant, LM Officer, GATC**.
   For `SUPER_ADMIN` / `STATE_ADMIN` / `DISTRICT_ADMIN`, sign out and show "Admin accounts are available on
   the website". This is UX only; the backend enforces everything. The Public needs no login: the QR verify
   screen is reachable from the login screen.
5. Load reference data via `/instruments/meta`, `/applications/meta`, `/inspections/meta` (cache in memory).

Test accounts: `database/seed/README.md` (shared demo password, one account per role).

**Done when:** you can log in as the seeded Merchant, Officer and GATC accounts, land on the right tabs, kill and reopen the app and stay
logged in, and a 403/401 shows a clear message.

## Phase 5 — Public QR verify (½ day, great demo moment)

1. Screen with `expo-camera` barcode scanning (QR). The QR encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`:
   take the last path segment, call `GET /public/verify/{certificate_number}` (no auth).
2. Show the big status: ✓ VALID / ⚠ EXPIRED / ✕ REVOKED (or SUPERSEDED), type, manufacturer/model/serial,
   valid from–until. Show "Certificate not found" for 404. Never link to the PDF.
3. Also a manual-entry field for the certificate number. Reachable without logging in (login screen button).

**Done when:** scanning the QR from a web-generated certificate PDF shows VALID in the app.

## Phase 6 — Merchant (Business) flows (3–5 days)

In this order, each a thin screen over an existing endpoint:

1. Dashboard: `GET /applications/stats` (status chips), needs-attention drafts.
2. Instruments: list/search/paging, create/edit form (type → unit filtering, state → district cascading, honor
   `locked_fields`), detail, delete with confirm.
3. Applications: create from an instrument, per-type document upload, view/remove, Submit, resubmit after
   DOCUMENTS_DEFICIENT, status timeline. Buttons only from `allowed_actions`.
4. **Uploads:** compress with `expo-image-manipulator` to well under 10 MiB (resize long edge ~2000 px, JPEG
   ~0.7) before `POST /documents` (multipart; don't set `Content-Type` yourself). PDFs via the document picker.
5. Documents/certificates: fetch the signed URL (`/documents/{id}/url`, `/certificates/{id}/pdf`) and open it
   with `expo-sharing` / the system viewer. Never store the URL.
6. Certificates list + detail with QR (`qr_code_data_uri`) and mock payment button (informational only).

**Done when:** the full demo story works on the phone as ABC Traders: register scale → apply → upload → submit.

## Phase 7 — Officer + GATC field flow (4–6 days, the app's main value)

1. Officer dashboard + application queue (`status`, `sort=scheduled_asc`); document review checklist
   (`PATCH /applications/{id}/review-checklist`), request-corrections / reject with note (≥10 chars), schedule
   (date in the **backend timezone**, optional GATC routing via `/gatc/eligible`).
2. Inspection screen, one step per screen with a sticky bottom button: details → checklist → measurements →
   photos (camera, `INSPECTION_EVIDENCE`, compressed) → remarks → **confirm** → submit. PATCH each step before
   moving on (`PATCH /inspections/{id}`).
3. Approve / Reject on the application, then **Issue certificate** (`POST /applications/{id}/certificate`).
4. GATC: same inspection screens, but only their assigned application(s); no scheduling, no issuing.

**Done when:** officer takes a scheduled inspection from SCHEDULED to CERTIFICATE_ISSUED on the phone, and a
GATC user can complete an assigned inspection.

## Phase 8 — Officer extras: certificates and expiry (1 day)

LM Officer and GATC certificate lists (`GET /certificates`, status filter, detail + PDF), and for LM Officers
the expiring-soon view (`GET /admin/certificates/{stats,expiring-soon}` is open to `LM_OFFICER`, own district
only). No admin dashboards in the app.

**Done when:** an officer can find a certificate they issued and open its PDF.

## Phase 9 — Store-readiness gaps (needs design decisions first)

These don't exist yet; ask Claude to plan each before building (each touches the backend):

1. **Password reset** (forgot password): token table (migration `0014`), email via Resend, two endpoints,
   rate limits, app screens. Required for any real user.
2. **Account deletion**: Apple requires in-app account deletion for apps with sign-up. Decide what happens to
   a Business's instruments/certificates (anonymise vs. block); certificates must stay verifiable.
3. **Minimum app version**: add `min_mobile_version` to `/health`; the app shows "please update" if older.
4. Optional later: push notifications (new table + Expo push; ask first), offline inspection drafts, biometric
   lock. Render free tier cold starts: keep-warm ping or paid instance before demos.

## Phase 10 — Build and ship (1–2 days + store review time)

1. Create an Expo account; `npm i -g eas-cli && eas login && eas build:configure`.
2. Set `EXPO_PUBLIC_API_ORIGIN` to the Render URL in `eas.json` build profiles.
3. `eas build --profile preview --platform android` → installable APK to demo on a real phone.
4. iOS needs an Apple Developer account (paid); Android Play Console is a one-time fee. For a CV, a preview
   APK + screen recording + README GIFs is enough if you skip the stores.
5. App name, icon, splash, bundle id (e.g. `com.<you>.maapmitra`).

## Phase 11 — Make it CV-ready

- README at repo root: problem, architecture diagram (web + mobile → FastAPI → Supabase), role matrix,
  screenshots/GIFs of the demo story (including the QR scan), tech list, how to run, live links.
- Metrics worth stating: 21 specs, 627 backend tests, RBAC with 6 roles + org isolation, signed URLs,
  refresh-token rotation with reuse detection, daily expiry job.
- Keep `docs/specs/` as your design-decision record; link it.
- Record a 2-minute demo: register → apply → inspect → approve → certificate → scan QR → VALID.
- Before sharing publicly: rotate/confirm no secrets in git history, and change the demo password if the
  deployment stays live.

---

## Suggested order of work (≈ 3–4 weeks part-time)

| Week | Phases |
|---|---|
| 1 | 0, 1, 2, 3, 4, 5 |
| 2 | 6 (Business) |
| 3 | 7 (Officer + GATC) |
| 4 | 8, 9 (password reset, deletion), 10, 11 |

## Rules to keep re-reading

- App → FastAPI only. No Supabase keys, no direct DB, no secrets in the bundle (`EXPO_PUBLIC_*` is public).
- Never hard-code statuses/types/units/regions/checklists: use the `/meta` endpoints.
- Buttons from `allowed_actions`; fields disabled from `locked_fields`; never aggregate paged lists on the client.
- Backend enforces every permission; the app's role tabs are only UX.
- Update the matching `CLAUDE.md` whenever the API, schema or status flow changes.
