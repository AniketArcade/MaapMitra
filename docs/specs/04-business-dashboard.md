# Spec 04 — Business dashboard (rev 2)

**Status:** Done. rev 1 implemented (frontend-only); rev 2 hardening pass implemented and verified (§10, §12)
**Build order:** Step 4 of 10
**Depends on:** Spec 03 rev 2 (`GET /applications`, `GET /applications/meta`, `scope_applications`, `Page[T]`, `StatusBadge`, `labelFor`), Spec 02 rev 2 (`GET /instruments`)

## 1. Goal
`/dashboard` is the role-aware landing page. For **BUSINESS** it must answer three questions at a glance, with numbers that are **correct at any volume**:
1. *What do I own?* instruments
2. *Where do my applications stand?* count per status
3. *What needs me now?* unfinished (DRAFT) applications, plus recent activity

Demo story: ABC Traders logs in and sees "1 Draft" and "1 Rejected" chips, a "Needs your attention" panel linking to the draft, and both applications under Recent. A Rejected application is history only: re-verification means a new application (Spec 03 §3).

**Out of scope:** Officer / Admin / GATC dashboards (step 5+; their branches stay placeholders), the Certificates section (placeholder until step 8), charts.

## 2. What rev 1 got wrong (why this pass exists)
| # | Problem in rev 1 | Consequence | Fix in rev 2 |
|---|---|---|---|
| P1 | Status counts and the "Needs attention" list were computed client-side from `GET /applications?page_size=100` | Beyond 100 applications the chips are **silently wrong** and an old DRAFT is never shown | Server-side counts (`GET /applications/stats`), and DRAFTs fetched with their own filtered query (§4) |
| P2 | Total shown as `items.length` | Wrong past 100 | Use `total` from the server |
| P3 | One shared loading/error state; error text had no retry | One failure looked like a whole-page failure; no recovery | Independent sections, each with **Retry** (§6) |
| P4 | Empty-state CTA always pointed to `/instruments` | Wrong for a business that already has instruments | CTA depends on state (§5) |
| P5 | Chips link to `/applications?status=…`, but only the needs-attention link was manually verified | Unverified navigation; the list page may ignore the query | `/applications` must read `status` from the URL (§7, §9) |
| P6 | Chip order was whatever the code produced | Inconsistent | Lifecycle order from `GET /applications/meta` |
| P7 | The shared demo password was written into the spec | Spec 01 says it lives only in the seed README | Removed; reference the seed README |
| P8 | Verification record mixed into the spec, with no coverage of errors, mobile or volume | Can't tell what was actually checked | Contract (this spec) and record (§10) are separate |

## 3. Access
Any logged-in user may call the endpoints below; the data is always scoped by `scope_applications` / `scope_instruments`. The BUSINESS dashboard branch is shown only to `role == BUSINESS`. Nothing new is exposed: counts are derived from rows the caller could already list.

## 4. Backend: one new endpoint

### `GET /api/applications/stats`
| | |
|---|---|
| Allowed | BUSINESS, LM_OFFICER, DISTRICT_ADMIN, STATE_ADMIN, SUPER_ADMIN (GATC → 403, anonymous → 401) |
| Query | none in step 4 (optional `instrument_id` later) |
| Response | `{ "total": int, "by_status": { "<STATUS>": int, ... } }` |

Rules:
- One grouped query over `scope_applications(...)`: `SELECT status, count(*) … GROUP BY status`. **Same scoping as the list**, so counts always equal what the list would return (officials never count DRAFTs; business counts all own).
- `by_status` contains **all 8 statuses**, zeros included, so the client needs no knowledge of the enum. `total` = sum of `by_status`.
- Response is `extra="forbid"`-style typed schema `ApplicationStats`. No caching.
- Register `/applications/stats` **before** `/applications/{id}`.
- No audit row (read-only aggregate).

`GET /applications/meta` must return statuses as an **ordered list** in lifecycle order (`DRAFT … CERTIFICATE_ISSUED`) with labels; the UI uses that order (P6).

