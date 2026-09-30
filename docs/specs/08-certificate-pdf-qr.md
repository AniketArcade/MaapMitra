# Spec 08 — Certificate PDF + QR (rev 1)

**Status:** Ready for Claude Code (all open decisions resolved, see §10)
**Build order:** Step 8 of 10
**Depends on:** Spec 07 rev 1 (`APPROVED` status, the `(APPROVED, CERTIFICATE_ISSUED)` edge already
reserved as system-only), Spec 05 rev 2 (`LOCATION_LOCK_STATUSES`, the instrument lock lifecycle),
Spec 03 rev 2 (`documents.upload()`'s put-outside-lock ordering and `signed_url()`'s "audit-writing GET
commits in the service" pattern, both reused as-is)

## 1. Goal

Root `CLAUDE.md`'s lifecycle is `… Approve/Reject → Certificate + QR → Public QR verification …`. Spec
07 stopped at `APPROVED` — a stable, non-terminal status. This step builds the last mile: an in-scope
officer issues the certificate, producing a PDF with an embedded QR and moving the application to the
terminal `CERTIFICATE_ISSUED` status. `ALLOWED_TRANSITIONS` (`services/applications.py`) already
reserves this exact edge:
```python
# System only: happens inside certificate creation (step 8), never via PATCH.
(S.APPROVED, S.CERTIFICATE_ISSUED): Edge(frozenset(), enabled=False),
```
`roles=frozenset()` means no role can ever pass `transition()`'s role check for this pair — confirmed
by the existing `test_certificate_issued_never_via_patch`. This step doesn't flip that edge; it builds
a dedicated endpoint that bypasses `transition()` entirely, exactly as the comment already says.

Demo story: continuing spec 07's demo, once the seeded ABC Traders application reads `APPROVED`, the
officer clicks **Issue certificate**. A certificate row is created with a real, sequential
`certificate_number` (e.g. `LM-CERT-2026-000001`), a PDF is rendered and stored, and the application
becomes `CERTIFICATE_ISSUED`. The instrument's location fields unlock (terminal status). The demo is
now ready for step 9: scanning the PDF's QR should reach a working (if not-yet-built) verify URL.

**Out of scope:**
- The public verify page itself (step 9). This spec only guarantees the QR/URL shape it produces is
  correct — `{PUBLIC_BASE_URL}/verify/{certificate_number}`, already fixed by backend/CLAUDE.md's QR
  section — and that `GET /api/public/verify/{certificate_number}` has a real row to look up once step
  9 builds the endpoint and page.
- `EXPIRED`/`REVOKED` transitions and the daily expiry job (step 10). Every certificate this step
  creates has `status = VALID`; nothing here ever changes it.
- A revoke endpoint or admin action. Not designed anywhere yet — flagged deferred (§9).
- Payments. Root `CLAUDE.md`'s separate open decision ("mocked in MVP, `payments` table only"),
  untouched by this step — certificate issuance is never gated on a payment.
- Re-verification. Once `CERTIFICATE_ISSUED` (terminal), a new application is how re-verification
  happens (root `CLAUDE.md`), not a feature of this step.

## 2. Access

- **Issuing** (`POST /api/applications/{id}/certificate`): role `LM_OFFICER`, any in-scope officer —
  **not** assigned-officer-locked, consistent with spec 07 D1. By the time an application is
  `APPROVED` the judgment call is already made; issuing is bookkeeping (render, store, flip status),
  not a decision, so the same "any in-jurisdiction officer" reasoning applies.
- **Reading** a certificate (`GET /certificates/{id}`, `GET /certificates/{id}/pdf`) uses a new
  `scope_certificates` helper (`services/scoping.py`), the same shape as `scope_documents`/
  `scope_inspections` (join to `Application`, reuse `scope_applications`):
  ```python
  def scope_certificates(stmt: Select[Any], user: User) -> Select[Any]:
      return scope_applications(
          stmt.join(Application, Certificate.application_id == Application.id), user
      )
  ```
  Same Reader set as the application itself: the owning business, in-jurisdiction officials, admins.
  Out of scope → 404, never 403 (fails closed, same rule as every other scoped read).

## 3. Data model (migration `0006_certificates`)

No existing table is altered. New `certificates` table:

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `application_id` | UUID FK → applications, `ON DELETE RESTRICT`, unique | one certificate per application, ever |
| `organization_id` | UUID, not null | denormalized, no FK — exactly `documents.organization_id`'s pattern, scoping convenience only |
| `certificate_number` | text, unique, not null | `LM-CERT-{UTC year}-{nextval('certificate_number_seq'):06d}`, display only (mirrors `application_number`'s pattern) |
| `snapshot` | JSONB, not null | instrument + business fields frozen at issuance (§3.1) |
| `valid_from` | date, not null | the issue date |
| `valid_until` | date, not null | `valid_from + CERTIFICATE_VALIDITY_YEARS` |
| `status` | enum `certificate_status` (`VALID`, `EXPIRED`, `REVOKED`), not null, default `VALID` | this step only ever writes `VALID` |
| `pdf_path` | text, unique, not null | `certificates/{id}.pdf` — never a URL |
| `data_hash` | text, not null | SHA-256 hex digest, formula fixed in §3.2 |
| `created_at` | timestamptz | `Timestamps` mixin; doubles as "issued at" |

New `certificate_number_seq` (hand-written in the migration, same as `application_number_seq`/
`instrument_uid_seq` — autogenerate misses sequences, both creation and drop).

### 3.1 Why a JSONB snapshot, not relational rows

Spec 06 D3 chose relational rows over a JSONB blob for checklist items — but that was a *list* of
independently-editable rows read and written across several requests. A certificate's snapshot is the
opposite: one immutable bundle, written exactly once at issuance, always read whole, never filtered or
updated. A single JSONB column is the simpler, correct shape here (§10 D5) — not an inconsistency with
spec 06's reasoning, its opposite case.

**Why a snapshot at all, not a live join:** `CERTIFICATE_ISSUED` is terminal
(`TERMINAL_STATUSES`, `core/application_types.py`), and `core/instrument_lock.py`'s `locked_fields()`
already returns `frozenset()` once the active application's status is terminal — **the instrument
becomes editable again the moment the certificate is issued.** If the certificate only stored
`application_id` and joined live, a business editing the instrument's manufacturer afterward would
silently change what the already-issued certificate displays. The snapshot is taken once, from the
already-loaded `application` (instrument + organization + approving officer), and never touched again —
the same "snapshot, not a live reference" principle spec 06 §5 already established for checklist items.

Snapshot fields (all plain JSON scalars):
```json
{
  "instrument_uid": "LM-JH-DHN-000002",
  "instrument_type": "WEIGHING_SCALE",
  "manufacturer": "Essae Teraoka",
  "model": "DS-252",
  "serial_number": "XYZ12345",
  "capacity": 500.0,
  "capacity_unit": "kg",
  "accuracy_class": null,
  "address": "Bank More, Dhanbad",
  "state_name": "Jharkhand",
  "district_name": "Dhanbad",
  "organization_name": "ABC Traders",
  "application_number": "APP-2026-000002",
  "approved_by_name": "Dhanbad LM Officer"
}
```
`state_name`/`district_name` come from `core/regions.py`'s `REGIONS[state_code]["name"]` /
`REGIONS[state_code]["districts"][district_code]` — codes alone aren't presentable on a certificate.
`approved_by_name` is the actor of the application's most recent history row where
`to_status == APPROVED` (`application.history`, already loaded).

### 3.2 `data_hash` formula

Fixed and documented here so it's reproducible outside this code if ever needed (e.g. a future manual
integrity check): SHA-256 hex digest of
```python
f"{certificate_number}|{instrument_uid}|{manufacturer}|{model}|{serial_number}|"
f"{organization_name}|{valid_from.isoformat()}|{valid_until.isoformat()}"
```
This is deliberately a hash of *fields*, not of the PDF bytes — root `CLAUDE.md`'s open decision
("Digital signature: hash-based in MVP, government e-sign later") means this is a tamper-evidence
fingerprint over the data a verifier can already see, not a cryptographic signature over the file. The
PDF prints a short form (first 16 hex chars) for a human to eyeball; the full value is stored for any
future automated check.

### 3.3 Model

`app/models/certificate.py`:
```python
class CertificateStatus(StrEnum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"

class Certificate(UUIDPk, Timestamps, Base):
    __tablename__ = "certificates"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    certificate_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, name="certificate_status"), nullable=False,
        server_default=CertificateStatus.VALID.value,
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    data_hash: Mapped[str] = mapped_column(Text, nullable=False)
```
`app/models/application.py` gains, mirroring `inspection` exactly:
```python
certificate: Mapped["Certificate | None"] = relationship(lazy="raise")
```
eager-loaded in `_scoped()` (`services/applications.py`) alongside the existing
`joinedload(Application.inspection)`.

## 4. Issuance flow

`app/services/certificates.py: issue(db, user, application_id, *, ip) -> Application`. Mirrors
`documents.py: upload()`'s lock ordering (expensive/external work outside any lock, then lock + verify
+ write):

