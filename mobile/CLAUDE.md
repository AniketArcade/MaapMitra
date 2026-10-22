# Mobile — Expo (React Native)

Project-wide rules are in `../CLAUDE.md`. **Status: auth + role shell done** (login/register, persisted session, Merchant/Officer/GATC tabs with placeholder screens). Public QR verify (5), Merchant (6) and Officer/GATC (7) flows done; Phase 8 (officer expiry view) done; remaining: store-readiness (`../appguide.md` Phases 9-10). It serves four audiences only: the Public (anonymous QR verification), Merchants (`BUSINESS`),
LM Officers (`LM_OFFICER`) and GATC test centres (`GATC`), against the same FastAPI backend as the web app.
**Admin roles (DISTRICT/STATE/SUPER_ADMIN) are web-only**: if one logs in, sign out and say "Admin accounts are available on the website".

## Stack

Expo SDK + TypeScript (strict) + expo-router. `expo-secure-store` (tokens), `expo-camera` (QR scan +
inspection photos), `expo-image-picker` / `expo-image-manipulator` (compress), `expo-file-system` +
`expo-sharing` (certificate PDF via signed URL). EAS Build for releases.

## Commands

```bash
cd mobile && npm install
npx expo start               # Expo Go / simulator
npx expo lint && npm run typecheck
eas build --profile preview
```

## Layout

```text
src/lib/        certificates (open/share PDF via signed URL), use-async (fetch + refetch on focus), use-paged-list (server paging + filters), upload (pick/compress/upload), nav (openInTab), qr (parse scanned URL/number), verify (public verify call + date format), config, storage (secure-store), api (single client), auth (AuthProvider), meta (cached /meta), nav, theme
src/components/ expiry-dashboard (officer), inspection-screen (field flow, root route `/inspection/[id]`), schedule-dialog, application-list/application-screen/application-row (shared by roles), officer-dashboard, instrument-list/instrument-detail (`canManage` for Business only), certificate-list/certificate-view (shared by all roles), instrument-form, section (dashboard card), verify-result (status badge card), ui (Screen/Button/TextField/Select/Loading/ErrorState/Empty), profile, placeholder, tab-icon
src/app/        _layout (AuthProvider + Stack.Protected by role), (auth)/ index=login + register, verify (public),
                (merchant)/ (officer)/ (gatc)/ tab layouts; officer extras live in the nested stack (officer)/more/
```

Routing gotchas: groups share URL space, so a path like `/instruments` is ambiguous between roles; give role-only screens unique paths (e.g. `/more/instruments`). The signed-out `/` must exist (`(auth)/index` is the login screen).

`src/app/` expo-router routes, `@/*` -> `src/*`, `@api-types` -> `../packages/api-types` (types only; `metro.config.js` watches that folder). Web (`w` in `expo start`) is a browser preview for layout only; camera, secure-store and sharing need a device.

## Environment

Copy `.env.example` to `.env` (gitignored). A phone can't reach `localhost`; run the backend with `--host 0.0.0.0`. **Android emulator: `EXPO_PUBLIC_API_ORIGIN=http://10.0.2.2:8000`** (iOS simulator: `http://localhost:8000`; real phone: the Mac's LAN IP).

Local test backend (demo accounts exist only locally; production has admin accounts only):
```bash
cd backend && source .venv/bin/activate
DATABASE_URL=postgresql+psycopg://localhost/lm_dev STORAGE_BACKEND=memory ENV=development uvicorn app.main:app --host 0.0.0.0
```
Accounts (password `LmDemo@2026`): `owner@abctraders.demo` (Merchant), `officer.dhn@lm.demo`, `gatc.dhn@lm.demo`, `state.jh@lm.demo` (admin -> blocked in the app).

`EXPO_PUBLIC_API_ORIGIN=http://<lan-ip>:8000` locally, the Render URL in production. It is public by
nature: **no secrets in the app bundle**, no Supabase keys, no direct Supabase calls.

## Rules (same as the web app unless noted)

- One typed API client (`lib/api.ts`), base URL = `EXPO_PUBLIC_API_ORIGIN`, always sends `X-Client: mobile`. No scattered `fetch`.
- **Auth:** access token in memory; refresh token in `expo-secure-store` (returned in the JSON body for `X-Client: mobile`). Single-flight refresh; on 401 refresh once and retry, else go to login. Never log tokens, never put them in URLs or deep links.
- Types come from `../packages/api-types` (generated from the backend OpenAPI schema; regenerate with `npm run gen` there), not hand-copied.
- **Never hard-code** statuses, types, units, regions, checklist items — load `/instruments/meta`, `/applications/meta`, `/inspections/meta`. Never re-derive `locked_fields`; action buttons come from `allowed_actions`; never aggregate paged data (use stats endpoints/`total`).
- Issue certificate is officer-only and gated on `status === "APPROVED"` (the one exception to `allowed_actions`); GATC never schedules, reviews or issues.
- Role navigation mirrors `frontend/components/app-shell.tsx` (`NAV` for Merchant, `OFFICER_NAV`, `GATC_NAV`; no admin navs); it is UX only, the backend enforces. Handle 403/404 explicitly.
- Instrument categories (spec 16, optional) are not in the app: create sends flat fields only, edit never touches `category_id`/`category_values` (edit on the website).
- Every screen handles loading, empty, error and success. Scheduling "today" uses the backend timezone from `ApplicationMeta.scheduling`.
- **Uploads:** `lib/upload.ts` resizes photos (long edge 2000 px, JPEG 0.7) before `POST /documents` (PDF/JPG/PNG only). Multipart bodies must use `new File(uri)` from `expo-file-system` (a Blob); the old `{uri, name, type}` descriptor fails with "Unsupported FormDataPart". Inspection photos use `document_type: "INSPECTION_EVIDENCE"`.
- **Cross-tab navigation:** push into another tab's stack with `openInTab(href)` (`withAnchor`) and give that stack's `_layout` `unstable_settings = { anchor: "index" }`, otherwise the detail is the only screen and Back has nowhere to go.
- Documents/certificates open through short-lived signed URLs from the API (`/documents/{id}/url`, `/certificates/{id}/pdf`); never cache or store the URL. Certificate PDFs: `Linking.openURL` to view, `File.downloadFileAsync` + `expo-sharing` to share/save. Merchants get a Certificates tab (the API scopes the list to their org) though the web only links certificates from applications.
- Public QR verify needs no login and shows only what `/public/verify/{certificate_number}` returns; the QR encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`, so parse the trailing number.
- Never type into the emulator with `adb input text` unless a text field is focused: unfocused keystrokes act as dev shortcuts (`R R` reloads, `d` opens the dev menu).
- Inspection flow is one step per screen with a sticky action button; PATCH each step before advancing; confirm before the irreversible Submit.
- Deferred until asked: push notifications, offline queue, biometric lock.
