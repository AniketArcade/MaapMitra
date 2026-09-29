# Spec 03 — Applications and document upload (rev 2)

**Status:** Ready for Claude Code (all decisions resolved, see §14)
**Build order:** Step 3 of 10
**Depends on:** Spec 01 rev 2 (auth, RBAC, audit, `get_client_ip`), Spec 02 rev 2 (instruments, `scope_instruments`, `Page[T]`, `errors.py`, `extra="forbid"`) **plus the amendments in §2**

## 1. Goal
A BUSINESS user picks one of its instruments, creates an **application** (DRAFT), uploads the required documents, and **submits** it (SUBMITTED). An LM_OFFICER in the jurisdiction can open the submitted application, start document review, and view the documents through short-lived signed links. Files live in a **private** Supabase Storage bucket; the database stores only `storage_path`.

Demo story: ABC Traders applies for verification of `XYZ12345`, uploads an invoice and a photo, submits it, and the Dhanbad officer opens the documents.

**Out of scope:**
- Scheduling, inspection, approve/reject after inspection, certificates (steps 5–8)
- Payments and fees (mocked later)
- OCR, email notifications, malware scanning (see §15)
- "Request changes" back to the business (D7)
- Checking that a re-verification has a previous certificate (step 10)
- The `RENEWAL` application type (D14)

## 2. Amendments to earlier specs (apply in this step)
1. **New error classes** in `app/core/errors.py`, mapped by the existing single handler: `Unprocessable` (422), `PayloadTooLarge` (413), `BadGateway` (502). Spec 02 defined only `NotFound`, `Conflict`, `Forbidden`; if `Unprocessable` and `StrictModel` already exist from the Spec 02 implementation, reuse them.
2. **HTTP client:** the Storage wrapper uses **`httpx2`**, already pinned in `requirements.txt` and API-compatible with `httpx` (moved from dev to runtime dependencies). Set explicit timeouts (connect 5 s, read/write 30 s).
3. **Body-size middleware** (§7): a new pure-ASGI middleware, added to `main.py`.
4. **Router rule:** any endpoint that writes an audit row must commit it, **including GET endpoints** (`GET /documents/{id}/url`). Put the commit in the service, not in the router.
5. **Instruments:** the edit lock, the RESTRICT-based delete and `active_application` from §9 activate now (they were reserved in Spec 02 §6–7).

## 3. Application status flow (from `backend/CLAUDE.md`)
```
DRAFT → SUBMITTED → DOCUMENT_REVIEW → SCHEDULED → INSPECTION → APPROVED | REJECTED → CERTIFICATE_ISSUED
```
`ALLOWED_TRANSITIONS` in `services/applications.py` is the only source of truth. Each edge lists who may take it:

| From → To | Who | Enabled in | Extra rules |
|---|---|---|---|
| DRAFT → SUBMITTED | BUSINESS (owner) | **step 3** | every required document type has ≥1 file (§6) |
| SUBMITTED → DOCUMENT_REVIEW | LM_OFFICER (jurisdiction) | **step 3** | — |
| DOCUMENT_REVIEW → REJECTED | LM_OFFICER (jurisdiction) | **step 3** | `note` required, 10–1000 chars |
| DOCUMENT_REVIEW → SCHEDULED | LM_OFFICER | step 5 | needs date + assigned officer |
| SCHEDULED → INSPECTION | LM_OFFICER | step 6 | — |
| INSPECTION → APPROVED / REJECTED | LM_OFFICER | step 7 | checklist complete |
| APPROVED → CERTIFICATE_ISSUED | system only | step 8 | same transaction as certificate creation; **never** via PATCH |

- The map holds every edge now. Each edge has an `enabled` flag; later steps flip it.
- REJECTED and CERTIFICATE_ISSUED are **terminal**. Re-verification means a new application.
- **Evaluation order for `PATCH /applications/{id}/status`** (so the error codes are unambiguous):
  1. Application not in the caller's scope → **404** (this includes DRAFTs for officials, §4)
  2. `(current status, requested status)` not an edge in the map → **409** `"Invalid status change"`
  3. Caller's role not allowed on that edge → **403**
  4. Edge exists but `enabled=false` → **409** `"This action is not available yet"`
  5. Edge rules fail (missing documents → 409 naming the missing types; missing or bad `note` → 422)
  6. Apply