1. `application = applications_service.load(db, user, application_id)` — scope 404, no lock yet.
2. `user.role != LM_OFFICER` → 403. `application.status != APPROVED` → **409**
   `"Application must be approved before a certificate can be issued"`. Fail fast before any expensive
   work.
3. Reserve `certificate_number` via `db.scalar(select(certificate_number_seq.next_value()))` — cheap,
   non-transactional; gaps are fine (same reasoning `instrument_uid`'s own comment already gives for
   its sequence).
4. Build the snapshot dict (§3.1) from the already-loaded `application` (instrument, organization,
   history). Compute `valid_from = today()` (reuse `core/clock.py`, spec 05's timezone-aware helper —
   never a bare `date.today()`), `valid_until = valid_from + relativedelta(years=CERTIFICATE_VALIDITY_YEARS)`.
   Compute `data_hash` (§3.2).
5. Generate the QR PNG (`segno.make(url).save(buf, kind="png", scale=…)`, encoding
   `f"{PUBLIC_BASE_URL}/verify/{certificate_number}"` — never localhost, same rule backend/CLAUDE.md's
   QR section already states) and render the PDF (ReportLab) embedding the QR, every snapshot field,
   the short `data_hash`, `valid_from`/`valid_until`, and the issuing officer's name. Content list only
   — exact visual layout is implementation discretion, the same latitude spec 06 gave the inspection
   flow's screen styling.
