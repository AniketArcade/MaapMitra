# Demo seed data

Creates the demo accounts from `docs/specs/01-login-rbac.md` §10. Safe to re-run: existing
emails and organizations are skipped.

```bash
cd backend && source .venv/bin/activate
python -m app.seed --password 'LmDemo@2026'
```

**Shared demo password:** `LmDemo@2026`

| Email | Role | Scope |
|---|---|---|
| `admin@lm.demo` | SUPER_ADMIN | — |
| `state.jh@lm.demo` | STATE_ADMIN | JH |
| `district.dhn@lm.demo` | DISTRICT_ADMIN | JH / DHN |
| `officer.dhn@lm.demo` | LM_OFFICER | JH / DHN |
| `owner@abctraders.demo` | BUSINESS | ABC Traders (JH / DHN) |
| `owner@othertraders.demo` | BUSINESS | Other Traders (JH / DHN), for org-isolation demos |

Demo instrument (for the org-isolation demo): Other Traders owns a weighing scale, serial
`OTH-0001` (30 kg, JH / DHN). ABC Traders must **not** be able to see it. `XYZ12345` is
**not** seeded: ABC Traders registers it live in the demo.

Optional, before a demo: make the next UID a nice number (UIDs are never credentials).

```sql
ALTER SEQUENCE instrument_uid_seq RESTART WITH 123;  -- next UID: LM-JH-DHN-000123
```

Demo application: a **SUBMITTED** verification application for `OTH-0001` with two generated
documents (a one-page PDF invoice and a small PNG), so the officer has a queue item on first login.
It needs Supabase Storage configured (`STORAGE_BACKEND=supabase` with a real key) and the
bucket created (`python -m app.cli create-bucket`). ABC Traders' application is **not** seeded.

- The seed refuses to run when `ENV=production` unless `--force-demo` is passed.
- **Production shortcut:** delete these accounts after the hackathon.