- `note` is optional (≤1000 chars) on every edge except DOCUMENT_REVIEW → REJECTED, where it is required.
- Every transition runs in one transaction that: locks the application row (`SELECT … FOR UPDATE`), changes the status, sets `submitted_at` on DRAFT → SUBMITTED, writes an `application_status_history` row, and writes an `APPLICATION_STATUS_CHANGED` audit row.
- DISTRICT_ADMIN, STATE_ADMIN, SUPER_ADMIN and GATC have no edges in step 3: they can read (admins) but any transition attempt → 403.

## 4. Access rules
| Action | BUSINESS | LM_OFFICER | DISTRICT_ADMIN / STATE_ADMIN / SUPER_ADMIN | GATC |
|---|---|---|---|---|
| Create / edit / delete a DRAFT | own org | 403 | 403 | 403 |
| Upload / delete documents (DRAFT only) | own org | 403 | 403 | 403 |
| List / get applications | own org (all statuses) | jurisdiction, **non-DRAFT only** | jurisdiction, **non-DRAFT only** (read-only) | 403 |
| Get a document download link | own org | jurisdiction, non-DRAFT | jurisdiction, non-DRAFT | 403 |
| Status transitions | per §3 | per §3 | 403 | 403 |

- **Officials never see DRAFT applications or their documents.** A draft is the business's unfinished work. `scope_applications` excludes `status = DRAFT` for every non-BUSINESS role; a DRAFT id requested by an official → **404**. The officer queue starts at SUBMITTED.
- `services/scoping.py: scope_applications(stmt, user)` sits beside `scope_instruments`. Business: `organization_id`. Officials: the application's `state_code`/`district_code`, plus the non-DRAFT rule. SUPER_ADMIN: all non-DRAFT. It **fails closed**. Out of scope → **404**.
- Documents are always reached **through their application**: `scope_documents` joins to the application and reuses `scope_applications`.

## 5. Data model (migration `0003_applications`)

### `applications`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `application_number` | text, unique | `APP-{YYYY}-{nextval('application_number_seq'):06d}` e.g. `APP-2026-000042` (D4). Display only. Year is the UTC year of creation |
| `instrument_id` | UUID FK → instruments, **ON DELETE RESTRICT**, indexed | |
| `organization_id` | UUID FK → organizations, not null, indexed | copied from the instrument; must equal the caller's org |
| `application_type` | enum `application_type`: `VERIFICATION`, `RE_VERIFICATION` | ASSUMPTION: product labels, not legal terms |
| `status` | enum `application_status` (8 statuses) | default `DRAFT` |
| `state_code`, `district_code` | text, not null | **snapshot** of the instrument's location at creation. Safe, because the location is locked while the application is non-terminal |
| `business_notes` | text, nullable, ≤1000 | |
| `submitted_at` | timestamptz, nullable | |
| `created_by` | UUID FK → users | |
| `created_at`, `updated_at` | timestamptz | |

- **One active application per instrument:** partial unique index `ux_applications_active_instrument` on `(instrument_id) WHERE status NOT IN ('REJECTED','CERTIFICATE_ISSUED')`. Race-free (D5).
- Indexes: `(organization_id, created_at desc)`, `(state_code, district_code, status)`.

### `application_status_history` (append-only, D3)
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `application_id` | UUID FK → applications, ON DELETE CASCADE, indexed | |
| `from_status` | `application_status`, nullable | null for the creation row |
| `to_status` | `application_status`, not null | |
| `actor_user_id` | UUID FK → users | |
| `note` | text, nullable | e.g. the rejection reason |
| `created_at` | timestamptz | |

