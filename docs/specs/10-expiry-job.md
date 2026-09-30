# Spec 10 — Expiry job + admin dashboard (rev 1)

**Status:** Ready for Claude Code (all open decisions resolved, see §10)
**Build order:** Step 10 of 10 — the last MVP step
**Depends on:** Spec 08 rev 1 (`certificates` table, `CertificateStatus`), Spec 09 rev 1
(`core/certificate_status.py: effective_status()`, `ADMIN_ROLES`/scoping precedent reused here)

## 1. Goal

Root `CLAUDE.md`'s lifecycle ends `… Public QR verification → Expiry → Re-verification`, and its stack
table already commits to the mechanism: "Expiry job | Daily cron calling a protected endpoint | Render
Cron / GitHub Actions." Spec 09 built the *read* side (a viewer sees `EXPIRED` computed live, even
before any job has run). This step builds the *write* side: a daily job that actually flips
`certificates.status` to `EXPIRED` once `valid_until` has passed, sends reminder emails at two
thresholds beforehand, and a minimal admin view so someone can see what's expiring without querying the
database directly.

Two things this step is **not**, despite the root `CLAUDE.md` line's phrasing:
- **Not a general admin console.** `backend/CLAUDE.md` never reserved any admin-stats/user-list/audit-
  log-browsing endpoint for this or any other step — none exists today. Root `CLAUDE.md`'s role table
  ("Admin: stats, users, audit logs") and `frontend/CLAUDE.md`'s `/admin` row ("Counts, expiring soon,
  audit log") describe a bigger surface than "Expiry dashboard" literally asks for, and than the demo
  story needs. This spec builds only the **expiry** slice — counts and an expiring-soon list, admin-
  role-gated. A full user-management UI and an audit-log browser are real, separate, unbuilt features
  that would need their own spec; §9/§10 D1 make this explicit rather than silently narrowing scope.
- **Not the "Cron runner: Render Cron vs GitHub Actions" open decision** (root `CLAUDE.md`). This spec
  builds the protected HTTP endpoint the scheduler calls — `POST /api/jobs/expiry-check` — already
  fixed in `backend/CLAUDE.md`'s API block before this spec existed. *Which* external scheduler calls
  it daily is a deployment-config choice outside this repo's code, untouched here.

Demo story: continuing spec 09's demo, `LM-CERT-2026-000001` is `VALID`, expiring 2028-09-30. Nobody
watches this in real time during a hackathon demo, so the walkthrough instead: (a) directly edits a
*second*, disposable demo certificate's `valid_until` into the past, (b) calls
`POST /api/jobs/expiry-check` with the correct secret, and (c) shows three things updating together —
the certificate's stored `status` flips to `EXPIRED` (not just the live-computed view spec 09 already
had), `/verify/{that certificate_number}` still correctly showed `EXPIRED` even before this (spec 09),
and the new `/admin` page's counts move.

**Out of scope:**
- Actually running a scheduler in production (Render Cron / GitHub Actions config) — a deployment
  step, not application code.
- A revoke endpoint/action — still nowhere (spec 08 §9, spec 09 §9 both already deferred it). This
  job never writes `REVOKED`, only ever `VALID → EXPIRED`.
- Re-verification / renewal flows — root `CLAUDE.md`: "a new application is how re-verification
  happens." The reminder email points a business back to logging in, not to any renew button (none
  exists).
- User management UI, audit-log browser UI (§10 D1).
- Payments, GATC, OCR — untouched, per root `CLAUDE.md`.

## 2. Access

