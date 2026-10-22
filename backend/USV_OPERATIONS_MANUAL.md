# USV / ECC Backend — Operations Manual

Procedural reference: **to make X happen, do Y.** Every procedure below was verified against the actual code in this repository (`app/`) as of this writing, not against the design specs. For *why* the system is shaped this way, see `ECC_USV_PLATFORM_SPEC.md` — this document deliberately does not repeat that rationale.

> **Cross-reference — read before relying on push ingestion in production:** Tribot's existing `usv_push` sender (see `TRIBOT_OPERATIONS_MANUAL.md`, "Known Integration Gap") currently posts to three fixed paths (`/api/v1/push/tribot/assets|alerts|ir-cases`) using mTLS-only authentication and a `{"data": [...]}` batch body. This backend's receiver, documented below, exposes a single path (`POST /api/v1/ingest/tribot`) using Bearer-token authentication and a one-event-envelope body. **These do not currently interoperate wire-for-wire.** Section 12 documents the receiver as built; it will not receive real Tribot traffic until that gap is closed on one side or the other.

---

## 1. Prerequisites

- Python 3.11+, PostgreSQL 14+ (this repo was verified against Postgres 16).
- `pip install -r requirements.txt` from the `backend/` directory.

## 2. Environment configuration (`.env`)

Settings are read by `app/core/config.py` (`pydantic-settings`, reads a `.env` file in `backend/`). All keys are optional with defaults shown; nothing below is required for a local/dev run against `localhost:5432`.

| Key | Default | Purpose |
|---|---|---|
| `database_host` / `database_port` / `database_name` / `database_user` / `database_password` | `localhost` / `5432` / `usv` / `usv_app` / `` | Primary Postgres connection. |
| `app_env` | `development` | `development` leaks real exception text into 500 responses; set anything else in production. |
| `auth_secret_key` | `dev-only-insecure-secret-change-me` | JWT signing key for human-user sessions. **Must** be overridden outside dev. |
| `auth_token_expiry_minutes` | `30` | Human session token lifetime. |
| `app_host` / `app_port` | `127.0.0.1` / `8000` | Bind address for `uvicorn`. |
| `cors_allowed_origins` | `http://localhost:4200` | Comma-separated list. |
| `tribot_base_url` / `tribot_api_token` / `tribot_request_timeout_seconds` | empty / empty / `10.0` | Only used by the **legacy pull-proxy** (`app/api/routes/tribot.py`), for the single-site drill-down view. `tribot_api_token` is issued from Tribot's own `/api/integration-credentials` (see the Tribot manual, Section 5), shaped `"<credential_id>.<secret>"`. Not used by the push receiver. |
| `deployment_mode` | `SINGLE_TENANT` | `SINGLE_TENANT` or `MULTI_TENANT_POOL` — see Section 11. |
| `platform_database_url_override` | empty (falls back to the primary DB) | Only meaningful in `MULTI_TENANT_POOL` mode. |
| `admin_database_url_override` | empty (falls back to `.../postgres`) | A superuser-capable DSN used only to `CREATE DATABASE` for a new tenant. |

## 3. First-time database setup

```bash
cd backend
alembic upgrade head        # creates/updates every table through the latest migration
python -m app.db.seed       # idempotent — safe to re-run
```

`alembic upgrade head` with no `sqlalchemy.url` set in `alembic.ini` reads the primary connection from `.env` via `app/core/config.py`. Do not hand-edit `alembic.ini`'s `sqlalchemy.url` — it is deliberately left blank so `alembic/env.py` falls back to `.env`.

**Do not run this against a tenant database directly for `MULTI_TENANT_POOL` provisioning** — use Section 11's procedure instead, which sets the target URL programmatically before invoking Alembic.

### What seeding creates

One Tenant ("Default Tenant"), one Business Unit ("Default Business Unit"), one Site (`SITE-001`, "Demo Manufacturing Plant"), placeholder Integration rows (Tribot/Claroty/Nozomi/Wazuh/IR/ECC), and six users — **all dev-only, all with the password shown, none of them safe to keep in any environment a real customer can reach:**

| Username | Role | Password |
|---|---|---|
| `platform.admin` | `usv_platform_admin` | `DevOnly!PlatformAdmin1` |
| `site.admin` | `usv_site_admin` | `DevOnly!SiteAdmin1` |
| `l2.analyst` | `usv_l2_analyst` | `DevOnly!L2Analyst1` |
| `l1.operator` | `usv_l1_operator` | `DevOnly!L1Operator1` |
| `auditor.user` | `usv_auditor` | `DevOnly!Auditor1` |
| `viewer.user` | `usv_viewer` | `DevOnly!Viewer1` |