6. `storage.put(pdf_path, pdf_bytes, "application/pdf")` — **outside** any lock. On `StorageError` →
   **502** (`BadGateway`), mirrors `documents.upload()` exactly.
7. Re-load and lock the application row (`for_update=True`, `.execution_options(populate_existing=True)`).
   Re-check `status == APPROVED` — a concurrent double-click race guard: the loser gets the same 409 as
   step 2, and the PDF just uploaded is deleted best-effort
   (`applications_service.delete_objects_best_effort([pdf_path])`).
8. One transaction:
   - Insert the `Certificate` row.
   - `applications_service.apply_certificate_issued(db, application, user)` — **new, small function**:
     ```python
     def apply_certificate_issued(db: Session, application: Application, user: User) -> None:
         """Called only from services/certificates.py, inside its own transaction. The
         APPROVED -> CERTIFICATE_ISSUED edge is system-only (Edge(frozenset(), enabled=False))
         and never reachable through transition()/PATCH."""
         application.status = S.CERTIFICATE_ISSUED
         _add_history(db, application, user, S.APPROVED, S.CERTIFICATE_ISSUED, None)
         audit.log(
             db, actor=user, action="APPLICATION_STATUS_CHANGED", entity_type="application",
             entity_id=application.id, organization_id=application.organization_id,
             details={"from": "APPROVED", "to": "CERTIFICATE_ISSUED", "note": None}, ip=ip,
         )
     ```
     reusing the existing private `_add_history()` — keeps the application's timeline UI working
     uniformly with every other transition, and keeps the generic audit action consistent (§10 D6).
   - Write a `CERTIFICATE_ISSUED` audit row separately (`entity_type="certificate"`,
     `entity_id=certificate.id`, `details={"certificate_number", "valid_until", "data_hash"}`) —
     mirrors `transition()`'s own established pattern of a generic row plus a specific one
     (`INSPECTION_SCHEDULED`, `INSPECTION_STARTED` do the same for their transitions).
   - `db.commit()`.
9. On any exception from step 7 onward, `except BaseException: db.rollback();
   delete_objects_best_effort([pdf_path]); raise` — same shape as `documents.upload()`.

## 5. API

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| `POST` | `/api/applications/{id}/certificate` | in-scope `LM_OFFICER`, application `APPROVED` | `{}` → `ApplicationDetail` |
| `GET` | `/api/certificates/{id}` | scope + Reader | → `CertificateOut` |
| `GET` | `/api/certificates/{id}/pdf?disposition=inline\|attachment` | scope + Reader | → `{url, expires_in}` |