### `documents`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | generated **before** the upload (it names the object) |
| `application_id` | UUID FK → applications, ON DELETE CASCADE, indexed | |
| `organization_id` | UUID, not null | copied from the application |
| `document_type` | enum `document_type` (§6) | |
| `original_filename` | text, ≤200 | sanitized (§7); **display only**, never used in paths |
| `content_type` | text | the **detected** type, never the client's claim |
| `size_bytes` | int, 1..10 485 760 | |
| `sha256` | text | hex digest of the file bytes |
| `storage_path` | text, unique | `applications/{application_id}/{document_id}.{pdf|jpg|png}`. **Never a URL** |
| `uploaded_by` | UUID FK → users | |
| `created_at` | timestamptz | |

- The migration also creates the sequence `application_number_seq` and the 3 enums (`application_type`, `application_status`, `document_type`). `downgrade` drops the tables, the enums **and** the sequence.

## 6. Document types and requirements
> **ASSUMPTION:** names and requirements are MVP placeholders, **not** the legal requirements. Verify with a domain expert (D6).

| `document_type` | Label | Required for VERIFICATION | Required for RE_VERIFICATION |
|---|---|---|---|
| `PROOF_OF_OWNERSHIP` | Purchase invoice / proof of ownership | ✅ | — |
| `INSTRUMENT_PHOTO` | Photo of the instrument (nameplate visible) | ✅ | ✅ |
| `PREVIOUS_CERTIFICATE` | Previous verification certificate | — | ✅ |
| `MODEL_APPROVAL` | Model approval certificate | optional | optional |
| `OTHER` | Other supporting document | optional | optional |

A requirement is **satisfied** when the application has at least one document of that type. The backend owns this table and serves it via `GET /applications/meta`: document types, labels, required-per-application-type, status labels, and `limits` (`max_file_bytes`, `max_documents`, `allowed_content_types`). The frontend never hard-codes it.

## 7. Upload, download and delete

### Size enforcement happens before parsing (B1)
FastAPI/Starlette parses the multipart body **before** the handler runs, so a size check inside the service is too late (the whole body is already spooled). Add a pure-ASGI **`BodySizeLimitMiddleware`** for `POST /api/documents`:
- Constants: `MAX_FILE = 10_485_760` (10 MiB), `MAX_REQUEST = MAX_FILE + 65_536` (multipart overhead).
- `Content-Length` missing or not an integer → `411`. Greater than `MAX_REQUEST` → `413`, **without reading the body**.
- Wrap `receive` and count bytes as they stream in; if the total exceeds `MAX_REQUEST`, stop and return `413` (covers a lying or absent length).
- Responses use the standard `{"detail": ...}` shape.

### Upload (`POST /api/documents`, multipart: `application_id`, `document_type`, `file`)
1. **Rate limit:** 60 uploads/hour per user (in-memory, same mechanism as Spec 01).
2. **Pre-checks, no lock:** scope-check the application (404), status `DRAFT` (409), `document_type` valid (422).
3. **Read and validate the file:** read at most `MAX_FILE + 1` bytes. More than `MAX_FILE` → `PayloadTooLarge` (413). Empty → `Unprocessable` (422). **Detect the real type from magic bytes**: `%PDF-` → PDF, `\x89PNG\r\n\x1a\n` → PNG, `\xFF\xD8\xFF` → JPEG; anything else → 422 `"Only PDF, JPG and PNG files are allowed"`. The extension and the client `Content-Type` are ignored.
4. **Prepare:** new `document_id`, `storage_path` from the id and the **detected** extension, `sha256`, sanitized filename.
5. **Put the object** into Storage (outside any DB lock). Failure or timeout → `BadGateway` (502) `"Upload failed, please retry"`; no DB row exists.
6. **Commit transaction:** lock the application row (`FOR UPDATE`), **re-check** status is still `DRAFT` and the document count is < 10 (409 otherwise), insert the row, write `DOCUMENT_UPLOADED` (type, size, sha256, **never** contents), commit.
7. If step 6 fails for any reason after step 5, **best-effort delete the object** and re-raise. Unlucky failures leave an orphan object; that is accepted for MVP (see §15).

Locking the application row in step 6 (and in delete, submit and application edit/delete) serializes those actions, so a document can never appear after submit, and two concurrent uploads can't exceed the limit.

### Filename sanitization
Drop any path components; remove control characters, quotes, backslashes and `;`; collapse whitespace; truncate to 200 chars; if empty use `document`; if it doesn't end with the detected extension, append it. The result is the only value ever placed in `download=` or shown in the UI.