**`POST /api/jobs/expiry-check`**: no user, no JWT — a machine-to-machine call authenticated by a
shared secret header, `X-Cron-Secret`, compared against `CRON_SECRET` (`core/config.py` — already
required at startup, currently unused anywhere in the codebase until this step). This is the first
non-JWT auth dependency in the app; `core/deps.py` gains:
```python
def require_cron_secret(x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None) -> None:
    if x_cron_secret is None or not secrets.compare_digest(x_cron_secret, get_settings().CRON_SECRET):
        raise AuthError("Invalid or missing cron secret")

CronAuth = Annotated[None, Depends(require_cron_secret)]
```
`secrets.compare_digest` (constant-time) rather than `==`, since this is a credential comparison.
Missing or wrong header → the existing `AuthError` (401) — this is authenticating *who's calling*, not
authorizing a role, so it reuses the same error class `get_current_user` already raises for a bad JWT,
not a new one. **Not rate-limited** (`backend/CLAUDE.md`'s Security section already only lists
`/auth/login` and `/public/verify` — a trusted scheduler calling once a day was never meant to share
that budget).

**`GET /api/admin/certificates/stats`** and **`GET /api/admin/certificates/expiring-soon`**: role-
gated to the existing `ADMIN_ROLES` (`core/roles.py` — `SUPER_ADMIN, STATE_ADMIN, DISTRICT_ADMIN`,
already defined, currently only used for user-management rank checks, reused here for the first time
for a read endpoint) via `Depends(require_roles(*ADMIN_ROLES))`. Jurisdiction-scoped through the
**existing** `scope_certificates` (spec 08, itself built on `scope_applications`, which already
handles all three admin roles: `SUPER_ADMIN` sees everything, `STATE_ADMIN` its state,
`DISTRICT_ADMIN` its state+district) — no new scoping helper needed.

## 3. Data model (migration `0007_certificate_reminders`)

Two new nullable columns on `certificates`, nothing else:

| column | type | notes |
|---|---|---|
| `reminder_30d_sent_at` | date, nullable | set once the 30-day-out reminder has actually been emailed; `NULL` means "not yet sent" |
| `reminder_7d_sent_at` | date, nullable | same, for the 7-day-out ("urgent") reminder |

