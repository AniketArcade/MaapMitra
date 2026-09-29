# Spec 01 — Login + RBAC (rev 2)

**Status:** Ready for Claude Code (all open decisions resolved, see §11)
**Build order:** Step 1 of 10
**Depends on:** backend scaffold (`chore/scaffold`)

## 1. Goal

Businesses can register, log in, log out and stay logged in via silent token refresh. The backend decides what each role may do. SUPER_ADMIN can create official accounts.

Every later step builds on three things from this spec:
- the `get_current_user` dependency
- the `require_roles(...)` dependency
- the `organization_id` scoping rule

### Out of scope (Step 1)
- Password reset and email verification (needs Resend; Good-to-Have)
- 2FA, OAuth, SSO, Supabase Auth (forbidden by the architecture rules)
- **`GET /users`, `PATCH /users/{id}`, jurisdiction-scoped user management** (deferred to the admin UI step, see §12)
- Creating GATC users or orgs (deferred until the GATC step; seed if needed earlier)
- Admin UI for audit logs (step 10)

---

## 2. Roles

`SUPER_ADMIN > STATE_ADMIN > DISTRICT_ADMIN > LM_OFFICER > GATC > BUSINESS > PUBLIC`

**Rule: the hierarchy is only used for managing users. It does not grant permissions.**
A higher role does **not** inherit a lower role's abilities. Every endpoint lists the exact roles it allows.

| Role | `organization_id` | Jurisdiction | Created by (Step 1) |
|---|---|---|---|
| `SUPER_ADMIN` | null | none (all) | CLI only |
| `STATE_ADMIN` | null | `state_code` required | SUPER_ADMIN via `POST /users` (or seed) |
| `DISTRICT_ADMIN` | null | `state_code` + `district_code` required | SUPER_ADMIN via `POST /users` (or seed) |
| `LM_OFFICER` | null | `state_code` + `district_code` required | SUPER_ADMIN via `POST /users` (or seed) |
| `GATC` | required (GATC org) | none | seed only in Step 1 |
| `BUSINESS` | required (business org) | inherited from its org | self-registration |
| `PUBLIC` | — | — | not stored. Unauthenticated = PUBLIC |

> **ASSUMPTION:** officers are scoped to one district and admins to a state or district. This is a product assumption, not a legal fact. Real Legal Metrology jurisdiction rules are unverified.

Nobody can change their own role or deactivate themselves (enforced when `PATCH /users` ships).

---

## 3. Data model (Alembic migration `0001_auth`)

### `organizations`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `type` | enum `org_type`: `BUSINESS`, `GATC` | |
| `name` | text, not null | e.g. "ABC Traders" |
| `registration_number` | text, nullable | **ASSUMPTION:** generic business ID (GSTIN or similar) |
| `address` | text, nullable | |
| `state_code` | text, **not null** | `^[A-Z]{2}$`, e.g. `JH` (feeds `instrument_uid`) |
| `district_code` | text, **not null** | `^[A-Z]{2,4}$`, e.g. `DHN` |
| `created_at`, `updated_at` | timestamptz | server defaults |

### `users`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `email` | text, **unique index**, stored lowercased | lowercased by a Pydantic validator before any query |
| `password_hash` | text | Argon2id |
| `full_name` | text | |
| `phone` | text, nullable | |
| `role` | enum `user_role` (6 stored roles) | |
| `organization_id` | UUID FK → organizations, nullable | see constraints |
| `state_code`, `district_code` | text, nullable | jurisdiction for officials |
| `is_active` | bool, default true | |
| `last_login_at` | timestamptz, nullable | |
| `created_at`, `updated_at` | timestamptz | |

**DB check constraints:**
1. `(role IN ('BUSINESS','GATC')) = (organization_id IS NOT NULL)`
2. `role <> 'STATE_ADMIN' OR state_code IS NOT NULL`
3. `role NOT IN ('DISTRICT_ADMIN','LM_OFFICER') OR (state_code IS NOT NULL AND district_code IS NOT NULL)`

