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

- The seed refuses to run when `ENV=production` unless `--force-demo` is passed.
- **Production shortcut:** delete these accounts after the hackathon.