No new enum, no new sequence — a plain `op.add_column` pair, dropped the same way in `downgrade()`.
These are the idempotency mechanism (§4): "sent" is a fact recorded on the row itself, not re-derived
from a log, so a second run of the same day (or a run that's late by a week) can tell exactly what
still needs doing.

`app/models/certificate.py`:
```python
reminder_30d_sent_at: Mapped[date | None] = mapped_column(Date)
reminder_7d_sent_at: Mapped[date | None] = mapped_column(Date)
```

## 4. Job flow

`app/services/certificates.py: expiry_check(db: Session) -> ExpiryCheckSummary` — lives alongside
`issue()`/`get()`/`signed_url()`/`public_verify()`, since it's certificate-domain logic, not a
generic "jobs" concern; `routers/jobs.py` stays a thin HTTP wrapper.

1. `today = clock.today()` (spec 05's timezone-aware helper — never `date.today()`).
2. `certificates = db.scalars(select(Certificate).where(Certificate.status == CertificateStatus.VALID))`
   — a single unbounded query. `REVOKED` and already-`EXPIRED` rows are never touched again, matching
   `Certificate`'s own model docstring (spec 08/09's grounding: "step 10 ... only ever flip
   `VALID → EXPIRED`, never touch `REVOKED`"). No pagination/batching — sized for the MVP's certificate
   volume, not a production fleet (§10 D2).
3. For **each** certificate, independently (own try/except, own commit — one certificate's failure
   never blocks another's, same "accepted MVP risk" tradeoff `documents.py: upload()`'s best-effort
   cleanup already makes elsewhere):
   - `days_left = (certificate.valid_until - today).days`.
   - **30-day reminder:** if `days_left <= EXPIRY_REMINDER_30D_DAYS` (default 30) and
     `reminder_30d_sent_at is None`: resolve the recipient(s) (§4.1), send the reminder email; **only
     on send success**, set `reminder_30d_sent_at = today` and commit. A failed send leaves the column
     `NULL`, so tomorrow's run retries it — this is the whole idempotency contract: "sent" means
     "actually sent," not "attempted."
   - **7-day ("urgent") reminder:** same check against `EXPIRY_REMINDER_7D_DAYS` (default 7) and
     `reminder_7d_sent_at`. Both reminders are checked (and can both fire) in the same pass — a job
     that hasn't run in three weeks still sends the 30-day reminder *and* the 7-day reminder in one
     catch-up run, in that order, rather than silently skipping the one whose window already passed.
   - **Expiry:** if `certificate.valid_until < today`: set `status = CertificateStatus.EXPIRED`, write
     one `CERTIFICATE_EXPIRED` audit row (`actor=None` — the only other "system" actor precedent in
     this codebase is `cli.py: create_superadmin()`'s own `actor=None` audit write;
     `entity_type="certificate"`, `entity_id=certificate.id`, `organization_id=certificate.organization_id`,
     `details={"certificate_number", "valid_until"}`, `ip=None` — there's no real client IP for a
     cron-triggered internal write), commit. This runs *after* the reminder checks above, in the same
     per-certificate pass, so a long-overdue certificate gets its final reminder and its expiry flip in
     one run rather than the reminder being silently skipped because the status already moved.
4. Return `ExpiryCheckSummary` (§5) — counts of what happened, for the calling scheduler's own logs.

### 4.1 Recipient resolution

`Certificate.organization_id → the org's BUSINESS user(s)`. `Organization` has no email column
(confirmed — `type, name, registration_number, address, state_code, district_code` only); every
existing signup path (`services/auth.py: register()`) creates exactly one `Organization` + one
`User(role=BUSINESS)` together, but it's not DB-enforced, so `expiry_check()` queries
`select(User.email).where(User.organization_id == certificate.organization_id, User.role == Role.BUSINESS)`
and emails **every** match (ordinarily one). Zero matches (a data anomaly, not expected in the demo) →
skip sending, count it separately (`skipped_no_recipient`, §5), never crash the job over one
certificate's missing recipient.

### 4.2 Email

`app/email/` (new package, deliberately mirrors `app/storage/`'s existing shape — `Storage` protocol +
`SupabaseStorage`/`MemoryStorage` + `get_storage()` picking by `STORAGE_BACKEND` — since this is the
exact same problem: a real backend for prod, a fake one tests can assert against, chosen by one env
var):
```python
class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...

class ResendEmail:
    """Direct REST call to Resend's API via httpx2 — no new SDK dependency, same choice
    SupabaseStorage already made for the same reason."""
    def send(self, *, to: str, subject: str, body: str) -> None: ...  # POST https://api.resend.com/emails

class MemoryEmail:
    """Test/dev double. Appends {to, subject, body} to self.sent instead of calling out."""
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})

def get_email() -> EmailSender: ...  # picks by EMAIL_BACKEND, exactly like get_storage()
```
Plain text, no HTML template engine (no new dependency, matches the PDF's own "content list only, not
a mandated layout" latitude): certificate number, instrument (manufacturer/model/serial from the
snapshot), `valid_until`, and a link to `{PUBLIC_BASE_URL}/login` (there's no renew flow to link to —
§1). `ResendEmail.send()` raising (network/API error) propagates to `expiry_check()`'s per-certificate
try/except (§4) — caught there, not swallowed inside the email module, so the summary's
`email_failures` count stays accurate.

**New settings** (`core/config.py`, same "MVP flat constant, may need tuning" pattern
`SCHEDULING_MAX_DAYS_AHEAD`/`CERTIFICATE_VALIDITY_YEARS` already use):
```python
EMAIL_BACKEND: Literal["resend", "memory"] = "resend"     # mirrors STORAGE_BACKEND
RESEND_FROM_EMAIL: str | None = None                       # required only when EMAIL_BACKEND == "resend"
EXPIRY_REMINDER_30D_DAYS: int = Field(default=30, ge=1)     # ASSUMPTION, not a regulatory rule
EXPIRY_REMINDER_7D_DAYS: int = Field(default=7, ge=1)       # ASSUMPTION, not a regulatory rule
```
`RESEND_API_KEY` already exists (`str | None = None`, currently unused anywhere). When
`EMAIL_BACKEND == "resend"`, both `RESEND_API_KEY` and `RESEND_FROM_EMAIL` become required at startup
— the same conditional-required validation Supabase credentials already get when
`STORAGE_BACKEND == "supabase"`. Local/test runs set `EMAIL_BACKEND=memory` (added to
`tests/conftest.py`'s forced env block, next to the existing `STORAGE_BACKEND=memory`) exactly the way
they already avoid needing real Supabase credentials.

## 5. API

| Method | Path | Allowed | Response |
|---|---|---|---|
| `POST` | `/api/jobs/expiry-check` | `X-Cron-Secret` header only | `ExpiryCheckSummary` |
| `GET` | `/api/admin/certificates/stats` | `ADMIN_ROLES` | `AdminCertificateStats` |
| `GET` | `/api/admin/certificates/expiring-soon` | `ADMIN_ROLES` | `Page[CertificateOut]` |

### Schemas
```python
# app/schemas/jobs.py
class ExpiryCheckSummary(BaseModel):
    checked: int
    reminders_30d_sent: int
    reminders_7d_sent: int
    expired: int
    email_failures: int
    skipped_no_recipient: int

# app/schemas/admin.py
class AdminCertificateStats(BaseModel):
    valid: int            # includes valid-and-expiring-soon; not a disjoint bucket
    expiring_soon: int     # VALID and valid_until <= today + EXPIRY_REMINDER_30D_DAYS
    expired: int
    revoked: int
```
`GET /admin/certificates/expiring-soon` reuses `CertificateOut` (spec 08) as-is for list items — it
already includes `organization_name`, appropriate for an admin viewer (unlike the deliberately
PII-stripped `PublicVerifyOut`, spec 09) — and the existing `Page[T]`/`PageParams` pattern (page ≥1,
page_size ≤100), filtered to `status == VALID and valid_until <= today + EXPIRY_REMINDER_30D_DAYS`,
ordered `valid_until asc` (soonest-expiring first).

### Behaviour rules
- `POST /jobs/expiry-check`: missing/wrong secret → 401. Otherwise always 200 with a summary, even if
  `checked == 0` or every email failed — the job ran; failures are visible in the response body, not a
  5xx, since a partial failure (one bad email) shouldn't make a monitoring system think the whole job
  crashed.
- `GET /admin/certificates/*`: non-admin role → 403 (role-gated by the FastAPI dependency before the
  handler runs, same "role check happens before scope" behavior every other single-role-gated endpoint
  already has — spec 08 §12's documented nuance applies here too, just with `ADMIN_ROLES` instead of
  one role). Out-of-jurisdiction is structurally impossible to express for `STATE_ADMIN`/
  `DISTRICT_ADMIN` here (they only ever see their own scope, never someone else's, so there's no
  404-vs-403 case to test the way spec 08's officer endpoints had).

## 6. Backend implementation

```
alembic/versions/0007_certificate_reminders.py   new: two nullable Date columns
app/models/certificate.py                        + reminder_30d_sent_at, reminder_7d_sent_at
app/core/config.py                               + EMAIL_BACKEND, RESEND_FROM_EMAIL,
                                                    EXPIRY_REMINDER_30D_DAYS, EXPIRY_REMINDER_7D_DAYS;
                                                    conditional-required validation for Resend creds
app/core/deps.py                                 + require_cron_secret(), CronAuth
app/email/__init__.py                            new: EmailSender protocol, get_email()
app/email/resend.py                              new: ResendEmail (httpx2, no SDK)
app/email/memory.py                              new: MemoryEmail (test/dev double)
app/schemas/jobs.py                              new: ExpiryCheckSummary
app/schemas/admin.py                             new: AdminCertificateStats
app/services/certificates.py                     + expiry_check(), _reminder_email_body() helper
app/services/admin.py                            new: certificate_stats(), expiring_soon()
app/routers/jobs.py                              new: POST /jobs/expiry-check
app/routers/admin.py                             new: GET /admin/certificates/stats,
                                                    GET /admin/certificates/expiring-soon
app/main.py                                       register jobs.router, admin.router (appended last,
                                                    alphabetical import between instruments/public for
                                                    jobs, and after public for admin — see main.py's
                                                    existing alphabetical-import/dependency-order split)
tests/conftest.py                                 force EMAIL_BACKEND=memory, next to STORAGE_BACKEND
```
No changes to `app/services/scoping.py` (reuses `scope_certificates` unchanged) or
`app/core/certificate_status.py` (unchanged — `expiry_check()` writes the real status directly by
comparing `valid_until` to `today`, the same comparison `effective_status()` already encodes; it
doesn't call `effective_status()` itself since that function's job is *display*, not *deciding what to
persist* — but both must stay in sync, which is straightforward since neither has any other logic).

## 7. Frontend implementation

| Route | Who | Content |
|---|---|---|
| `app/admin/page.tsx` (new) | `ADMIN_ROLES` | Four count cards (valid / expiring soon / expired / revoked) + a table of expiring-soon certificates |

- `app/admin/layout.tsx` — uses `AppShell` like every other logged-in screen (unlike step 9's public
  page); role-gated in the layout, UX-only (`frontend/CLAUDE.md`'s existing rule — the backend
  enforces it for real via `ADMIN_ROLES`).
- `lib/api.ts`: `getAdminCertificateStats()`, `getExpiringSoonCertificates(page)` (reuses the existing
  generic paged-list type already used by the applications/instruments list pages — confirm its exact
  name at implementation time rather than inventing a new one).
- `lib/types.ts`: `AdminCertificateStats` type mirroring the schema above; the expiring-soon table uses
  the existing `Certificate` type (spec 08) unchanged.
- Table columns: certificate number, organization name, instrument (manufacturer/model), `valid_until`,
  days remaining (computed client-side from `valid_until`, same "never trust the browser clock for
  business-logic decisions, only display" spirit as `frontend/CLAUDE.md`'s scheduling rule — this is
  display-only, the backend already decided what's "expiring soon").
- Standard loading/empty/error/success states (`frontend/CLAUDE.md`'s UI-states rule) — empty state
  ("Nothing expiring soon") is a real, expected state here, not an error.
- `frontend/CLAUDE.md`'s Key screens `/admin` row is corrected to describe what's actually built
  (§10 D1) — "audit log" and "users" removed from that row, since this spec doesn't build them.

## 8. Tests (backend)

New `tests/test_expiry_job.py` (uses the exact `frozen_today` time-freezing fixture pattern already
established in `tests/test_scheduling.py`: `monkeypatch.setattr(clock, "now_utc", lambda: FROZEN)`) and
`tests/test_admin_certificates.py`:

- **Auth**: missing/wrong `X-Cron-Secret` → 401; no `Certificate` row touched.
- **30-day reminder**: a `VALID` certificate with `valid_until` frozen to exactly 30 days out,
  `reminder_30d_sent_at is None` → job → `MemoryEmail.sent` has one entry to the business owner's
  email, `reminder_30d_sent_at` set to today, `status` still `VALID`.
- **7-day reminder**: same shape at 7 days out.
- **Catch-up (both reminders + expiry in one run)**: a certificate whose `valid_until` is already 2
  days in the past and both reminder columns are still `NULL` (simulating a job that hasn't run in a
  month) → one run sends **both** reminder emails and flips `status` to `EXPIRED`, with one
  `CERTIFICATE_EXPIRED` audit row.
- **Idempotency**: run the job twice at the same frozen "today" → the second run sends zero additional
  emails and makes zero additional changes (`ExpiryCheckSummary.reminders_30d_sent == 0` etc. on the
  second call) — this is the literal requirement `backend/CLAUDE.md`'s Expiry job section already
  states.
- **`REVOKED` is never touched**: a `REVOKED` certificate with `valid_until` in the past → job → status
  stays `REVOKED`, no reminder emails, no audit row (it was never `VALID`, so it's outside the job's
  query entirely).
- **Email failure doesn't block the expiry flip or other certificates**: a certificate at day 0 (both
  a reminder due and past `valid_until`) whose `send()` is monkeypatched to raise → `status` still
  flips to `EXPIRED` (independent of email success) and a second, healthy certificate in the same run
  still gets its own reminder sent; the failed one's reminder column stays `NULL` (so it's retried next
  run) and `ExpiryCheckSummary.email_failures == 1`.
- **No recipient**: a certificate whose organization has no `BUSINESS` user (constructed directly,
  bypassing the normal signup path) → job doesn't crash, `skipped_no_recipient == 1`.
- **Admin stats/list scope**: `SUPER_ADMIN` sees every org's expiring certificates; `STATE_ADMIN`/
  `DISTRICT_ADMIN` see only their own jurisdiction (mirrors `scope_applications`'s existing coverage,
  spec 08's `scope_certificates` tests); `BUSINESS`/`LM_OFFICER`/`GATC` → 403.
- **Stats counts are zero-filled and correct**, including the `valid` bucket being inclusive of
  `expiring_soon` (not disjoint) — an explicit assertion, since that's an easy off-by-one to get wrong.

## 9. Deferred and recorded for later (none of these are build-order steps — the MVP build order ends
at step 10)

- A full admin console: user list/management UI, an audit-log browser. Root `CLAUDE.md`'s role table
  and `frontend/CLAUDE.md`'s original `/admin` row description implied these; this spec deliberately
  doesn't build them (§10 D1) — they're real, separate features that would need their own spec.
- Which scheduler (Render Cron vs GitHub Actions) calls `POST /api/jobs/expiry-check` daily — root
  `CLAUDE.md`'s own open decision, a deployment-config choice, not application code.
- A revoke endpoint/action, still nowhere (spec 08 §9, spec 09 §9).
- Retrying a failed reminder email sooner than "whenever the daily job next runs" — no queue, no
  backoff schedule; the daily cadence itself is the retry mechanism.
- Templated/HTML emails, unsubscribe links, delivery-status webhooks from Resend — plain text only.

## 10. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Build the full "Admin: stats, users, audit logs" surface root `CLAUDE.md`/`frontend/CLAUDE.md` gesture at, or just the expiry slice? | **Just expiry** — counts + an expiring-soon list, admin-role-gated. Neither `backend/CLAUDE.md` nor any earlier spec ever actually reserved a user-list or audit-log-browsing endpoint (confirmed: none exists today), and the demo story only needs "expiry is tracked." Building a generic admin console here would be scope creep into an unspecified, undesigned feature; `frontend/CLAUDE.md`'s `/admin` row is corrected to match what's actually built (§7). |
| D2 | Should the expiry job's certificate scan be paginated/batched for scale? | **No — a single unbounded query.** Sized for the MVP's certificate volume (dozens, not millions); root `CLAUDE.md`'s own instruction is "pick the simplest thing that works for the MVP, flag production shortcuts" — this is one. |
| D3 | Reminder trigger semantics: exact single day ("on day 30"), or a threshold ("30 days or fewer remaining")? | **Threshold**, tracked via a nullable `sent_at` column rather than a log — `backend/CLAUDE.md`'s own requirement ("must be idempotent... running it twice sends no duplicate emails") only makes sense against a threshold model: an exact-day model would silently skip anyone the job missed on the exact trigger day (a paused scheduler, a deploy, etc.), while a threshold model catches up correctly on the next run. |
| D4 | New `resend` PyPI dependency, or a direct REST call? | **Direct REST via the already-present `httpx2`** — mirrors `SupabaseStorage`'s own explicit choice ("REST via httpx2, service role key, no SDK") for the identical reason: one fewer dependency, and this codebase has already established the pattern for exactly this kind of "call one REST API with a bearer key" integration. |
| D5 | Email backend selection: hardcode Resend, or mirror `Storage`'s protocol + backend-select pattern? | **Mirror `Storage`.** Tests need to assert what would have been sent without hitting a real API (exactly why `MemoryStorage` exists); a `MemoryEmail` test/dev double selected by a new `EMAIL_BACKEND` env var, parallel to `STORAGE_BACKEND`, is the same solved problem reapplied, not a new pattern to invent. |
| D6 | If a certificate's organization has zero or multiple `BUSINESS` users, what happens? | **Zero → skip and count it (`skipped_no_recipient`), never crash the job over one row. Multiple → email all of them.** `Organization` has no email column and the one-business-user-per-org shape isn't DB-enforced (§4.1), so the job has to tolerate both edge cases rather than assume the happy path every existing signup path happens to produce. |
| D7 | Does a failed reminder email block that certificate's expiry status flip? | **No — independent.** The status flip is the more important side effect (it's what makes `/verify/...`'s live computation and the stored truth agree) and shouldn't depend on an unrelated third-party API being up. A failed email simply leaves its `sent_at` column `NULL` for the next run to retry. |

## 11. Acceptance criteria

- [x] `POST /api/jobs/expiry-check` requires a correct `X-Cron-Secret` header (401 otherwise), and on
  success returns an accurate `ExpiryCheckSummary`.
- [x] Running the job twice against the same data on the same day sends zero duplicate reminder
  emails and makes zero additional changes on the second call.
- [x] A certificate whose `valid_until` has passed gets its **stored** `status` flipped to `EXPIRED`
  (not just the live-computed view spec 09 already provided), with one `CERTIFICATE_EXPIRED` audit
  row.
- [x] A `REVOKED` certificate is never touched by the job, regardless of `valid_until`.
- [x] A certificate that's overdue by weeks still receives both its 30-day and 7-day reminder emails
  (if not already sent) in the same run that also expires it.
- [x] One certificate's email failure never blocks another certificate's processing, and never blocks
  its own expiry status flip; the failed reminder is retried on the next run.
- [x] `GET /admin/certificates/stats` and `.../expiring-soon` are `ADMIN_ROLES`-only (403 otherwise)
  and correctly jurisdiction-scoped for `STATE_ADMIN`/`DISTRICT_ADMIN`.
- [x] `/admin` renders counts and an expiring-soon table from real data, with no login/role bypass.
- [x] `ruff`, `eslint`, `tsc` and the build are clean; backend test suite green including
  `tests/test_expiry_job.py` and `tests/test_admin_certificates.py`.
- [x] Migration `0007_certificate_reminders` round-trips locally and applies to Supabase.
- [x] `backend/CLAUDE.md` updated: "Expiry job" subsection filled in with the real mechanism
  (threshold + `sent_at` columns, `EMAIL_BACKEND`, recipient resolution); new "Admin" API lines; env
  block gains `EMAIL_BACKEND`/`RESEND_FROM_EMAIL`/the two reminder-day settings; migrations table gets
  `0007`; rate-limit line unchanged (confirmed, since `/jobs/expiry-check` isn't rate-limited).
  `frontend/CLAUDE.md`'s `/admin` Key screens row corrected to what's actually built (§10 D1). Root
  `CLAUDE.md` step 10 marked ✅ linking to this spec — the last step in the MVP build order.

## 12. Verification record

One correction to the spec found during implementation: §6 originally had `services/certificates.py:
expiry_check()` compare `certificate.valid_until < today` directly for the expiry decision, deliberately
*not* calling `core/certificate_status.py: effective_status()` (reasoning at the time: "that function's
job is display, not deciding what to persist"). On reflection during implementation this was backwards
— `backend/CLAUDE.md`'s own already-written Public verify section says `effective_status()` is "the
single source of truth step 10's cron should call too, not re-derive." Since services already import
freely from `core/` (no layering issue), `expiry_check()` was changed to call
`effective_status(certificate.status, certificate.valid_until, today=today) ==
CertificateStatus.EXPIRED` instead of re-deriving the comparison — the two paths (live display, actual
persistence) are now structurally guaranteed to agree, not just coincidentally identical logic
maintained in two places.

Backend (`pytest`, local `lm_test`): full suite green — **391 tests**, including 9 new in
`tests/test_expiry_job.py` (auth; 30-day and 7-day reminders individually; a catch-up run sending both
reminders and expiring in one pass; idempotency across two runs; `REVOKED` left untouched; one
certificate's email failure isolated from another's success and from its own expiry flip; no-recipient
handling; an empty-DB sanity check) and 3 new in `tests/test_admin_certificates.py` (role 403s;
`SUPER_ADMIN`/`STATE_ADMIN`/`DISTRICT_ADMIN` jurisdiction scope on the expiring-soon list; zero-filled
stats with `valid` confirmed inclusive of `expiring_soon`, not disjoint). `ruff check`/`ruff format
--check` clean. Migration `0007` round-tripped locally and applied cleanly to Supabase (`alembic
check` clean after).

Frontend (`tsc` via `next build`, `eslint`): clean, no new suppressions. `/admin` is listed as a static
route in the build output.

Manual, against local dev servers (`lm_dev`, `EMAIL_BACKEND=memory`, no real Resend account needed):
created a disposable certificate via the service layer directly (bypassing the UI, since fabricating a
naturally-overdue certificate through the normal issuance flow isn't possible — `valid_from` is always
today), backdated its `valid_until` by 2 days via SQL. `curl -X POST /api/jobs/expiry-check` with no
header and a wrong header both returned 401; with the correct `X-Cron-Secret` it returned `{"checked":
1, "reminders_30d_sent": 1, "reminders_7d_sent": 1, "expired": 1, "email_failures": 0,
"skipped_no_recipient": 0}` — both reminders and the expiry flip firing in one catch-up run, exactly as
designed. `GET /api/public/verify/{certificate_number}` (spec 09) and a direct DB read afterward both
confirmed `status: "EXPIRED"` — the **stored** value, not just spec 09's live computation. A second
`expiry-check` call returned all zeros (idempotent). Logged into `/admin` as the seeded
`admin@lm.demo` (`SUPER_ADMIN`): counts showed 1 Expired, 0 elsewhere, and the expiring-soon table
correctly showed "Nothing expiring soon" (the only certificate had just moved out of that bucket into
Expired). Confirmed the new "Expiry dashboard" link on `/dashboard`'s admin card reaches `/admin`
correctly — the discoverability gap noted during planning (§7).

Incidental note, not a code issue: an earlier `alembic downgrade -1` run against local `lm_dev` during
this session's migration round-trip was mistakenly issued while still on revision `0006` (before `0007`
existed), which downgraded `0006 -> 0005` and dropped the whole `certificates` table (migration `0006`
owns its creation) rather than testing `0007`'s own down-migration. This was caught immediately and the
correct round-trip (`0007 -> 0006 -> 0007`) was re-run afterward with a clean `alembic check` — but it
means `lm_dev`'s previously-issued demo certificates (from earlier sessions' spec 08/09 walkthroughs)
were wiped locally. Supabase was never touched by this mistake (confirmed via `alembic current`
throughout). Purely local, disposable dev data; re-seeding or re-issuing certificates against `lm_dev`
is unaffected otherwise.
