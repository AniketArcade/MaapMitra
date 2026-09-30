# Spec 09 — Public QR verification (rev 1)

**Status:** Ready for Claude Code (all open decisions resolved, see §10)
**Build order:** Step 9 of 10
**Depends on:** Spec 08 rev 1 (`certificates` table, `certificate_number` format, the immutable
`snapshot` JSONB, the `{PUBLIC_BASE_URL}/verify/{certificate_number}` URL the PDF's QR already
encodes)

## 1. Goal

Root `CLAUDE.md`'s lifecycle ends `… Certificate + QR → Public QR verification → Expiry …`. Spec 08
built the certificate and a QR that already points at `{PUBLIC_BASE_URL}/verify/{certificate_number}`
— but nothing serves that URL yet. This step builds the last public-facing piece: anyone who scans the
QR (or types the certificate number in) reaches a page, with no login, that says whether the
certificate is genuine and current.

Both the endpoint and the page were **pre-reserved, not newly designed, in this step**:
`backend/CLAUDE.md`'s API block already lists `GET /api/public/verify/{certificate_number} # no auth`
and a "Public verify" subsection (field whitelist, live status, rate-limited);
`frontend/CLAUDE.md`'s structure tree already reserves `app/verify/[certificateNumber]/ # PUBLIC, no
auth`, its Key screens table already describes "Big status badge: ✓ VALID / ⚠ EXPIRED / ✕ REVOKED",
and `proxy.ts`'s matcher already excludes `verify` from the login redirect. This spec is what actually
builds those already-agreed shapes, and pins down the handful of details neither file spelled out
(exact response field list, rate limit value, status-precedence rule, PDF exposure).

Demo story: continuing spec 08's demo, `LM-CERT-2026-000001` now exists. A consumer scans the QR
printed on ABC Traders' weighing-scale certificate (or on the PDF), lands on `/verify/LM-CERT-2026-000001`
with no login prompt, and sees a large ✓ VALID badge with the instrument's type/model/serial and
validity dates — enough to trust the scale without seeing anything about ABC Traders itself.

**Out of scope:**
- `EXPIRED`/`REVOKED` becoming the certificate's **stored** status, and the reminder emails — that's
  step 10's daily job. This step only computes the *displayed* status live (§4); it never writes to
  `certificates.status`.
- A revoke endpoint or admin action. Still not designed anywhere (spec 08 §9 also deferred it) — this
  step's status precedence (§4) assumes a `REVOKED` row can exist, but nothing yet creates one outside
  a manual DB edit.
- Any UI for viewing or downloading the certificate PDF from the public page (§10 D4 — deliberately
  refused, not merely unbuilt).
- Payments, GATC, OCR — untouched, per root `CLAUDE.md`.

## 2. Access

**No authentication, no RBAC dependency.** The endpoint takes only `db: DB` — no `CurrentUser`, no
`require_roles(...)`. This is the one deliberate exception to "every read of org-owned data goes
through a `scope_*` helper" (`backend/CLAUDE.md`): a certificate's verification-relevant fields are, by
design, not org-owned data once issued — that's the entire point of a public QR. `scope_certificates`
(spec 08) stays untouched and unused here.

Root `CLAUDE.md`'s role table already lists this: "**Public:** QR verification only." No new role is
added to `core/roles.py` — "public" here means "no `Depends` at all," not a `Role` enum member.

## 3. Data model

**None.** No migration, no new column, no new table. `certificate_number` is already `unique=True`
(migration `0006`), so Postgres already has the unique index this lookup needs — a single indexed
`WHERE certificate_number = :n` query, no joins, since every field the response needs (§5) already
lives in `certificates.snapshot`/`valid_from`/`valid_until`/`status` (spec 08 §3.1's JSONB snapshot
pays for itself again here: no `Application`/`Instrument` join needed just to answer "is this genuine,"
which matters for a page whose one hard requirement is "must load fast on mobile data"
(`frontend/CLAUDE.md`).

## 4. Status precedence (the "live" computation)

`certificates.status` is a stored column that only step 10's cron will ever move off `VALID` — but a
certificate can be genuinely past `valid_until` for weeks before that job next runs. `backend/CLAUDE.md`
already commits to "Computes status live: if `valid_until < today`, return EXPIRED even if the cron
hasn't run yet." This step is what implements that, as a small pure function so step 10 can reuse the
exact same rule instead of re-deriving it:

`app/core/certificate_status.py` (new — same shape and reasoning as `core/instrument_lock.py:
locked_fields()`, a single source of truth several layers call):
```python
def effective_status(
    status: CertificateStatus, valid_until: date, *, today: date
) -> CertificateStatus:
    if status == CertificateStatus.REVOKED:
        return CertificateStatus.REVOKED  # a revoke is permanent, never "expires" instead
    if valid_until < today:
        return CertificateStatus.EXPIRED
    return status  # VALID, or already EXPIRED if step 10's cron already ran