### Download link (`GET /api/documents/{id}/url`)
- Scoped through the application (404 otherwise; officials never reach DRAFT documents).
- Returns `{ "url": <absolute Supabase signed URL>, "expires_in": 300 }`. The Storage API returns a **relative** path; the wrapper builds the absolute URL (`{SUPABASE_URL}/storage/v1` + path). Verify the exact format against the Supabase docs during implementation.
- Includes `download=<sanitized filename>`.
- Writes `DOCUMENT_URL_ISSUED` (D9) and **commits it** even though this is a GET (§2.4).
- Accepted risk: a signed link works for anyone holding it until it expires (5 minutes).

### Delete (`DELETE /api/documents/{id}`)
Owner only, DRAFT only. Lock the application row, re-check `DRAFT`, delete the row, write `DOCUMENT_DELETED`, commit; then delete the Storage object best-effort (a failure is logged as an orphan).

### Storage module (`app/storage/`)
- `Storage` protocol: `put(path, data, content_type)`, `delete(paths)`, `signed_url(path, expires_in, download_name)`.
- `SupabaseStorage`: Storage REST API via `httpx2`, authenticated with `SUPABASE_SERVICE_ROLE_KEY`. **No `supabase-py` SDK** (D10). `MemoryStorage` for tests. Selected by `STORAGE_BACKEND: Literal["supabase","memory"] = "supabase"`; `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_BUCKET` are **required when `STORAGE_BACKEND=supabase`** (validated at startup).
- `python -m app.cli create-bucket`: creates the **private** bucket if missing (idempotent), with bucket-level `file_size_limit` = 10 MiB and allowed MIME types = PDF/JPEG/PNG (defence in depth). Run once per environment.
- The service role key never reaches the frontend, logs or responses. Log Storage failures **without** request headers.

### Upload path through the deployment (D2)
Default: browser → Vercel rewrite → Render. Vercel's limit on proxied request bodies is unverified. Make the fallback a **config flip, not a code change**: `lib/api.ts` sends `POST /documents` to `NEXT_PUBLIC_UPLOAD_ORIGIN` when it is set (the public Render URL), otherwise to the relative `/api` path. Direct uploads work because auth is a bearer header, not a cookie; they require `CORS_ORIGINS` to include the Vercel domain and `Authorization` in the allowed headers.

## 8. API
| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| GET | `/applications/meta` | any logged-in user | → `ApplicationMeta` |
| POST | `/applications` | BUSINESS | `{instrument_id, application_type, business_notes?}` → `201 ApplicationOut` |
| GET | `/applications` | BUSINESS, LM_OFFICER, DISTRICT/STATE/SUPER_ADMIN | `?status=&instrument_id=&q=&page=&page_size=` → `Page[ApplicationOut]` |
| GET | `/applications/{id}` | same | → `ApplicationDetail` |
| PATCH | `/applications/{id}` | BUSINESS | `{application_type?, business_notes?}`, DRAFT only → `ApplicationOut` |
| DELETE | `/applications/{id}` | BUSINESS | DRAFT only → `204` |
| PATCH | `/applications/{id}/status` | per §3 | `{status, note?}` → `ApplicationDetail` |
| POST | `/documents` | BUSINESS | multipart → `201 DocumentOut` |
| GET | `/documents/{id}/url` | readers | → `{url, expires_in}` |
| DELETE | `/documents/{id}` | BUSINESS | DRAFT only → `204` |

Register `/applications/meta` **before** `/applications/{id}`. All request schemas use `extra="forbid"`.

- `ApplicationOut`: id, application_number, status, application_type, instrument summary (id, uid, type, serial, capacity, unit), organization_name, state/district, business_notes, submitted_at, created_at, updated_at.
- `ApplicationDetail` = `ApplicationOut` + `documents: [DocumentOut]` + `history: [{from_status, to_status, actor_name, note, created_at}]` + `requirements: [{document_type, label, required, satisfied}]` + `allowed_actions: [status]`.
  - `allowed_actions` = edges from the current status that are **enabled** and allowed for the caller's role. It does **not** consider requirements: the UI disables **Submit** until every required item is `satisfied`.