### `refresh_tokens`
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users, indexed | |
| `token_hash` | text, unique | SHA-256 of the raw token. Raw token never stored |
| `expires_at` | timestamptz | |
| `revoked_at` | timestamptz, nullable | |
| `created_at` | timestamptz | |

### `audit_logs` (**append-only**: no update or delete code paths)
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `actor_user_id` | UUID FK → users, nullable | null for anonymous events (failed login) |
| `action` | text | `USER_REGISTERED`, `LOGIN_SUCCEEDED`, `LOGIN_FAILED`, `LOGOUT`, `USER_CREATED`, `REFRESH_REUSE_DETECTED` |
| `entity_type`, `entity_id` | text, UUID nullable | |
| `organization_id` | UUID, nullable | |
| `details` | JSONB | **never** passwords or tokens |
| `ip_address` | text, nullable | from `get_client_ip` (§6) |
| `created_at` | timestamptz, indexed | |

---

## 4. Tokens and cookies

| | Access token | Refresh token |
|---|---|---|
| Format | JWT, HS256, `JWT_SECRET` | opaque `secrets.token_urlsafe(48)` |
| TTL | `JWT_ACCESS_TTL_MIN` (15 min) | `JWT_REFRESH_TTL_DAYS` (7 days) |
| Frontend storage | memory only | httpOnly cookie |
| Claims / storage | `sub`, `role`, `org_id` (or null), `type:"access"`, `iat`, `exp`, `jti` | row in `refresh_tokens` (hash only) |

**Decode rules:** `jwt.decode(..., algorithms=["HS256"], options={"require": ["exp","sub","type"]})`. Reject if `type != "access"`.

### Cookies (set on register/login/refresh; cleared on logout and on refresh failure)
| cookie | attributes | purpose |
|---|---|---|
| `lm_refresh` | `HttpOnly`, `Secure` (except localhost), `SameSite=Lax`, `Path=/api/auth`, max-age = refresh TTL | the refresh token |
| `lm_session=1` | `HttpOnly`, `Secure` (except localhost), `SameSite=Lax`, `Path=/`, max-age = refresh TTL | presence flag only, used by `proxy.ts`. Carries no secret |

Why two: `lm_refresh` is only sent to `/api/auth/*`, so `proxy.ts` on `/dashboard` could never see it.

### Rotation and reuse detection
Every `/refresh` revokes the presented row and issues a new one. When a **revoked** token is presented:
- `revoked_at` less than **10 seconds** ago → treat as a race loser: return `401`, **do not** revoke the family, **do not** clear cookies (the winner already set fresh ones).
- otherwise → revoke **all** of that user's refresh tokens, write `REFRESH_REUSE_DETECTED`, clear both cookies, return `401`.

An unknown, expired or malformed token → `401`, clear both cookies.

### Claims are a hint, not the authority
`get_current_user` loads the user from the DB on every request and rejects the token if the user is inactive, or their role or `organization_id` differs from the claims. Services still re-check ownership, as `backend/CLAUDE.md` requires.

---

## 5. API

Base `/api`. Errors use FastAPI's default `{"detail": ...}`.

| Method | Path | Allowed | Body → Response |
|---|---|---|---|
| POST | `/auth/register` | public (rate-limited) | `RegisterRequest` → `201 AuthResponse` + cookies |
| POST | `/auth/login` | public (rate-limited) | `LoginRequest` → `200 AuthResponse` + cookies |
| POST | `/auth/refresh` | `lm_refresh` cookie | — → `200 AuthResponse` + rotated cookies |
| POST | `/auth/logout` | none required | — → `204` always, cookies cleared, row revoked if present |
| GET | `/auth/me` | any logged-in user | → `UserOut` |
| POST | `/users` | SUPER_ADMIN | `UserCreate` → `201 UserOut` |