There is no separate "create the first admin" procedure needed here (unlike Tribot — see that manual's Section 3): seeding creates a usable admin directly. **To change or remove these accounts for a non-dev environment**, edit `app/db/seed.py`'s `USERS` list before first seeding, or disable a seeded account afterward via a direct `UPDATE usv_user SET status='disabled' WHERE username=...`.

## 4. Starting the service

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On startup the app verifies the DB connection (logs a warning, does not crash, if it fails) and starts a background asyncio task that polls the `ingested_event` staging table every 5 seconds (Section 12). Stopping the process cancels that task cleanly.

## 5. Logging in

```
POST /api/v1/auth/login
{"username": "platform.admin", "password": "DevOnly!PlatformAdmin1"}
```

Returns `{"token": "...", ...}`. Use `Authorization: Bearer <token>` on every subsequent human-facing request. In `MULTI_TENANT_POOL` mode, also pass `"tenant_code"` in the login body to select which tenant database to authenticate against; in `SINGLE_TENANT` mode the sole Tenant row is used automatically and `tenant_code` can be omitted.

## 6. RBAC roles

Defined in `app/core/rbac.py`. Every endpoint that mutates state declares which of these it accepts via `require_role(...)`; endpoints not shown here accept any authenticated user (`get_current_user`).

| Role constant | Value |
|---|---|
| `USV_PLATFORM_ADMIN` | `usv_platform_admin` |
| `USV_SITE_ADMIN` | `usv_site_admin` |
| `USV_L2_ANALYST` | `usv_l2_analyst` |
| `USV_L1_OPERATOR` | `usv_l1_operator` |
| `USV_AUDITOR` | `usv_auditor` |
| `USV_VIEWER` | `usv_viewer` |

Today, only **Platform Admin** and **Site Admin** may create Business Units, create Sites, or issue/revoke ingestion credentials (Sections 8–10). Every other write path in the codebase should be checked against its own route file for its specific `require_role(...)` list — this table is not exhaustive for modules outside this session's build.

## 7. Procedure — Add a Business Unit

```
POST /api/v1/business-units
Authorization: Bearer <platform_admin_or_site_admin_token>
{"name": "West Region Plants"}
```

Response includes `business_unit_id` (UUID) — you need this for Section 8.

`GET /api/v1/business-units` (any authenticated user) lists all of them; `GET /api/v1/business-units/{id}` fetches one.

## 8. Procedure — Add a Site (a new Tribot deployment location)

```
POST /api/v1/site
Authorization: Bearer <platform_admin_or_site_admin_token>
{
  "site_code": "SITE-002",
  "name": "Plant B",
  "business_unit_id": "<uuid from Section 7>",
  "description": "optional",
  "timezone": "UTC",
  "criticality": "medium"
}
```

`site_code` must be unique — a duplicate returns `409 SITE_CODE_EXISTS`. Response includes `site_id` (UUID).

**This alone does not connect anything.** A Site with no ingestion credential (next section) will never appear with live data — it is purely a registration. `GET /api/v1/site` lists all sites; `GET /api/v1/site/{id}` fetches one.

## 9. Procedure — Issue an ingestion credential for a site

This is the credential that specific site's Tribot instance will present when pushing data in.

```
POST /api/v1/sites/{site_id}/ingestion-tokens
Authorization: Bearer <platform_admin_or_site_admin_token>
```

Response:

```json
{"token_id": "...", "site_id": "...", "status": "active", "token": "<token_id>.<secret>", ...}
```

**The `token` field is shown exactly once.** It is stored server-side only as a bcrypt hash and cannot be retrieved again — if lost, issue a new one (below) and revoke the old one. Copy `token` immediately into that site's Tribot instance's push configuration as its bearer credential (see the Tribot manual's Section 6) — **once that wiring is compatible; see the cross-reference banner at the top of this document.**

`GET /api/v1/sites/{site_id}/ingestion-tokens` lists every token ever issued for that site (active and revoked) — use this to audit what's live.

## 10. Procedure — Revoke an ingestion credential

```
DELETE /api/v1/sites/{site_id}/ingestion-tokens/{token_id}
Authorization: Bearer <platform_admin_or_site_admin_token>
```

Immediately invalidates that credential; any further push attempts using it get `401 UNAUTHORIZED`. There is no "rotate" endpoint — rotation is issue-new-then-revoke-old, done in that order so the sending Tribot instance is never left with zero valid credentials.

## 11. How ingestion actually works (background knowledge, not a procedure)

- `POST /api/v1/ingest/tribot` (separate auth scheme from human logins — a Tribot push credential, never a `UsvUser` JWT, is accepted here, and vice versa) accepts one event envelope: `{eventId, eventType, objectType, objectId, occurredAt, payload, siteId?}`.
- The site/tenant that the event is attributed to comes **only** from the authenticated credential (looked up via `token_id`), never from `envelope.siteId` in the body — a payload claiming a different site is silently ignored for attribution purposes (this was specifically tested against payload-spoofing).
- The handler writes the envelope to the `ingested_event` staging table and returns `202` **immediately** — `{"status": "accepted", "eventId": "..."}` or `{"status": "duplicate", ...}` if that `eventId` was already seen (idempotent via a Postgres `ON CONFLICT DO NOTHING` on the primary key). Nothing is normalized into fleet tables synchronously.
- A background worker (started in `app/main.py`'s lifespan, polling every 5 seconds) picks up rows where `ingested_event.process_status = 'pending'`, in `received_at` order, and normalizes each into `fleet_asset` / `alert` / `remediation` / `incident` based on `objectType`. Handled object types today: `asset`, `alert`, `remediation`, `incident`, `ir_case` (mapped to Incident). **`finding` is not yet handled** — those events sit at `process_status='pending'` indefinitely by design, because Tribot's Finding entity shape isn't finalized yet.
- Each event is committed individually; one bad event never blocks the batch behind it.

### Troubleshooting ingestion

Query `ingested_event` directly (or add an admin endpoint if you need this often — none exists yet):

| `process_status` | Meaning | Action |
|---|---|---|
| `pending` | Received, not yet normalized. Normal if <5s old. If persistently pending for `finding` events, that's expected (unhandled type, see above). If persistently pending for a handled type, the worker loop may not be running — check server logs for "ingestion worker tick failed". |
| `processed` | Normalized successfully into the matching fleet table. `processed_at` is set. |
| `failed` | The normalizer raised an exception — see `error_message` on the row (common cause: payload missing the resource's id field, e.g. an asset event with no `asset_id`/`assetId`). |
| `skipped` | No normalizer registered for that `objectType` (currently only `finding`). |

A `401` on `POST /api/v1/ingest/tribot` means: malformed `Authorization` header, unknown `token_id`, a revoked token, or a wrong secret — the response never distinguishes which, by design (avoids helping a credential-guessing attacker).

## 12. Procedure — Query fleet views

All under `/api/v1/fleet/*`, human-authenticated (`get_current_user`), same filter convention on every endpoint:

- No filter → **comprehensive/compiled view**: every site across the whole deployment.
- `?siteId=<uuid>` → **site-wise**: exactly one site.
- `?businessUnitId=<uuid>` → **BU-compiled**: every site under that Business Unit.
- `?siteIds=<comma-separated uuids>` / `?businessUnitIds=<comma-separated uuids>` → the same, for an explicit multi-site or multi-BU set.

Endpoints: `GET /api/v1/fleet/assets`, `/alerts`, `/remediations`, `/incidents`, `/correlation-groups` (the last has no site/BU filter — it's cross-cutting by CVE).

A Business Unit with zero sites, or a site with zero processed events, correctly returns `[]` — not an error, and not "everything."

## 13. Procedure — Provision a new tenant (`MULTI_TENANT_POOL` mode only)

**There is no HTTP endpoint for this today** — deliberately, per the platform spec, until product decides who is authorized to trigger it and how billing hooks in. The mechanism itself is real and tested; invoke it from a Python shell on a machine with this backend's dependencies and `.env` available:

```bash
cd backend
python -c "
from app.services.tenant_provisioning_service import provision_tenant
entry = provision_tenant('acme', 'Acme Corp')
print(entry.tenant_id, entry.database_name, entry.status)
"
```

This: creates a new Postgres database named `usv_tenant_<hex>` in the same cluster (via `admin_database_url`), runs every Alembic migration against it, seeds one Tenant + one default Business Unit row inside it, and registers it in the `tenant_registry` table (in the platform database) so the login-time tenant router (Section 5, `tenant_code`) can find it. **It is idempotent/resumable** — if it fails partway (e.g. database created but migration crashed), calling it again with the same `tenant_code` picks up where it left off rather than erroring or duplicating.

After provisioning, log in with `{"username": "...", "password": "...", "tenant_code": "acme"}` — but note the new tenant database has no seeded users yet (only the seed script's Tenant/BU rows). Insert a first user directly, or extend `provision_tenant` to also call the seeding logic in `app/db/seed.py` scoped to that tenant's database, before relying on this for a real customer onboarding.

### Switching `deployment_mode`

This is a `.env` flag, not a migration. Switching `SINGLE_TENANT` → `MULTI_TENANT_POOL` on a database that already has data does **not** retroactively split that data into per-tenant databases — it only changes how *new* logins/provisioning behave going forward. Do not flip this on a live single-tenant deployment without a separate, deliberate data-migration plan.

## 14. Known gaps (do not assume otherwise)

- No HTTP endpoint for tenant provisioning (Section 13) — script/shell only.
- `finding` object-type events are accepted and staged but never normalized (Section 11) — Tribot's Finding wire shape isn't final.
- The wire contract mismatch with Tribot's actual `usv_push` sender (top of this document) means the ingestion pipeline in Section 11, while independently tested and working, has not been exercised against a real Tribot instance's real traffic as of this writing.
- The legacy pull-proxy (`app/api/routes/tribot.py`, using `tribot_base_url`/`tribot_api_token`) is a separate, still-functional on-demand single-site drill-down — it is not superseded by anything above and has its own, unrelated operational needs (a valid Tribot pull-API credential per site, configured today via a single global `.env` value, not per-site).
