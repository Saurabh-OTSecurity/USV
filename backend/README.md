# Tribastion Site USV — Backend (Phase 0, Story Points 1-5)

## Project purpose

Tribastion is an OT cybersecurity platform ecosystem. The Site USV (Unified
Site View) is a site-level component of that platform: it will eventually
receive OT asset information from a pluggable source (Tribot, Claroty, or
Nozomi — one choice per site), receive security alerts from Wazuh (USV's
own fixed, internal-only SIEM engine, never a customer choice), integrate
with the standalone Incident Response module, and communicate centrally
with the ECC module (USV is the sole site component permitted to connect
to ECC).

**Phase 0** builds the foundation those future integrations sit on top of:
the database schema, authentication/RBAC, and read APIs for the core
resources. It does **not** implement any of the actual external
integrations (Tribot/Claroty/Nozomi/Wazuh/IR/ECC connectivity), asset or
vulnerability data, alerting, or the frontend beyond what Story Points 6-7
add. As of Story Point 5, the backend is feature-complete for Phase 0.

## Architecture summary

Layered: **API route → service → repository → SQLAlchemy → PostgreSQL**.
See `ARCHITECTURE.md` for the full layering diagram plus the rationale
behind the password hashing algorithm, the token mechanism, and the
logout limitation.

## Prerequisites

- Python 3.11+
- PostgreSQL 16+, reachable and running (see **Database setup** below)

## Installation

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then edit with real values — see Environment variables below
```

`.env` is git-ignored and must never be committed.

## Database setup

Point `.env` at any standard, already-running PostgreSQL 16+ server via
the `DATABASE_*` variables (see **Environment variables** below).

If you don't have PostgreSQL installed and just want a disposable local
instance for development:

```
pip install pgserver
python scripts/dev_postgres.py
```

This runs real PostgreSQL binaries against `backend/.devdb/` (git-ignored)
and writes the resulting connection details to `.env`. It's a dev
convenience only — the application always talks to PostgreSQL purely
through the `DATABASE_*` environment variables, exactly as it would
against any standard PostgreSQL server. See **Troubleshooting** below for
a caveat about this specific package.

### Migrations

```
.venv\Scripts\python -m alembic upgrade head
```

Five migrations, in order: extensions (pgcrypto) → site + usv →
integration + sync_state → usv_user → audit_log.

### Seed data

```
.venv\Scripts\python -m app.db.seed
```

Creates one site (`SITE-001`), one USV instance (`USV-001`), seven
integration configuration records, and six users — one per role:

| username        | role                | password (dev only)      |
|------------------|--------------------|---------------------------|
| platform.admin   | usv_platform_admin | DevOnly!PlatformAdmin1    |
| site.admin       | usv_site_admin     | DevOnly!SiteAdmin1        |
| l2.analyst       | usv_l2_analyst     | DevOnly!L2Analyst1        |
| l1.operator      | usv_l1_operator    | DevOnly!L1Operator1       |
| auditor.user     | usv_auditor        | DevOnly!Auditor1          |
| viewer.user      | usv_viewer         | DevOnly!Viewer1           |

**These passwords are fictional development fixtures only.** They are
never suitable for staging or production. Passwords are stored as bcrypt
hashes — never plaintext, never logged.

## Running the API

```
.venv\Scripts\python -m uvicorn app.main:app --host %APP_HOST% --port %APP_PORT% --reload
```

- `GET /health` — unauthenticated, reports `healthy`/`degraded` based on
  database connectivity.
- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`
  — see `ARCHITECTURE.md` for the logout limitation (client-side token
  discard only; no server-side revocation in this phase).
- `GET /api/v1/site`, `/api/v1/usv`, `/api/v1/integrations` (list + detail)
  — read-only, any authenticated role.
- `GET`/`POST /api/v1/users` — `usv_platform_admin` only.

CORS is configured explicitly via `CORS_ALLOWED_ORIGINS`. It never falls
back to a wildcard origin.

## API documentation