### Schemas
```python
class RegisterRequest(BaseModel):
    organization_name: str            # 2..200 chars
    registration_number: str | None = None
    address: str | None = None
    state_code: str                   # ^[A-Z]{2}$
    district_code: str                # ^[A-Z]{2,4}$
    full_name: str
    email: EmailStr                   # lowercased by validator
    phone: str | None = None
    password: SecretStr               # 8..128 chars (MVP policy)

class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr               # max 128 chars

class UserOut(BaseModel):
    id: UUID; email: str; full_name: str; role: Role
    organization_id: UUID | None; organization_name: str | None
    state_code: str | None; district_code: str | None; is_active: bool

class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int                   # seconds
    user: UserOut

class UserCreate(BaseModel):          # officials only
    email: EmailStr; full_name: str; phone: str | None = None
    role: Literal["STATE_ADMIN", "DISTRICT_ADMIN", "LM_OFFICER"]
    password: SecretStr               # 8..128; admin sets initial password (MVP)
    state_code: str | None = None; district_code: str | None = None
    # required codes per role: see DB constraints in §3
```
`UserCreate` rejects `GATC`, `BUSINESS` and `SUPER_ADMIN` with `422`.

### Behaviour rules
- **Register:** creates one `organizations` row (BUSINESS) and one `users` row (role BUSINESS) in **one transaction**, writes `USER_REGISTERED`, returns tokens. The client cannot choose a role; extra fields are ignored.
- **Duplicate email:** unique index is the source of truth. Catch `IntegrityError` and return `409 "Email already registered"` (also covers the race). This reveals that the account exists. Accepted for MVP, flagged for production.
- **Login failure:** always `401 "Invalid email or password"` for unknown email, wrong password or inactive user. For an unknown email, still verify against a dummy Argon2 hash so timing doesn't leak existence.
- **Login success:** update `last_login_at`, write `LOGIN_SUCCEEDED`, run `needs_rehash`. **Failure** writes `LOGIN_FAILED` with the attempted email in `details`, never the password.
- **Commit-then-raise (security writes must survive the error):** any path that raises after a security-relevant write (`LOGIN_FAILED` audit row, family revocation, `REFRESH_REUSE_DETECTED`) must `db.commit()` **before** raising the HTTP error. Otherwise the request rollback erases the evidence.
- **Logout:** idempotent. Always clear both cookies and return `204`, even if the cookie is missing, expired or unknown.
- **Inactive user:** refresh and every authenticated route return `401`.
- **Wrong role:** `403 "Insufficient permissions"`. (Org-owned resources in later steps return `404` for other orgs.)

---

## 6. Rate limiting and client IP

| Endpoint | Limits |
|---|---|
| `POST /auth/login` | 5/min **per email** AND 20/min **per IP** |
| `POST /auth/register` | 10/hour per IP |