- `DocumentOut`: id, document_type, original_filename, content_type, size_bytes, created_at. **No `storage_path`, no URL.**
- **Create:** the instrument must be in the caller's scope (404). Lock the instrument row (`FOR UPDATE`), insert the application (org and location copied from the instrument), flush. A partial-unique violation → 409 `"This instrument already has an application in progress"`. Write the creation history row (`null → DRAFT`) and `APPLICATION_CREATED`.
- **PATCH (DRAFT only):** locks the application row; an empty diff → 200, no audit row, `updated_at` unchanged; a real change writes `APPLICATION_UPDATED` with `details.changes`. Changing `application_type` is allowed (requirements are recalculated at submit).
- **DELETE (DRAFT only):** lock the row, collect the document paths, delete the application (documents and history cascade), write `APPLICATION_DELETED`, commit; then delete the Storage objects best-effort.
- `q` searches application number, instrument UID and serial (escaped like instruments, max 100 chars). Sorted by `created_at desc, id`.

## 9. Changes to Step 2 (instruments), activated now
- **Edit lock:** while the instrument has an application whose status is **not** REJECTED or CERTIFICATE_ISSUED (DRAFT counts), PATCHing any of `manufacturer, model, serial_number, capacity, capacity_unit, accuracy_class, state_code, district_code` → 409 `"This instrument has an application in progress; these details can't be changed"`. If that application is a DRAFT, add `"Delete the draft to edit them."` `address`, `latitude` and `longitude` stay editable for now (see §15). The PATCH and application-create both lock the instrument row, so the check can't race.
- **Delete:** the `ON DELETE RESTRICT` FK raises `IntegrityError` → roll back the session and return 409 `"This instrument has applications and can't be deleted"`. This covers **any** application, terminal ones included.
- `InstrumentOut` gains `active_application: {id, application_number, status} | null`, fetched with one LEFT JOIN (no N+1). For officials, a DRAFT is reported as `null`.

## 10. Backend implementation
```
app/core/application_types.py   ApplicationType, ApplicationStatus, DocumentType, REQUIREMENTS, labels
app/core/errors.py              + Unprocessable, PayloadTooLarge, BadGateway (if not present)
app/middleware/body_limit.py    BodySizeLimitMiddleware (pure ASGI)
app/models/application.py       Application, ApplicationStatusHistory
app/models/document.py          Document
app/schemas/application.py      create/update/out/detail/status/meta
app/schemas/document.py         DocumentOut, DocumentUrl
app/services/scoping.py         + scope_applications, scope_documents (non-DRAFT rule for officials)
app/services/applications.py    ALLOWED_TRANSITIONS (with enabled flags), create/list/get/update/delete, transition()
app/services/documents.py       upload (sniff, limits, lock), signed_url, delete, sanitize_filename
app/services/instruments.py     + edit lock, RESTRICT → 409, active_application
app/storage/{base,supabase,memory}.py
app/routers/{applications,documents}.py
app/cli.py                      + create-bucket
alembic/versions/0003_applications.py
```
New runtime dependencies: `python-multipart`, `httpx2`. New setting: `STORAGE_BACKEND`.

## 11. Frontend implementation
| Route | Who | Content |
|---|---|---|
| `/applications` | Business, officials | list with status badges, status filter, search, paging |
| `/applications/new?instrument_id=` | Business | pick an instrument without an active application → type → notes → **Create draft** |
| `/applications/[id]` | Business, officials | header (number, status badge, instrument); **requirements checklist**; upload per document type (DRAFT + business only; `accept="application/pdf,image/jpeg,image/png"`); document list with **View** and Delete (DRAFT only); **Submit** (confirm dialog; disabled until requirements met); officer **Start review** / **Reject** (reason dialog); status timeline |