- `GET /docs` — interactive Swagger UI.
- `GET /openapi.json` — raw OpenAPI schema.

**These are unauthenticated in local development by design.** Any
non-development deployment (staging/production) must put `/docs` and
`/openapi.json` behind authentication (e.g. only reachable by an
authenticated `usv_platform_admin`, or disabled entirely) before exposing
the service outside a trusted development network — this is not enforced
by the application itself in this phase.

Every endpoint's required role is documented in its OpenAPI tag/summary in
`/docs`, and summarized here for convenience:

| Endpoint                        | Method | Required role                    |
|----------------------------------|--------|-----------------------------------|
| `/health`                        | GET    | none (unauthenticated)            |
| `/api/v1/auth/login`             | POST   | none (unauthenticated)            |
| `/api/v1/auth/me`                | GET    | any authenticated role            |
| `/api/v1/auth/logout`            | POST   | any authenticated role            |
| `/api/v1/site`                   | GET    | any authenticated role            |
| `/api/v1/site/{site_id}`         | GET    | any authenticated role            |
| `/api/v1/usv`                    | GET    | any authenticated role            |
| `/api/v1/usv/{usv_id}`           | GET    | any authenticated role            |
| `/api/v1/integrations`           | GET    | any authenticated role            |
| `/api/v1/integrations/{id}`      | GET    | any authenticated role            |
| `/api/v1/users`                  | GET    | `usv_platform_admin` only         |
| `/api/v1/users`                  | POST   | `usv_platform_admin` only         |

## Authentication / RBAC model

Bearer JWT issued by `POST /api/v1/auth/login`, validated on every
protected request by `get_current_user` (`app/core/rbac.py`), which also
re-checks `usv_user.status == 'active'` against the database on every
request. Role checks use `require_role(*allowed_roles)`, built on the same
six role constants used everywhere else in the codebase:

| Role                  | Intended capability |
|------------------------|---------------------|
| `usv_platform_admin`   | Platform configuration, all sites, user/role management, audit review. Sole role permitted to reach user-management endpoints (built in Story Point 4) and any future dashboard/graphics customization. |
| `usv_site_admin`       | Site-level configuration and user access within assigned site. |
| `usv_l2_analyst`       | Review/triage future SIEM alerts, assign/close future workflow objects. |
| `usv_l1_operator`      | View operational screens, acknowledge permitted events. |
| `usv_auditor`          | Read-only access to audit records and permitted site evidence. |
| `usv_viewer`           | Read-only operational dashboards within assigned site scope. |

Only `usv_platform_admin` currently has any role-gated endpoint
(`/api/v1/users`); the other five roles are equally able to read
site/usv/integration data and their own profile in this phase — finer
per-role restrictions on those resources are future work, not part of
Phase 0.

## Environment variables

| Variable                     | Purpose                                              | Example (dev)                  |
|-------------------------------|-------------------------------------------------------|----------------------------------|
| `DATABASE_HOST`               | PostgreSQL host                                       | `localhost`                      |
| `DATABASE_PORT`               | PostgreSQL port                                       | `5432`                           |
| `DATABASE_NAME`               | PostgreSQL database name                              | `usv`                            |
| `DATABASE_USER`               | PostgreSQL user                                       | `usv_app`                        |
| `DATABASE_PASSWORD`           | PostgreSQL password                                   | *(secret, never commit)*         |
| `APP_ENV`                     | `development` enables verbose error messages          | `development`                    |
| `AUTH_SECRET_KEY`             | HMAC secret for signing/verifying JWTs                | *(secret, never commit)*         |
| `AUTH_TOKEN_EXPIRY_MINUTES`   | JWT lifetime in minutes                               | `30`                              |
| `APP_HOST`                    | Host uvicorn binds to                                 | `127.0.0.1`                      |
| `APP_PORT`                    | Port uvicorn binds to                                 | `8000`                           |
| `CORS_ALLOWED_ORIGINS`        | Comma-separated list of allowed CORS origins          | `http://localhost:4200`          |