```
`REVOKED` always wins over a date comparison — once revoked, a certificate never displays as merely
expired, even if it's also past `valid_until`. Called with `clock.today()` (spec 05's
timezone-aware helper — never `date.today()`), never persisted by this step.

## 5. API

| Method | Path | Allowed | Response |
|---|---|---|---|
| `GET` | `/api/public/verify/{certificate_number}` | anyone, no auth | `PublicVerifyOut` |

`certificate_number` is matched **exactly** (case-sensitive, no normalization) — the format
(`LM-CERT-{year}-{seq:06d}`) is fixed and the QR encodes it verbatim, so this is a lookup by natural
key, not a search. No format validation on the path param either: anything that doesn't match a row
simply 404s, which is cheap (one indexed lookup) and correct — no reason to duplicate the
`LM-CERT-\d{4}-\d{6}` shape as a second, separately-maintained check.

### Schema (`app/schemas/public.py`, new)
```python
class PublicVerifyOut(BaseModel):
    certificate_number: str
    status: CertificateStatus
    instrument_type_label: str
    manufacturer: str
    model: str
    serial_number: str
    valid_from: date
    valid_until: date

    @classmethod
    def from_model(cls, c: Certificate) -> Self:
        s = c.snapshot
        return cls(
            certificate_number=c.certificate_number,
            status=effective_status(c.status, c.valid_until, today=clock.today()),
            instrument_type_label=TYPE_LABELS[InstrumentType(s["instrument_type"])],
            manufacturer=s["manufacturer"],
            model=s["model"],
            serial_number=s["serial_number"],
            valid_from=c.valid_from,
            valid_until=c.valid_until,
        )