- Action buttons come from `allowed_actions` (plus the requirements check for Submit).
- **View:** open a blank tab **synchronously on click**, then set its location once the signed URL arrives (avoids Safari and mobile popup blockers). Handle a fetch failure by closing the tab and showing an error.
- The instrument detail page gets **Apply for verification** (no active application) or **View application APP-…**. Because editing is blocked while a draft exists, show the 409 message inline.
- Dashboard: business card shows an applications count and link; officer card shows a "Submitted, awaiting review" count and link.
- `lib/api.ts`: don't set `Content-Type` for `FormData`; route uploads through `NEXT_PUBLIC_UPLOAD_ORIGIN` when set.
- Upload UX: per-file "Uploading…" state, server errors (413/422/409/502) shown inline, and client-side size and type pre-checks as a convenience only.
- Status labels and document types come from `GET /applications/meta`; nothing is hard-coded.

## 12. Tests (backend; `STORAGE_BACKEND=memory`)
Concurrency tests need committed sessions and explicit cleanup.

**Org isolation**
- Business A can't list, get, patch, delete or transition B's application; can't upload to it; can't get a URL for or delete B's document → all 404, B unchanged.

**Visibility of drafts**
- A DRAFT in DHN is absent from the DHN officer's list, `GET` → 404, its document URL → 404, and `active_application` is `null` for the officer. After submit it appears.

**Jurisdiction and RBAC**
- The DHN officer sees DHN applications and gets 404 for RNC/PAT; the state admin sees their state; `scope_applications` fails closed.
- Every endpoint is parameterized over the 6 roles.

**Transitions**
- Each enabled edge succeeds for the right role.
- Evaluation order (§3): non-edge → 409 (even for the wrong role); wrong role on a real edge → 403; not-yet-enabled edge → 409 `"not available yet"`.
- REJECTED is terminal; `CERTIFICATE_ISSUED` can't be set via PATCH.
- Reject without a note, or with a note under 10 chars → 422.
- Submit without required documents → 409 naming the missing types; for RE_VERIFICATION the required set differs.
- Each transition writes exactly one history row and one audit row.
- Two concurrent transitions → exactly one succeeds.

**One active application**
- A second create → 409, including two concurrent creates. After REJECTED, a new application is allowed.

**Instrument rules**
- Identity or location PATCH while an application (DRAFT included) is active → 409, with the "delete the draft" hint when it is a draft; `address` PATCH → 200.
- After REJECTED the lock lifts.
- Deleting an instrument with any application → 409 and the session stays usable.
- `active_application` appears on `InstrumentOut`.

**Uploads**
- PDF, PNG and JPEG accepted; the detected type wins over a fake extension or `Content-Type`.
- An `.exe` or HTML file renamed to `.pdf` → 422.
- Middleware: declared `Content-Length` over the limit → 413 **without the body being read**; missing length → 411; a streamed body exceeding the limit → 413.
- Exactly 10 MiB → accepted; 10 MiB + 1 → 413; empty → 422.
- The 11th document → 409; 11 concurrent uploads to an application with 0 documents → at most 10 rows.
- Upload racing submit: after the submit commits, an in-flight upload → 409 and no extra row (object deleted).
- Upload after submit → 409; document delete after submit → 409.
- Storage `put` fails → 502, no row. Commit fails after `put` → the object is deleted.
- `storage_path` never appears in any response.
- Filename sanitization: `../../x.pdf`, `a";b.pdf`, control characters, 300-char names, empty names.
- Deleting a draft application removes its objects (checked via `MemoryStorage`).
- The 61st upload in an hour → 429.

**Signed URLs**
- `expires_in` ≤ 300; the URL is absolute and contains the sanitized `download` name; out of scope → 404.
- Issuing one writes `DOCUMENT_URL_ISSUED` **and it is committed** (row visible after the GET returns).

**Audit**
- `APPLICATION_CREATED`, `APPLICATION_UPDATED`, `APPLICATION_STATUS_CHANGED`, `APPLICATION_DELETED`, `DOCUMENT_UPLOADED`, `DOCUMENT_DELETED`, `DOCUMENT_URL_ISSUED` each write one row with the right `organization_id`.