`APP_ENV` other than `development` (e.g. `staging`, `production`)
suppresses exception detail in 500 responses — see the unhandled
exception handler in `app/main.py`.

## Tests

```
.venv\Scripts\python -m pytest app/tests/ -v
```

All nine test files run together in one session (87 tests as of Story
Point 4): `test_database.py`, `test_security.py`, `test_rbac.py`,
`test_health.py`, `test_auth.py`, `test_site.py`, `test_usv.py`,
`test_integrations.py`, `test_users.py`. Verified stable under reordering
and repeated runs — no test-isolation issues found.

## Troubleshooting

Issues actually hit while building this backend, and how they were
resolved:

- **PostgreSQL installer download blocked / 403 Forbidden** (via
  `winget install PostgreSQL.PostgreSQL.16`, host
  `get.enterprisedb.com`): some restricted networks block that specific
  CDN. Try Chocolatey (`choco install postgresql16`) instead, or download
  the installer from `postgresql.org` on an unrestricted machine.
- **Chocolatey fails with a NuGet lock-file error when not run
  elevated**: `choco install` needs an elevated (Run as Administrator)
  shell to write to `C:\ProgramData\chocolatey`. Either elevate, or
  install PostgreSQL to a user-writable location by another method.
- **`CREATE EXTENSION pgcrypto` fails with "extension ... is not
  available"**: this means the PostgreSQL build in use is missing contrib
  modules — this happens with some minimal/portable builds (e.g. the
  `pgserver` package used by `scripts/dev_postgres.py`, which only bundles
  `plpgsql` and `pgvector`). A standard PostgreSQL install (the official
  Windows installer, `apt install postgresql-contrib` on Debian/Ubuntu,
  etc.) ships `pgcrypto` by default and does not hit this. Note this
  doesn't actually block the app: since PostgreSQL 13, `gen_random_uuid()`
  — the only pgcrypto function this schema uses — is a core built-in, not
  dependent on the extension.
- **`AttributeError: module 'bcrypt' has no attribute '__about__'` (or a
  `ValueError: password cannot be longer than 72 bytes` from deep inside
  `passlib`)**: `passlib==1.7.4`'s bcrypt backend is incompatible with
  `bcrypt>=4.1`, which removed the version attribute passlib reads. Fixed
  by pinning `bcrypt==4.0.1` (already pinned in `requirements.txt` — if
  you see this, something re-resolved the pin).
- **FastAPI startup/shutdown log lines don't appear when hitting the app
  via `TestClient`**: `TestClient(app)` only runs the `lifespan` context
  (and therefore the startup/shutdown logging) when used as a context
  manager: `with TestClient(app) as client: ...`. All tests in this repo
  use a `client` fixture that does this correctly; a bare
  `TestClient(app)` used standalone will skip lifespan.
- **`alembic`/`pytest`/`uvicorn`: command not found, or `ModuleNotFoundError:
  No module named 'alembic'`**: there may be more than one virtualenv in
  this checkout. The one this backend actually uses is
  **`backend/.venv`** (created per **Installation** above, run from inside
  `backend/`). If a `.venv` also exists at the repository root, it is not
  this backend's environment — do not `pip install`/run commands against
  it. Always invoke `backend\.venv\Scripts\python`,
  `backend\.venv\Scripts\alembic`, etc. explicitly, or activate
  `backend\.venv` before running bare `alembic`/`pytest`/`uvicorn`.

## Story point status

- **Story Points 1-4**: complete (schema, security/RBAC, FastAPI app +
  auth endpoints, site/usv/integration/user endpoints).
- **Story Point 5** (this checkpoint): full suite verified together (87/87
  passing, stable under reordering/repetition), cross-cutting
  auth/RBAC/audit-log/no-secret-leakage checks verified explicitly (see
  git history / session notes for the verification run), documentation
  completed. The backend is feature-complete for Phase 0 — no further
  backend work is expected before Story Points 6-7 (frontend).