The `POST` returns `ApplicationDetail` (not `CertificateOut`) so it mirrors `PATCH .../status` and
`PATCH .../inspection`'s existing response shape — the frontend's `changeStatus()`-style
single-state-update pattern just works, no new response handling needed.

`GET /certificates/{id}/pdf` returns a **signed URL**, not raw bytes, despite the `/pdf` name (that
path was pre-reserved in backend/CLAUDE.md before this spec existed) — it behaves exactly like
`documents.py: signed_url()` / `GET /documents/{id}/url`. Documented explicitly here so an implementer
doesn't build a byte-streaming endpoint by mistake.

### Schemas (`app/schemas/certificate.py`)
```python
class CertificateOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    certificate_number: str
    status: CertificateStatus
    valid_from: date
    valid_until: date
    issued_at: datetime
    instrument_uid: str
    instrument_type: InstrumentType
    manufacturer: str
    model: str
    serial_number: str
    capacity: float
    capacity_unit: CapacityUnit
    organization_name: str
    qr_code_data_uri: str  # "data:image/png;base64,...", regenerated on every read — never stored

    @classmethod
    def from_model(cls, c: Certificate) -> Self:
        s = c.snapshot
        return cls(
            id=c.id, application_id=c.application_id, certificate_number=c.certificate_number,
            status=c.status, valid_from=c.valid_from, valid_until=c.valid_until,
            issued_at=c.created_at, instrument_uid=s["instrument_uid"],
            instrument_type=s["instrument_type"], manufacturer=s["manufacturer"], model=s["model"],
            serial_number=s["serial_number"], capacity=s["capacity"],
            capacity_unit=s["capacity_unit"], organization_name=s["organization_name"],
            qr_code_data_uri=qr_code_data_uri(c.certificate_number),
        )
```
`qr_code_data_uri()` (`app/pdf/certificate.py`) is called fresh on every read, from
`certificate_number` alone (deterministic, no randomness) — **never persisted**, consistent with
backend/CLAUDE.md's QR section: "The DB is the source of truth, never the PDF or QR." Regenerating a
small PNG on each `GET` is cheap; storing a derivable image would just be one more thing that could
drift from the truth.

`ApplicationDetail` (`app/schemas/application.py`) gains:
```python
certificate: CertificateOut | None
```
built the same way `inspection: InspectionOut | None` already is, from the eager-loaded
`a.certificate` — `/applications/[id]` never needs a second fetch to show the certificate summary.

### Behaviour rules
- `POST /applications/{id}/certificate`: out of scope → 404; wrong role → 403; status not `APPROVED` →
  409 (exact message in §4 step 2); success → 200 `ApplicationDetail` with
  `status: "CERTIFICATE_ISSUED"` and `certificate` populated.
- `GET /certificates/{id}` / `.../pdf`: out of scope → 404 (never 403, same rule as every other scoped
  read). No role restriction beyond scope — same Reader set as the application.
- `GET /certificates/{id}/pdf`: mirrors `documents`' `disposition` query param exactly —
  `inline` (default, no `download=`) vs `attachment` (`download=<sanitized certificate_number>.pdf`).
  Audited as `CERTIFICATE_URL_ISSUED` (mirrors `DOCUMENT_URL_ISSUED`), committed in the service (§
  "Audit-writing GETs commit in the service," backend/CLAUDE.md).

## 6. Backend implementation
```
app/pdf/__init__.py                empty (package marker — matches backend/CLAUDE.md's reserved layout)
app/pdf/certificate.py             qr_code_data_uri(url) [segno]; render(snapshot, ...) -> bytes [ReportLab]
app/models/certificate.py          Certificate, CertificateStatus
app/models/application.py          + certificate relationship
app/core/config.py                 + CERTIFICATE_VALIDITY_YEARS = 2  (ASSUMPTION — not a real Legal
                                    Metrology rule; flag for domain-expert correction)
app/schemas/certificate.py         CertificateOut
app/schemas/application.py         ApplicationDetail.certificate
app/services/scoping.py            + scope_certificates
app/services/applications.py       + apply_certificate_issued(); _scoped() eager-loads .certificate
app/services/certificates.py       new: issue(), get(), signed_url()  (mirrors documents.py's shape)
app/routers/applications.py        new: POST /{id}/certificate  (application-scoped action, same file
                                    as .../status and .../inspection, not routers/certificates.py)
app/routers/certificates.py        new: GET /{id}, GET /{id}/pdf
app/main.py                        register certificates router
requirements.txt                   + reportlab, + segno, + python-dateutil (relativedelta)
alembic/versions/0006_certificates.py
```
No change to `app/storage/` — the existing `Storage` protocol (`put`, `delete`, `signed_url`) and the
single global `SUPABASE_BUCKET` (already allowlisting `application/pdf`) are reused as-is (§10 D7). No
`create-bucket` CLI change.