```
This is the **complete** field list — nothing else goes on the wire. No `id`, `application_id`,
`organization_name`, `application_number`, `address`, `state_name`/`district_name`,
`approved_by_name`, `pdf_path` or `data_hash`. `backend/CLAUDE.md`'s line ("certificate number,
instrument type/model/serial, `valid_until` and status") is honored as a floor, not a literal
exhaustive list — `manufacturer` is added because "model/serial" alone doesn't identify an instrument
without it, and `valid_from` is added so the page can show a validity range instead of just an end
date. Both are physical-instrument facts, not business/owner identity, so neither reopens the "no
owner PII" rule. `backend/CLAUDE.md`'s Public verify subsection is updated to this exact list (§11).

**Why `instrument_type_label`, not the raw `InstrumentType` enum + a client-side lookup:** every other
screen in the app resolves enum → label via `getInstrumentMeta()` (`GET /instruments/meta`,
"any logged-in user" — `backend/CLAUDE.md`'s API block). `/verify/[certificateNumber]` has no session,
so it structurally cannot call an auth-gated meta endpoint — doing so would 401, and `lib/api.ts`'s
401 handler would try a refresh and then redirect to `/login`, exactly the "navigation to a private
area" `frontend/CLAUDE.md`'s Public verify page rules forbid. `app/pdf/certificate.py` already solved
an equivalent problem (rendering has no HTTP client to call meta with either) the same way: import
`TYPE_LABELS` (`core/instrument_types.py`) directly. This endpoint does the same — the label is
computed server-side from the same canonical dict, so "never hard-code instrument type labels" still
holds (the frontend still hard-codes nothing; it just receives a pre-labeled string instead of a code
it would otherwise have to resolve itself).

### Behaviour rules
- No matching `certificate_number` → **404** `"Certificate not found"` (mirrors
  `services/certificates.py: get()`'s existing message).
- No audit row is written. Every other audited action in this codebase has an actor; an anonymous,
  high-volume, non-mutating public read doesn't fit `audit_logs`' shape or purpose, and logging one row
  per QR scan would make the table's volume driven by public traffic instead of internal actions (§10
  D2).
- Rate-limited via the existing `slowapi` `limiter` (`core/rate_limit.py`), same mechanism as
  `/auth/login`: `@limiter.limit("30/minute")` per IP (§10 D3). This isn't just abuse prevention — spec
  08 D2 already flagged that `certificate_number`'s sequential format is enumerable, and named this
  step's rate limit as the mitigation.
- CORS: same app-wide policy as every other route (`backend/CLAUDE.md`'s CORS section) — no relaxation
  needed since the browser already calls same-origin `/api/*` through the Next.js rewrite, exactly like
  every authenticated call.

## 6. Backend implementation

```
app/core/certificate_status.py     new: effective_status()
app/schemas/public.py               new: PublicVerifyOut
app/services/certificates.py        + public_verify(db, certificate_number) -> Certificate
app/routers/public.py               new: GET /verify/{certificate_number}  (rate-limited, no auth)
app/main.py                         register public.router (prefix "/public")
```
`services/certificates.py: public_verify()`:
```python
def public_verify(db: Session, certificate_number: str) -> Certificate:
    """No scope check: deliberately public (spec 09 §2). One indexed lookup, no joins — every
    field PublicVerifyOut needs already lives on this row (spec 08 §3.1's snapshot)."""
    certificate = db.scalar(
        select(Certificate).where(Certificate.certificate_number == certificate_number)
    )
    if certificate is None:
        raise NotFound("Certificate not found")
    return certificate
```
`routers/public.py`:
```python
router = APIRouter(prefix="/public", tags=["public"])

@router.get("/verify/{certificate_number}")
@limiter.limit("30/minute")
def verify(request: Request, certificate_number: str, db: DB) -> PublicVerifyOut:
    certificate = certificates_service.public_verify(db, certificate_number)
    return PublicVerifyOut.from_model(certificate)
```
`app/main.py`: add `public` to the router import tuple (alphabetical — between `instruments` and
`users`) and `public.router,` to the registration tuple (last, after `certificates.router,` — it's the
newest/least-depended-on router, matching the existing "spec/dependency order" the tuple already
follows).

No changes to `app/services/scoping.py`, `app/core/deps.py`, `app/models/certificate.py`, or the
`certificates` table.

## 7. Frontend implementation

| Route | Who | Content |
|---|---|---|
| `app/verify/[certificateNumber]/page.tsx` (new) | Public | Status badge, instrument summary, validity — nothing else |

- `app/verify/[certificateNumber]/layout.tsx` (new) — **no `AppShell`** (no header nav, no auth guard
  to skip past — there's nothing to guard). Reuses the exact centered-card shape
  `app/(auth)/layout.tsx` already uses for the equally-public login/register pages:
  ```tsx
  <main className="flex flex-1 items-center justify-center bg-muted/40 px-4 py-10">{children}</main>
  ```
- `page.tsx`: `"use client"`, fetches on mount via `getPublicVerify(certificateNumber)`
  (`useParams()`), handling all four states `frontend/CLAUDE.md`'s UI-states rule requires —
  loading, **empty is a 404** ("Certificate not found", not a blank page), error (network/5xx —
  distinct message, e.g. "Couldn't check this certificate. Try again."), and success. On success:
  a large badge — ✓ VALID (green) / ⚠ EXPIRED (amber) / ✕ REVOKED (red), per `frontend/CLAUDE.md`'s
  Key screens line — plus `instrument_type_label` + manufacturer + model + serial_number, and
  `valid_from`–`valid_until`. `certificate_number` printed once, at the top.
  - No sign-in prompt, no link to `/login`, no link back into the app — this page is a dead end by
    design, reachable only from a QR/URL, matching "no navigation to private areas"
    (`frontend/CLAUDE.md`'s Public verify page rules).
  - `AuthProvider`'s existing unconditional `/auth/refresh` call on every page mount (`lib/auth.ts`)
    fires here too, exactly as it already does on `/login`/`/register` today — it's a pre-existing,
    silent, harmless no-op without a session cookie. Not a regression this step introduces; no special
    case needed.
- `lib/api.ts`: `getPublicVerify(certificateNumber: string): Promise<VerifyResult>` — a plain
  `api<VerifyResult>(\`/public/verify/${certificateNumber}\`)` call. This is safe to route through the
  ordinary `api()` wrapper unmodified: the endpoint never returns 401 (there's nothing to authenticate),
  so `api()`'s refresh-then-redirect-to-login branch can never trigger for it.
- `lib/types.ts`: new `VerifyResult` type mirroring `PublicVerifyOut` exactly (`certificate_number`,
  `status`, `instrument_type_label`, `manufacturer`, `model`, `serial_number`, `valid_from`,
  `valid_until`).
- `proxy.ts`: **no change** — its matcher already excludes `verify` (pre-reserved before this spec
  existed). Confirm this as a regression check, don't re-add it.

## 8. Tests (backend)

New `tests/test_public_verify.py`, all calling `client.get(...)` **without** `auth_header(...)`:
- **Success (VALID):** issue a real certificate through the existing spec 08 flow
  (`make_application(status="APPROVED")` → `certificates_service.issue()`), then `GET
  /api/public/verify/{certificate_number}` with no `Authorization` header → 200, `status == "VALID"`,
  every field matches the certificate's snapshot/dates, response JSON's key set is **exactly** the
  `PublicVerifyOut` fields (explicit assertion that `organization_name`, `id`, `application_id`,
  `pdf_path`, `data_hash`, `address` etc. are absent — a regression guard on the "no owner PII, no
  internal IDs" rule, not just a happy-path check).
- **Not found:** a random/garbage string → 404 `"Certificate not found"`.
- **Live EXPIRED:** create a certificate whose `valid_until` is in the past (write the row directly
  via `SessionLocal`, bypassing `issue()` — no need to freeze `clock.today()`) while `status` stays the
  stored `VALID` → `GET` → 200, `status == "EXPIRED"`. Proves the override is computed per-request, not
  dependent on step 10's cron ever having run.
- **REVOKED beats an expired date:** same as above but also set `status = CertificateStatus.REVOKED`
  → `GET` → 200, `status == "REVOKED"`, not `"EXPIRED"` — proves the precedence order in §4.
- **Truly public:** the same request succeeds identically with no header, with a random business
  user's token, and with an out-of-jurisdiction officer's token — proves this isn't accidentally still
  scope-gated by something upstream (e.g. a shared dependency reintroduced later).
- **Rate limit:** mirrors `test_login_per_ip_limit`'s exact shape — 30 requests (mix of hits and
  misses; either is fine) from one `TestClient` all return non-429, the 31st returns 429.

## 9. Deferred and recorded for later steps

- **Step 10:** the daily expiry job writes `EXPIRED` into `certificates.status` for real (reminders,
  idempotency) — it should call the same `effective_status()`/`core/certificate_status.py` this step
  introduces to decide *which* certificates need the write, rather than re-deriving the date
  comparison. Also: whether `CertificateOut` (the **authenticated** `GET /certificates/{id}`, spec 08)
  should start showing this same live-computed status instead of the raw stored column — left alone in
  this step (§10 D1) but worth revisiting once step 10 makes `EXPIRED`/`REVOKED` real stored values.
- A revoke endpoint/admin action — still nowhere, same as spec 08 §9 already noted.
- Any caching/CDN layer in front of `/public/verify` — unnecessary at MVP/demo scale; a single indexed
  row lookup is already fast enough.

## 10. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Should the authenticated `GET /certificates/{id}` (spec 08) also switch to `effective_status()`? | **No, not in this step.** It keeps returning the raw stored `status` (always `VALID` until step 10's cron exists). Changing it now would be scope creep into a screen this spec doesn't own; noted as a step-10 follow-up (§9) instead. |
| D2 | Audit-log every public verify hit? | **No.** No actor, high anonymous volume, non-mutating — doesn't fit `audit_logs`' existing shape or purpose. If usage analytics are ever wanted, that's a separate, explicitly-scoped metrics decision, not a silent addition to the audit trail. |
| D3 | Rate limit value | **30/minute per IP**, via the existing `slowapi` `limiter` (same mechanism as `/auth/login`'s `20/minute`). **ASSUMPTION** — a production-tuning knob, picked to comfortably cover a burst of legitimate scans while still meaningfully slowing down enumeration of the sequential `certificate_number` format (spec 08 D2). |
| D4 | Should `/verify/[certificateNumber]` also offer View/Download of the certificate PDF, like the authenticated `/certificates/[id]` page does? | **No — deliberately refused, not just unbuilt.** The PDF (`app/pdf/certificate.py: render()`) embeds the full snapshot: `address`, `state_name`/`district_name`, `organization_name`, `approved_by_name` — exactly the fields §5's whitelist exists to withhold. A signed-URL link to it from this page would leak everything the public API deliberately doesn't return. The public page shows only `PublicVerifyOut`'s fields; it never references `pdf_path` or calls anything PDF-related. |
| D5 | Exact `certificate_number` match, or case-insensitive / trimmed? | **Exact match only.** The format has no ambiguous casing and the only realistic entry path is a QR scan (which reproduces the string exactly) or a copy-paste from the PDF. A more forgiving match is easy to add later if manual entry turns out to matter; adding it speculatively now is unjustified complexity. |

## 11. Acceptance criteria

- [x] `GET /api/public/verify/{certificate_number}` requires no auth and returns exactly the
  `PublicVerifyOut` field set for a real, issued certificate.
- [x] A `VALID` certificate whose `valid_until` has already passed shows `EXPIRED`, without needing
  step 10's cron to have run.
- [x] A `REVOKED` certificate always shows `REVOKED`, even past its `valid_until`.
- [x] An unknown `certificate_number` → 404 `"Certificate not found"`, not a 500 or an empty 200.
- [x] The response never includes `organization_name`, any internal ID, `address`, `pdf_path`,
  `data_hash` or any other field beyond the documented whitelist.
- [x] More than 30 requests/minute from one IP → 429, matching the existing rate-limit response shape.
- [x] `/verify/[certificateNumber]` renders with no login prompt, no header nav, and no link into any
  private area of the app; scanning a real demo certificate's QR (`LM-CERT-2026-000001`) reaches it
  directly and shows a correct ✓ VALID badge.
- [x] `ruff`, `eslint`, `tsc` and the build are clean; backend test suite green including
  `tests/test_public_verify.py`.
- [x] `backend/CLAUDE.md` updated: the "Public verify" subsection's field list matches `PublicVerifyOut`
  exactly (not just the shorthand it currently has); a short "Public verify (step 9)" subsection added
  under Application status flow or its own heading, naming `core/certificate_status.py:
  effective_status()` and its reuse plan for step 10; API block's `GET
  /api/public/verify/{certificate_number}` line confirmed (already present); rate limit line updated
  ("login 5/min per email + 20/min per IP, register 10/hour per IP, public verify 30/min per IP").
  `frontend/CLAUDE.md`'s Key screens `/verify/[certificateNumber]` row confirmed/expanded with the real
  field list. Root `CLAUDE.md` step 9 marked ✅ linking to this spec.

## 12. Verification record

No corrections to the spec were needed during implementation — the grounding done before coding
(confirming `core/deps.py`/`core/security.py` already import from `models/`, so
`core/certificate_status.py` importing `CertificateStatus` from `app.models.certificate` isn't a new
layering pattern) held up exactly as expected.

One test-writing note, not a spec or implementation bug: the first version of the "live EXPIRED" test
moved `valid_until` back by `timedelta(days=1)` from its issued value (`today + 2 years`), which is
still two years in the future — the assertion correctly failed (`VALID`, not `EXPIRED`). Fixed by
setting `valid_until = clock.today() - timedelta(days=1)` directly instead of subtracting from the
already-future date.

Backend (`pytest`, local `lm_test`): full suite green — **379 tests**, including 6 new in
`tests/test_public_verify.py` (success with an exact-field-set assertion; not-found; live `EXPIRED`
via a direct row edit with the stored status left `VALID`; `REVOKED` beating an expired date; identical
response with no auth header vs. a random business token vs. an out-of-jurisdiction officer token;
30/minute rate limit). `ruff check`/`ruff format --check` clean. No migration in this step, so nothing
to apply to Supabase.

Frontend (`tsc --noEmit`, `eslint`, `next build`): clean, no new suppressions. `/verify/[certificateNumber]`
is listed as a dynamic route in the build output.

Manual, in Chrome against local dev servers (`lm_dev`): navigated directly to
`/verify/LM-CERT-2026-000001` — no login prompt, no header nav, a green ✓ VALID badge with "Weighing
scale", "Essae Teraoka", "DS-252", "XYZ12345", "30/09/2026 – 30/09/2028". The network tab confirmed the
page's own `GET /api/public/verify/...` call (a separate, harmless `POST /api/auth/refresh` also fired
from the pre-existing, unconditional `AuthProvider` mount effect, unrelated to this page and succeeding
only because this browser profile already had a valid session from an earlier session — the verify
call itself never depends on it). A bogus certificate number (`LM-CERT-2026-999999`) rendered
"Certificate not found" via the same `StateMessage` component `/certificates/[id]` already uses.
