# Mobile — Expo (React Native)

Project-wide rules are in `../CLAUDE.md`. **Status: planned, not scaffolded yet.** This file is the
contract for when it is. It serves four audiences only: the Public (anonymous QR verification), Merchants (`BUSINESS`),
LM Officers (`LM_OFFICER`) and GATC test centres (`GATC`), against the same FastAPI backend as the web app.
**Admin roles (DISTRICT/STATE/SUPER_ADMIN) are web-only**: if one logs in, sign out and say "Admin accounts are available on the website".

## Stack

Expo SDK + TypeScript (strict) + expo-router. `expo-secure-store` (tokens), `expo-camera` (QR scan +
inspection photos), `expo-image-picker` / `expo-image-manipulator` (compress), `expo-file-system` +
`expo-sharing` (certificate PDF via signed URL). EAS Build for releases.

## Commands (once scaffolded)

```bash
cd mobile && npm install
npx expo start               # Expo Go / simulator
npx expo lint && npx tsc --noEmit
eas build --profile preview
```

## Environment

`EXPO_PUBLIC_API_ORIGIN=http://<lan-ip>:8000` locally, the Render URL in production. It is public by
nature: **no secrets in the app bundle**, no Supabase keys, no direct Supabase calls.

## Rules (same as the web app unless noted)

- One typed API client (`lib/api.ts`), base URL = `EXPO_PUBLIC_API_ORIGIN`, always sends `X-Client: mobile`. No scattered `fetch`.
- **Auth:** access token in memory; refresh token in `expo-secure-store` (returned in the JSON body for `X-Client: mobile`). Single-flight refresh; on 401 refresh once and retry, else go to login. Never log tokens, never put them in URLs or deep links.
- Types come from the backend OpenAPI schema (generated), not hand-copied.
- **Never hard-code** statuses, types, units, regions, checklist items — load `/instruments/meta`, `/applications/meta`, `/inspections/meta`. Never re-derive `locked_fields`; action buttons come from `allowed_actions`; never aggregate paged data (use stats endpoints/`total`).
- Role navigation mirrors `frontend/components/app-shell.tsx` (`NAV` for Merchant, `OFFICER_NAV`, `GATC_NAV`; no admin navs); it is UX only, the backend enforces. Handle 403/404 explicitly.
- Every screen handles loading, empty, error and success. Scheduling "today" uses the backend timezone from `ApplicationMeta.scheduling`.
- **Uploads:** compress/resize photos below the server's 10 MiB limit before `POST /documents` (PDF/JPG/PNG only). Inspection photos use `document_type: "INSPECTION_EVIDENCE"`.
- Documents/certificates open through short-lived signed URLs from the API (`/documents/{id}/url`, `/certificates/{id}/pdf`); never cache or store the URL.
- Public QR verify needs no login and shows only what `/public/verify/{certificate_number}` returns; the QR encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`, so parse the trailing number.
- Inspection flow is one step per screen with a sticky action button; PATCH each step before advancing; confirm before the irreversible Submit.
- Deferred until asked: push notifications, offline queue, biometric lock.