## 7. Frontend implementation

| Route | Who | Content |
|---|---|---|
| `app/applications/[id]/page.tsx` (existing, extended) | in-scope `LM_OFFICER` | **Issue certificate** button while `APPROVED`; certificate summary + link once `CERTIFICATE_ISSUED` |
| `app/certificates/[id]/page.tsx` (new) | Business, officials, admins | Certificate details, QR image, View/Download PDF |

- **Issue certificate button:** shown when `application.status === "APPROVED"` and the caller is an
  officer (`isOfficer`, UX-only check — **not** driven by `allowed_actions`, since this edge is
  deliberately never enabled there, `roles=frozenset()`). This is the one documented exception to
  frontend/CLAUDE.md's "status-change buttons come only from `allowed_actions`" rule — noted explicitly
  in that file so it doesn't read as a bug later. No confirm dialog (§10 D1) — same "no dialog, direct
  transition" pattern `startInspection()` already uses. On success, `setState({kind: "ready", app:
  updated})` exactly like every other action on this page.
- **Certificate summary section:** once `application.status === "CERTIFICATE_ISSUED"` and
  `app.certificate` is present, show `certificate_number` and `valid_from`–`valid_until`, plus a
  **View certificate** link to `/certificates/{app.certificate.id}`.
- **`/certificates/[id]`:** fetches `GET /certificates/{id}` (`getCertificate()`, new `lib/api.ts`
  function); renders the QR directly from `qr_code_data_uri` (an `<img src="data:image/png;base64,...">`
  — no extra network round trip); **View**/**Download** buttons reuse the exact `onView`/`onDownload`
  signed-URL pattern already in `applications/[id]/page.tsx` (open a blank tab synchronously, then point
  it at the signed URL from `GET /certificates/{id}/pdf?disposition=inline`; `?disposition=attachment`
  + `window.location.assign()` for download). frontend/CLAUDE.md's Key screens table already names this
  route ("Business | Download PDF, show QR") — broadened here to every Reader role, matching how every
  other scoped page in the app already works (business + in-jurisdiction officials + admins).
- `lib/types.ts`: new `Certificate`/`CertificateOut` type (mirrors the schema above);
  `ApplicationDetail.certificate: Certificate | null`.
- `lib/api.ts`: `getCertificate(id)`; certificate signed-URL calls inline in the page component,
  mirroring `onView`/`onDownload`'s existing inline `api<{url, expires_in}>(...)` calls — no new
  wrapper function needed, same as documents.

## 8. Tests (backend)

New `tests/test_certificates.py`:
- **Issuance success**: `APPROVED` application, in-scope officer (not necessarily the one who
  approved) → 200, `status == "CERTIFICATE_ISSUED"`, `certificate_number` matches the documented
  pattern, `data_hash` matches the §3.2 formula recomputed from the response, one
  `APPLICATION_STATUS_CHANGED` audit row (`to: "CERTIFICATE_ISSUED"`) and one `CERTIFICATE_ISSUED`
  audit row. PDF fetchable via the signed URL (`GET /certificates/{id}/pdf` → `GET` the returned URL →
  200, `content-type: application/pdf`). Instrument's `locked_fields` is `[]` afterward (unlocked).
- **Wrong status**: every non-`APPROVED` status (`DRAFT`, `SUBMITTED`, `DOCUMENT_REVIEW`, `SCHEDULED`,
  `INSPECTION`, `REJECTED`) → 409 with the documented message; no `Certificate` row created.
- **Role/scope**: BUSINESS/admins/GATC → 403; out-of-jurisdiction officer → 404 — parametrized like
  spec 05 §11/spec 07's role coverage.
- **Double-issue race**: two concurrent `POST`s on the same `APPROVED` application (thread-based, same
  shape as `test_concurrent_transitions_one_wins`) — exactly one 200, the other 409; exactly one
  `Certificate` row exists afterward.
- **`GET /certificates/{id}` / `.../pdf` scope**: business owner, in-jurisdiction official, admin all
  succeed; a different org's business user and an out-of-jurisdiction officer → 404.
- `test_certificate_issued_never_via_patch` (existing, `tests/test_applications_transitions.py`) is
  unchanged and keeps passing — it tests the *generic* PATCH path, which must still never reach this
  status regardless of this step's new dedicated endpoint.

## 9. Deferred and recorded for later steps

- **Step 9:** the public verify page and endpoint (`GET /api/public/verify/{certificate_number}`,
  rate-limited), consuming the `certificate_number`/URL shape this step fixes.
- **Step 10:** `EXPIRED`/`REVOKED` transitions and the daily expiry job, reading `valid_until`.
- A revoke endpoint or admin action — not designed anywhere yet.
- Payments (root `CLAUDE.md`'s separate open decision) — untouched, never a gate on issuance.
- Re-issuing or regenerating a certificate's PDF (e.g. after a template change) — `pdf_path` is written
  once and never touched again in this step.

## 10. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | Issuance trigger | **Single-click "Issue certificate" button**, no confirm dialog — same pattern as "Start inspection." A dedicated `POST /api/applications/{id}/certificate`, not the generic status PATCH (which structurally can't reach this edge). |
| D2 | `qr_token` vs `certificate_number` in the QR/public URL | **`certificate_number` directly**, matching backend/CLAUDE.md's already-written QR section. No separate `qr_token` column — dropped as redundant. Enumerability of `LM-CERT-{year}-{seq}` is an accepted MVP tradeoff; `/public/verify` is already documented as rate-limited (step 9 enforces it). |
| D3 | Validity period | **2 years from issue date**, a flat `CERTIFICATE_VALIDITY_YEARS = 2` constant for every instrument type. **ASSUMPTION** — not a real Legal Metrology rule, flagged for domain-expert correction before any non-demo use. |
| D4 | QR image library | **`segno`** — lightweight, no Pillow dependency, outputs PNG bytes directly. Paired with **ReportLab** (already anticipated in backend/CLAUDE.md's structure) for the PDF. |
| D5 | Snapshot storage: JSONB blob, or relational rows (like spec 06's checklist items)? | **JSONB.** Unlike spec 06's checklist items (a list of independently-editable rows), a certificate's snapshot is one immutable bundle written once and always read whole — the opposite case, so the opposite storage shape is correct, not an inconsistency. |
| D6 | Audit rows on issuance | **Two**, mirroring `transition()`'s own established pattern (confirmed in the live code, not just documentation): the generic `APPLICATION_STATUS_CHANGED` (via the new `apply_certificate_issued()`) plus a specific `CERTIFICATE_ISSUED` row with certificate details — same shape as `INSPECTION_SCHEDULED`/`INSPECTION_STARTED` already do for their own transitions. |
| D7 | Storage: new `certificates` bucket, or reuse `documents`? | **Reuse the existing single `SUPABASE_BUCKET`** (already allowlists `application/pdf`), storage path `certificates/{id}.pdf` parallel to documents' `applications/{application_id}/{document_id}.{ext}`. No new bucket, no new `Storage` method, no `create-bucket` CLI change — simplest MVP choice. |

## 11. Acceptance criteria

- [x] `0006_certificates` round-trips locally (`upgrade`, `downgrade -1`, `upgrade`), `alembic check`
  clean, and applies to Supabase.
- [x] From a live `APPROVED` demo application, **Issue certificate** produces a real
  `certificate_number`, a fetchable PDF containing a QR that decodes to
  `{PUBLIC_BASE_URL}/verify/{certificate_number}`, and moves the application to
  `CERTIFICATE_ISSUED`.
- [x] The instrument's `locked_fields` is empty once the certificate is issued (identity/location
  fields both unlock, per the already-existing `LOCATION_LOCK_STATUSES`/`TERMINAL_STATUSES` rules —
  no change needed there, just confirmed).
- [x] Issuing twice (or on a non-`APPROVED` application) is refused with the documented 409; no
  orphaned `Certificate` row or PDF object from a race or a rejected attempt.
- [x] `GET /certificates/{id}` and `.../pdf` enforce the same org-isolation/jurisdiction rules as every
  other scoped read (404, never 403, when out of scope).
- [x] `/certificates/[id]` renders the QR and lets every Reader role View/Download the PDF.
- [x] `ruff`, `eslint`, `tsc` and the build are clean; backend test suite green including
  `tests/test_certificates.py`.
- [x] `backend/CLAUDE.md` updated: Data model section's `certificates` line replaced with the real
  columns; API block's `GET /api/certificates/{id}`/`.../pdf` lines confirmed and `POST
  /api/applications/{id}/certificate` added; Application status flow section gains a short "Certificate
  issuance (step 8)" subsection (mirroring Scheduling/Field inspection/Approve-Reject); new audit
  actions (`CERTIFICATE_ISSUED`, `CERTIFICATE_URL_ISSUED`); migrations table gets `0006`.
  `frontend/CLAUDE.md` updated: Key screens table's `/certificates/[id]` row filled in; the
  `allowed_actions` rule gains a one-line note naming this step's button as the sole exception. Root
  `CLAUDE.md` step 8 marked ✅ linking to this spec.

## 12. Verification record

**Two corrections to the spec found during implementation**, beyond the two already known before
coding started (stdlib `_add_years()` instead of `python-dateutil`; `CERTIFICATE_VALIDITY_YEARS` as a
`Settings` field, not a bare constant):
1. §4's re-lock query needed `.execution_options(populate_existing=True)`, which the spec's snippet
   omitted. Without it, a concurrent double-issue race silently let both requests insert a
   `Certificate` row (the identity map returned the stale pre-lock `APPROVED` status to the second
   caller) — caught by `test_issue_certificate_double_issue_race`, the exact pitfall
   `backend/CLAUDE.md`'s "Row locks re-read" rule already warns about.
2. §2/§5 assumed a scope-then-role evaluation inside `services/certificates.py: issue()`. In practice
   the router's `Officer` dependency (`require_roles(Role.LM_OFFICER)`) enforces role **before** the
   handler body runs at all, so every non-officer gets a uniform 403 regardless of scope — the same
   behavior every other single-role-gated endpoint in this codebase already has (e.g.
   `reschedule_inspection`). The service-level role check stays (defense in depth for direct calls,
   now ordered after `load()`), but it's dead code on the HTTP path; `test_issue_certificate_role_and_scope`
   documents the real behavior instead of the spec's assumed one.

Backend (`pytest`, local `lm_dev`/`lm_test`): full suite green — **373 tests**, including 5 new in
`tests/test_certificates.py` (issuance success with `data_hash` recomputed and matched against the
audit row; every non-`APPROVED` status incl. `DRAFT`'s 404; role/scope; a threaded double-issue race;
`GET /certificates/{id}`/`.../pdf` scope for business/official/admin vs. out-of-org/out-of-jurisdiction)
plus `conftest.py`'s `make_application` fixture extended to reach `status="APPROVED"` (completes the
checklist and submits via the public `inspections_service` functions, then approves). `ruff
check`/`ruff format --check` clean. Migration round-tripped locally and applied cleanly to Supabase
(`alembic check` clean after).

Frontend (`tsc --noEmit`, `eslint`, `next build`): clean, no new suppressions. `/certificates/[id]` is
listed as a dynamic route in the build output.

Manual, in Chrome against local dev servers (`lm_dev`, `STORAGE_BACKEND=memory`): as
`officer.dhn@lm.demo`, opened the live `APPROVED` ABC Traders demo application
(`APP-2026-000002`/`LM-JH-DHN-000002`), clicked **Issue certificate** — status became "Certificate
issued", a new section showed `LM-CERT-2026-000001`, "Valid 30/09/2026 – 30/09/2028" (confirms the
2-year default). **View certificate** opened `/certificates/{id}`, showing a real, visually-scannable
QR code and the certificate details; **View PDF** correctly requested a signed URL and navigated to it
(the actual byte-serving only works against real Supabase Storage, not the `memory` backend used
locally — verified instead at the backend test level: the stored object starts with `%PDF` and is typed
`application/pdf`). Re-opening the instrument's detail page confirmed "Application in progress" was
gone — fully unlocked, as expected for a terminal status.