## 13. Demo seed (⚠️ seed changes need approval)
- **Do not** seed an application for ABC Traders; the demo creates it live.
- Seed **one SUBMITTED application** for Other Traders' `OTH-0001` (type VERIFICATION) with two tiny generated documents (a one-page PDF and a small PNG) uploaded through the storage layer. This gives the officer a queue item on first login, and gives the isolation check something to hit. The seed requires storage to be configured (it fails with a clear message otherwise) and refuses to run in production without `--force-demo`, like the other seeds.
- Side effect (fine): `OTH-0001` becomes edit-locked in the demo.

## 14. Decisions (resolved)
| # | Decision | Resolution |
|---|---|---|
| D1 | Upload path | **Through FastAPI** (multipart → backend → Storage), so the server checks type and size before storing anything |
| D2 | Vercel rewrite body limit | **Verify on first deploy**; the fallback is a config flip (`NEXT_PUBLIC_UPLOAD_ORIGIN`), not a code change |
| D3 | Status timeline | **New `application_status_history` table** (business users can't read `audit_logs`) |
| D4 | Application number | **`APP-{YYYY}-{seq:06d}`**, one global sequence. Add the convention to `backend/CLAUDE.md` |
| D5 | Active applications per instrument | **One**, enforced by a partial unique index |
| D6 | Document types and requirements | **§6 table, marked ASSUMPTION** |
| D7 | "Request changes" during review | **Not in MVP**: reject with a reason and re-apply |
| D8 | Transitions enabled in step 3 | **Submit, Start review, Reject (during review)** |
| D9 | Audit document access | **Yes** (`DOCUMENT_URL_ISSUED`), committed even on GET |
| D10 | Storage client | **Plain REST via `httpx2`**, no SDK |
| D11 | Payments / fees | **Out of scope** |
| D12 | Seed | **One SUBMITTED application for `OTH-0001` with two generated documents** |
| D13 | Officials see DRAFTs? | **No.** Officer queues start at SUBMITTED |
| D14 | `RENEWAL` application type | **Omitted** (ASSUMPTION); adding it later is an `ALTER TYPE … ADD VALUE` migration |

## 15. Deferred and recorded for later steps
- **Step 5 (scheduling):** lock `address`, `latitude`, `longitude` once the application reaches SCHEDULED, so an assigned officer's target can't change.
- Malware scanning of uploads (required by `CLAUDE.md` "where possible"; not in step 3; accepted MVP risk, mitigated by type sniffing and bucket-level MIME limits).
- Per-organization storage quota; a reconcile job to remove orphan Storage objects.
- "Request changes" flow; copying documents into a new application after a rejection.
- The `RENEWAL` type.

## 16. Acceptance criteria
- [ ] Spec 02 amendments (§2, §9) applied; Spec 01 and Spec 02 tests still pass.
- [ ] `0003_applications` round-trips locally (`upgrade`, `downgrade -1`, `upgrade`; enums and sequence dropped on downgrade) and applies to Supabase; the private bucket exists with the size and MIME limits (`create-bucket`).
- [ ] As `owner@abctraders.demo`: apply for `XYZ12345` → upload an invoice PDF and a photo → submit → status shows SUBMITTED with a timeline.
- [ ] While the application exists, changing the instrument's serial is blocked and deleting the instrument is blocked.
- [ ] As `officer.dhn@lm.demo`: see the seeded Other Traders application and the ABC one → Start review → View both documents (the link opens and stops working after 5 minutes). An ABC **draft** is not visible to the officer.
- [ ] ABC Traders can't reach Other Traders' application or documents by list or by URL (404).
- [ ] A 10 MiB upload works through the deployed Vercel rewrite. If it fails, set `NEXT_PUBLIC_UPLOAD_ORIGIN` and confirm the CORS preflight passes from the Vercel origin.
- [ ] All §12 tests pass; ruff, eslint, tsc and the build are clean.
- [ ] `backend/CLAUDE.md` and `frontend/CLAUDE.md` updated: new tables, transition map and evaluation order, storage module, body-limit middleware, `/applications` and `/documents` APIs, upload rules, the "officials never see DRAFT" rule, and the no-hard-coded-document-types rule.

**Before implementation (you):** put `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_BUCKET` in `backend/.env` (Claude Code must not edit `.env*`). The service role key is under Supabase → Project Settings → API keys; it is a secret, backend only.