The dashboard's other data uses existing endpoints, which are already correct at any volume because they return `total`:
| Need | Call |
|---|---|
| Instrument count | `GET /instruments?page_size=1` → `total` |
| Status chips + total applications | `GET /applications/stats` |
| Needs-attention panel | `GET /applications?status=DRAFT&page_size=5` (items + true `total`) |
| Recent | `GET /applications?page_size=5` |

The four requests run **in parallel** and are rendered independently.

## 5. UI contract (BUSINESS branch of `RoleCard`)
```
┌ Welcome, {name} ({role}) ───────────────────────────────┐
│ Instruments        12  →  /instruments                   │
│ Applications        7  →  /applications                  │
│ [Draft 2] [Submitted 1] [Document review 1] [Rejected 3] │   chips, lifecycle order, count > 0 only
│                                                          │
│ Needs your attention                                     │
│  • APP-2026-000042 · XYZ12345 · Draft → upload & submit  │   up to 5 DRAFTs
│  + 3 more →  /applications?status=DRAFT                  │   shown when total > 5
│                                                          │
│ Recent                                                   │
│  APP-… · LM-JH-DHN-… · [badge] · date                    │   5 newest, any status
│                                                          │
│ Certificates   (placeholder until step 8)                │
└──────────────────────────────────────────────────────────┘
```
- **Counts** come from `total` / `by_status`, never from `items.length`.
- **Chips:** one per status with count > 0, in `meta` order, label via `labelFor`, each linking to `/applications?status=<STATUS>`. Chips wrap on narrow screens; each is a full touch target (≥ 44 px).
- **"Needs your attention" rules** (extendable table):

| Condition | Row text | Link |
|---|---|---|
| Application status = DRAFT | "Upload documents and submit" | `/applications/{id}` |
| *(reserved, step 10)* Certificate expiring ≤ 30 days | "Re-verify before {date}" | certificate page |

  Panel hidden when there is nothing to show. If DRAFT `total` > 5, add "+ N more →" linking to `/applications?status=DRAFT`.
- **Recent rows:** application number, instrument UID, `StatusBadge` (text label, never colour alone), created date; whole row links to `/applications/{id}`.
- **Empty states** (each section decides for itself):
  | Situation | Message | CTA |
  |---|---|---|
  | 0 instruments | "Register your first instrument to get started" | `/instruments/new` |
  | ≥1 instrument, 0 applications | "Start a verification application" | `/applications/new` |
  | 0 DRAFTs | panel hidden | — |
- Officer / Admin / GATC branches: unchanged.

## 6. States and freshness
Every section (instrument tile, chips, needs-attention, recent) has its **own** state; a failure in one never blanks another:

| State | Behaviour |
|---|---|
| Loading | Skeleton or "Loading…" text of fixed height (no layout shift) |
| Error | "Couldn't load {section}." + **Retry** button that refetches only that section |
| Empty | per §5 |
| Success | per §5 |

- **Freshness:** fetch on mount and again when the tab regains focus (`visibilitychange`). No polling.
- A `401` follows the global refresh-then-login rule in `lib/api.ts`; the dashboard adds no handling of its own.
- A `403` shows the standard "You don't have access" state.

## 7. Frontend implementation
Files: `app/dashboard/page.tsx` (BUSINESS branch), `lib/api.ts` (+ `getApplicationStats()`), `lib/types.ts` (+ `ApplicationStats`), **`app/applications/page.tsx`** (read `status` from the URL).

- Replace `useApplicationsSummary()` (single 100-item fetch) with small independent hooks, e.g. `useApplicationStats()`, `useApplications({status?, pageSize})`, `useInstrumentCount()`, each returning `{ state: "loading"|"error"|"ready", data, retry }`.
- Delete the client-side counting/grouping code.
- `/applications` must initialise its status filter from `?status=` and keep the URL in sync when the filter changes (so chip links, back button and shared links work). An unknown status value is ignored (no filter), not an error.
- Types and labels come from `GET /applications/meta`; nothing hard-coded.

## 8. Tests