Over the limit → `429`. Implementation:
- Per-IP limits: `slowapi` decorators, in-memory storage (no Redis).
- Per-email limit: small in-memory sliding-window counter in `services/auth.py` (slowapi can't key on the request body). Key on the lowercased email.

**Client IP behind the proxy:** the backend sits behind the Vercel rewrite and Render's proxy, so `request.client.host` is a proxy address. Implement `get_client_ip(request)` in `core/deps.py`, used for **both** rate-limit keys and `audit_logs.ip_address`:
- read the forwarded-for value set by the trusted proxy chain
- configure uvicorn `--proxy-headers` and `--forwarded-allow-ips` for Render
- **Verify on first deploy:** log the resolved IP from two different networks and confirm they differ.

**Production shortcut, flagged:** limits reset on restart and aren't shared across instances.

---

## 7. Backend implementation

```
app/core/security.py     hash_password, verify_password (argon2-cffi PasswordHasher, needs_rehash)
                         create_access_token, decode_access_token (PyJWT, pinned alg)
                         new_refresh_token, hash_token
app/core/deps.py         get_current_user   → loads User; 401 on bad/expired token, inactive user, or role/org mismatch
                         require_roles(*roles) → dependency factory; 403 otherwise
                         get_client_ip
                         CurrentUser = Annotated[User, Depends(get_current_user)]
app/core/roles.py        Role enum, ROLE_RANK dict (used by later user-management step)
app/models/{organization,user,refresh_token,audit_log}.py
app/schemas/{auth,user}.py
app/services/auth.py     register, login, refresh, logout (token + audit logic; commit-then-raise)
app/services/users.py    create_user (SUPER_ADMIN only)
app/services/audit.py    log(db, actor, action, entity, details, ip), same transaction as caller
app/routers/{auth,users}.py   thin handlers
app/cli.py               python -m app.cli create-superadmin --email ... (prompts for password)
```

**Usage pattern for all later endpoints:**
```python
@router.post("/instruments", status_code=201)
def create_instrument(
    body: InstrumentCreate,
    user: User = Depends(require_roles(Role.BUSINESS)),
    db: Session = Depends(get_db),
) -> InstrumentOut:
    return instruments_service.create(db, user, body)   # service filters by user.organization_id
```

**New dependencies:** `argon2-cffi`, `PyJWT`, `email-validator`, `slowapi`.

---

## 8. Frontend implementation

| File | Purpose |
|---|---|
| `app/(auth)/login/page.tsx` | email + password form (shadcn), inline error on 401/429 |
| `app/(auth)/register/page.tsx` | org fields (incl. required state and district codes) + user fields |
| `app/dashboard/page.tsx` | role-aware placeholder ("Welcome, {name} ({role})") |
| `lib/auth.ts` | in-memory access token, `AuthProvider`, `useAuth()` → `{user, login, logout, status}` |
| `lib/api.ts` | typed client; attaches `Authorization: Bearer`; refresh handling below |
| `lib/types.ts` | `Role`, `User`, `AuthResponse` mirroring backend |
| `proxy.ts` | coarse guard: no `lm_session` cookie on a private route → redirect to `/login`. `/verify/*`, `/login`, `/register` stay public |
| `next.config.ts` | `rewrites`: `/api/:path*` → `${API_ORIGIN}/api/:path*` |

**Refresh handling (must survive races):**
- One **module-level** single-flight promise for `/auth/refresh` (a component-level ref breaks under React StrictMode's double mount and across concurrent callers).
- On a `401` from a protected call: await the shared refresh, then retry once; if it still fails, clear state and redirect to `/login`.
- If `/auth/refresh` itself returns `401` because it lost a race, retry `/auth/refresh` once (the winner already rotated the cookie), then give up.
- On page load, call `/auth/refresh` to restore the session (access token is never persisted).

**Other rules:**
- Next.js 16 renamed `middleware.ts` to `proxy.ts`.
- `proxy.ts` is UX only. The backend enforces everything.
- Role checks in the UI only hide navigation. A 403 shows an explicit "You don't have access" state.
- Env: `API_ORIGIN` (server-side, used by the rewrite) replaces `NEXT_PUBLIC_API_URL`.
- **Test early:** a multi-MB upload through the rewrite (needed in step 3).

---

## 9. Tests (backend, `pytest`, local Postgres 16 via Docker)

Reset the rate limiter between tests, or the 429 test makes others flaky.

**Auth**
- Register creates org + user in one transaction; role is always BUSINESS even if the client sends `role`. Missing or badly formatted `state_code` / `district_code` → 422.
- Duplicate email → 409, including two concurrent registrations (one wins, one gets 409).
- Login OK with correct credentials; the same 401 message for wrong password, unknown email and inactive user.
- Access token carries `sub`, `role`, `org_id`. Expired token, wrong secret, `alg: none`, tampered token, and a refresh token used as an access token all → 401.
- Token with a stale role or org (user changed in DB) → 401.
- Refresh rotates; the old token then fails.
- **Reuse detection:** a revoked token presented after 10s → all the user's tokens revoked, `REFRESH_REUSE_DETECTED` row exists **after** the 401 response.
- **Race:** two concurrent `/refresh` calls with the same token → one 200, one 401, and the user's tokens are **not** all revoked.
- Logout revokes the row and clears both cookies; calling it with no cookie still returns 204.
- Password hash is Argon2id. No response or log line contains a password or token.
- 6th login attempt for one email within a minute → 429. The 21st from one IP → 429.
- **Security writes survive errors:** after a failed login, the `LOGIN_FAILED` row exists (commit-then-raise).

**RBAC**
- `require_roles` returns 403 for each disallowed role, parameterized over all six roles.
- `POST /users`: only SUPER_ADMIN succeeds; every other role → 403. Creating `GATC`, `BUSINESS` or `SUPER_ADMIN` → 422. Missing state or district code for the role → 422.
- A user set inactive directly in the DB gets 401 on their next request, even with a still-valid access token.

**Audit**
- Register, login success, login failure, logout and user create each write exactly one `audit_logs` row. `audit_logs.ip_address` is populated from `get_client_ip`.

---

## 10. Demo seed users

Seed inserts these directly (no API needed). **Seed changes need approval, per CLAUDE.md.**

| Email | Role | Scope |
|---|---|---|
| `admin@lm.demo` | SUPER_ADMIN | — |
| `state.jh@lm.demo` | STATE_ADMIN | JH |
| `district.dhn@lm.demo` | DISTRICT_ADMIN | JH / DHN |
| `officer.dhn@lm.demo` | LM_OFFICER | JH / DHN |
| `owner@abctraders.demo` | BUSINESS | ABC Traders (JH / DHN) |
| `owner@othertraders.demo` | BUSINESS | Other Traders. Used to demo and test org isolation |

- The seed **refuses to run when `ENV=production`** unless `--force-demo` is passed.
- The shared demo password is documented in the seed README only. **Production shortcut, flagged:** remove these accounts after the hackathon.

---

## 11. Decisions (resolved)

| # | Decision | Resolution |
|---|---|---|
| D1 | `refresh_tokens` table | **Yes.** Add it to the table list in `backend/CLAUDE.md` |
| D2 | Browser → API path | **Next.js rewrite proxy**, so the refresh cookie is first-party. `API_ORIGIN` replaces `NEXT_PUBLIC_API_URL` |
| D3 | Rate limiting | **`slowapi` in memory** + in-memory per-email counter |
| D4 | Test database | **Local Postgres 16 via Docker.** Second Supabase project only if Docker is unavailable |
| D5 | Official accounts' first password | **Admin sets it** (MVP) |
| D6 | Scope | **Step 1 ships `POST /users` for SUPER_ADMIN only.** `GET/PATCH /users` deferred (§12) |
| D8 | `state_code` / `district_code` | **Required** at business registration with format validation |

## 12. Deferred to the admin UI step

Record these so they aren't lost:
- `GET /users` (paginated: `page`, `page_size` default 20, max 100; `Page[T]` shape) and `PATCH /users/{id}`.
- `can_manage(actor, target_role, target_scope)`: target's current and new role rank strictly below the actor's, and target is in the actor's jurisdiction. STATE_ADMIN matches `state_code`; DISTRICT_ADMIN matches both codes.
- `effective_scope(user)`: an official's own scope; for BUSINESS and GATC, **the org's** scope (otherwise state and district admins can never see business users).
- On PATCH, the **new** `state_code` / `district_code` must also fall inside the caller's jurisdiction (else a district admin could move an officer out of their district).
- Deactivating a user revokes all their refresh tokens.
- Users cannot change their own role or deactivate themselves.
- GATC org and user creation.

---

## 13. Acceptance criteria

- [ ] `alembic upgrade head` creates the 4 tables on Supabase. `alembic downgrade -1` removes them.
- [ ] A business can register, log in, reload the page and stay logged in, then log out. Two open tabs do not log each other out.
- [ ] `officer.dhn@lm.demo` can log in and sees an officer dashboard placeholder.
- [ ] A business user calling `POST /api/users` gets 403.
- [ ] All tests in §9 pass. `ruff check` is clean.
- [ ] Deployed check: `get_client_ip` resolves different IPs from two different networks.
- [ ] `backend/CLAUDE.md` updated: `refresh_tokens` table, both cookies, `/auth` and `/users` endpoints, trusted-proxy note, CORS note (browser calls go through the rewrite).
- [ ] `frontend/CLAUDE.md` updated: `proxy.ts` (not `middleware.ts`), rewrite + `API_ORIGIN` env, the `lm_session` cookie, single-flight refresh rule.