### Backend (`pytest`) — `GET /applications/stats`
- **Org isolation:** business A's stats exclude B's applications (B has applications in every status).
- **Officials:** DHN officer's counts exclude DRAFTs and other districts; state admin counts their state; SUPER_ADMIN counts all non-DRAFT.
- **Consistency:** for each role, `by_status[s]` equals `GET /applications?status=s` `total`, and `total` equals the sum.
- **Shape:** all 8 statuses present with zeros; no unknown keys.
- **RBAC:** GATC → 403; anonymous → 401; parametrized over the 6 roles.
- **Route order:** `/applications/stats` isn't captured as an `{id}` (no 422/404).
- **Volume:** with > 100 applications for one org, counts and `total` are still exact.

### Frontend
Check whether the project has a test runner. If **yes**, add component tests (Testing Library) for: chips ordering and zero-hiding, `total` > items case ("+ N more"), each empty-state variant, per-section error + Retry, and the `?status=` filter round trip. If **no**, do not add a runner just for this step: run the manual script in §9 and record the result in §10.

## 9. Acceptance criteria and manual script
Use the seeded demo accounts (passwords: see `database/seed/README.md`).

- [x] `GET /api/applications/stats` implemented and its backend tests pass; `ruff` clean.
- [x] Dashboard counts and chips match the `/applications` list totals for `owner@abctraders.demo` and `owner@othertraders.demo`.
- [x] Create > 5 DRAFT applications for one org (test data): panel shows 5 rows and "+ N more", and N is right. Then confirm counts stay right with > 100 applications (script or test DB).
- [x] Clicking each chip lands on `/applications` **with that status filter applied**; browser Back returns to the dashboard.
- [x] Empty states: an org with 0 instruments shows the register CTA; an org with instruments but 0 applications shows the start-application CTA.
- [x] Error state: stop the backend (or block one request in DevTools) → only the affected section shows an error with a working **Retry**; the rest still renders.
- [x] Return from `/applications/{id}` after submitting a draft: the dashboard reflects the new status without a manual reload. *(Verified architecturally, not by an actual submit — see §12; a real submit against the demo account would permanently consume ABC Traders' only DRAFT.)*
- [x] Mobile width (~375 px): chips wrap, no horizontal scroll, tap targets ≥ 44 px.
- [x] `tsc --noEmit` and `eslint` clean.
- [x] `backend/CLAUDE.md` updated (`/applications/stats`, ordered statuses in `/applications/meta`); `frontend/CLAUDE.md` updated with the rule: **never aggregate paged data on the client; use a server endpoint or `total`.**
- [x] Root `CLAUDE.md` build order still shows step 4 ✅ and links to this spec.

## 10. Verification record (rev 1, kept for history)
Done in Chrome against `localhost:3000` / `localhost:8000` with the seeded demo accounts:
- `owner@othertraders.demo`: 1 seeded application, one status chip, one Recent row with the right badge.
- `owner@abctraders.demo`: 3 instruments, 2 applications (1 DRAFT, 1 REJECTED); both chips, the needs-attention link opened the right detail page.
- `tsc --noEmit` and `npm run lint` clean.

**Not covered by rev 1:** chip navigation, error and retry behaviour, more than 5 drafts, more than 100 applications, mobile width, refresh-after-return. Rev 2 (§9) covers all of these.

## 11. Decisions (resolved)
| # | Decision | Resolution |
|---|---|---|
| D1 | Keep client-side aggregation from one 100-item fetch, or add a server endpoint? | **Add `GET /applications/stats`.** The shortcut shows wrong numbers with no warning past 100, and the endpoint is ~20 lines reusing `scope_applications`. Step 5's officer dashboard reuses it. *(If you decline: minimum mitigation is to use `total` and show "Showing latest 100" whenever `total` > items.)* |
| D2 | Needs-attention scope | **DRAFT only** for now; the rules table (§5) is where later steps add rows |
| D3 | Refresh policy | **Fetch on mount + on tab focus**; no polling |
| D4 | Chip order | **Lifecycle order from `/applications/meta`** |
| D5 | Dashboard test strategy | **Backend tests for the endpoint; frontend manual script** unless a runner already exists |
| D6 | Redesign into KPI tiles or charts | **No.** Keep the chips; charts belong to the admin analytics step |

## 12. Verification record (rev 2)

Backend (`pytest`, local `lm_test`):
- `tests/test_applications_stats.py` (new): shape (8 statuses, zero-filled), org isolation, officials
  scoped and excluding DRAFT, per-status consistency with `GET /applications?status=`, RBAC (GATC 403,
  anonymous 401, all 6 roles), route order (`/stats` not swallowed by `/{id}`), and a 105-application
  volume case — `total` and `by_status` stay exact past one page (the rev-1 regression this endpoint
  exists to fix).
- `tests/test_applications_rbac.py::test_meta` tightened to assert the full 8-status lifecycle order,
  not just that `DRAFT` is first.
- Full suite: 296 passed, `ruff check` and `ruff format --check` clean.

Frontend (`tsc --noEmit`, `eslint`): clean. `lib/use-async.ts` needed a derived-state design (comparing
a request generation `nonce` against the last-resolved one) rather than an explicit `setStatus("loading")`
call in the effect body — this repo's `react-hooks/set-state-in-effect` and `react-hooks/refs` lint rules
(React Compiler-era) reject the "obvious" version of that hook.

Manual, in Chrome against the running dev servers, as `owner@abctraders.demo` (3 instruments, 2
applications: 1 DRAFT, 1 REJECTED — real data already present, not freshly seeded):
- Chips now come from `GET /applications/stats`, not client aggregation; counts matched.
- **Error + Retry, isolated per section:** patched `window.fetch` to reject only
  `/applications/stats` and forced a refetch (dispatching `visibilitychange` with
  `document.visibilityState` overridden to `"visible"`, since an automated tab reports `"hidden"`).
  Only the applications-summary section showed "Couldn't load applications." + Retry; Instruments,
  Needs-your-attention and Recent were unaffected. Unpatching and clicking Retry recovered it.
- **Chip navigation + Back:** the "Draft" chip → `/applications?status=DRAFT` with the filter applied
  in both the list and the Status dropdown; changing the dropdown to "Rejected" → URL updated to
  `?status=REJECTED` via `router.replace`; browser Back → straight to `/dashboard` (replace, not push,
  means Back skips the intermediate filter state and lands where the user actually came from).
- **Unknown status ignored:** navigated to `/applications?status=BOGUS` — UI showed "All statuses" and
  both applications, and the network log confirmed no `status` param was ever sent to the backend (no
  422). Confirmed via `read_network_requests`.
- **"+ N more":** mocked the DRAFT-list response (5 items, `total: 8`) — panel showed 5 rows and
  "+ 3 more" linking to `/applications?status=DRAFT`.
- **Empty states:** mocked 0 instruments / 0 applications → "Register your first instrument to get
  started"; mocked 3 instruments / 0 applications → "Start a verification application". Both CTAs and
  links correct.
- **Mobile width:** true browser-window resize didn't propagate to the tab's CSS viewport in this
  automation environment (`window.innerWidth` stayed at the desktop size regardless of
  `resize_window`), so width was instead constrained directly on the shell's `<main>` element — a valid
  substitute here since the chip/recent layout has no viewport media query, only unconditional
  `flex-wrap`, so container width alone determines wrapping. At 358px (≈390px viewport minus gutters):
  no horizontal scroll, chip tap targets measured 44×44px via `getBoundingClientRect()`, `flex-wrap`
  confirmed `"wrap"` via `getComputedStyle`.
- **Post-submit refresh:** not exercised with a real submit (would have permanently consumed ABC
  Traders' one demo DRAFT). Covered instead by the architecture: `/applications/{id}` and `/dashboard`
  are different routes, so navigating back to the dashboard always mounts a fresh `DashboardPage` and
  `useAsync`'s mount-effect refetches everything — the same mechanism verified working in every other
  case above.
- 100+ application volume was **not** re-driven through the browser (would mean creating 100+ real rows
  against whatever database the running dev server points at); the equivalent case is covered
  deterministically by the backend's `test_volume_past_one_page`, which is the more reliable check for
  this specifically.