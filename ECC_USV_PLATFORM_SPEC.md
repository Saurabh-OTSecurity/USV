# ECC/USV — Multi-Tenant Fleet Platform Specification

**Repo:** `USV/USV` (backend: FastAPI + PostgreSQL + Alembic; frontend: Angular)
**Purpose:** Hand this file to a Claude Code session running inside this repo. It translates the business-side FRD (`ECC_USV.docx`) into implementation-ready work for **ECC/USV only**, against the code that actually exists here today. "ECC" and "USV" are the same product in this FRD — the document uses both names interchangeably; this spec uses **ECC** for the platform/product and **USV** only when naming the existing `Usv` DB entity, to avoid the two now-different meanings colliding.
**Companion document:** `TRIBOT_ECC_INTEGRATION_SPEC.md` (same source FRD, scoped to the Tribot repo). Section 8 here and Section 5 there define one wire contract — keep them byte-for-byte consistent on field names, event types, and command types.
**Status:** Draft for engineering — gap analysis based on a live read of this repo on 2026-09-16. **Update 2026-09-18:** the five open questions from Section 10 were answered — see Section 10. **Update 2026-09-19: those answers were then revised by a deployment-model clarification that changes the tenancy design materially — see new Section 3.5, and Section 10's second decisions table.** Read Section 3.5 before Section 6/7's tenancy content; the 2026-09-18 "separate database per tenant, sized for enterprise scale" decision was based on an incomplete picture and is superseded by 3.5, not simply layered on top of it.

---

## 1. How to use this document

1. Read Section 2 (source truth) and Section 3 (as-built baseline) first. The single most important thing in this document is Section 3.4 — **this repo is currently single-tenant with no ingestion/storage of Tribot's domain data at all**, which is a materially bigger gap than the FRD's phrasing ("extends the existing multi-tenant architecture design," FRD Section 6) suggests exists in code today.
2. Section 4 is the task list, in dependency order. Multi-tenancy (T-1) blocks almost everything else — do not build fleet views or subscriptions on top of a schema that has no tenant column, you will redo the migrations.
3. Section 6 lists decisions, now resolved (Section 10) — read Section 10 first if you only have time for one section, then come back to the tasks it touches.
4. **Build sequencing (decided):** Tribot's repo defines the Finding/Remediation/Incident field shapes first (its `app/ir/` module is further along). This repo's T-2 ingestion schema conforms to whatever `TRIBOT_ECC_INTEGRATION_SPEC.md` Section 5.3 ends up specifying once Tribot's side ships — check that file for the current field shapes before finalizing this repo's migrations, not just this document's Section 8 copy of it.

---

## 2. Source documents

- `ECC_USV.docx` — the FRD. Main body Sections 1–9 (`FR-1.x`–`FR-8.x`) are ECC's platform-level requirements. **Appendix A**, Part B (Sections 15–25, `ECC-IR-001`…`ECC-IR-029`) is ECC's IR scope. Part C (Sections 26–43) is the shared wire contract.
- `Triot_Detection-Engine_Api/Specifications/TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md` — the existing, already-implemented Tribot-side pull API this repo's `tribot_client.py` currently consumes. Read Section 2 of that document in particular ("Deployment and Consumption Model") — it explicitly states Tribot is single-tenant and pushes tenant-scoping responsibility entirely onto the consumer (i.e., onto this repo).
- `TRIBOT_ECC_INTEGRATION_SPEC.md` (companion doc) Section 3.2 — describes Tribot's existing `usv_push` sender, which this repo has no corresponding receiver for today.

---

## 3. As-built baseline (read this before coding)

### 3.1 Stack and conventions

FastAPI backend on PostgreSQL, SQLAlchemy 2.0-style typed models (`Mapped[...]`/`mapped_column`), UUID primary keys with `gen_random_uuid()` server defaults, Alembic migrations (`alembic/versions/`). Layering is `api/routes/` → `services/` → `repositories/` → `models/`, with matching `schemas/` (Pydantic) per resource — a clean, conventional layered architecture that the new work below should extend rather than restructure.

### 3.2 What exists today, entity by entity

| Model (`app/models/`) | Fields (summarized) | FRD mapping |
|---|---|---|
| `Site` | site_id, site_code, name, description, timezone, criticality, status | Matches FRD's `sites` entity (Section 6) — **but has no `tenant_id`**. |
| `Usv` | usv_id, **site_id (1:1, unique)**, usv_code, hostname, installation_id, version, status, last_heartbeat | This is the record of *one on-prem USV/co-located instance per site* — conceptually closest to FRD's `data_sources` (Section 6), but modeled 1:1 with Site rather than as a general "data source" registry. Confusingly named relative to the product's own name (ECC/USV) — worth a naming decision, see Section 6.4. |
| `Integration` | integration_id, site_id (nullable), integration_type, name, provider, version, status, is_fixed_engine | Generic integration record. `is_fixed_engine` suggests a distinction between a first-class built-in integration (e.g., Tribot) and a pluggable one — confirm this is how Tribot's integration should be flagged. |
| `SyncState` | sync_id, integration_id, entity_type, watermark, last_started/completed_at, records_received/created/updated/failed, status, last_error | Good structural match for FRD's `TRIBOT_sync_state` (Section 6, FR-1.5) — **but nothing currently writes to this table**, because nothing currently ingests data from Tribot (Section 3.4). |
| `UsvUser` | user_id, **site_id (nullable, singular)**, username, password_hash, role (`usv_platform_admin/usv_site_admin/usv_l2_analyst/usv_l1_operator/usv_auditor/usv_viewer`), status | Single-tenant user model. Roles conflate "platform-wide" and "one-site" scope into an enum rather than the FRD's `tenant_id` + `site_ids[]` claim structure (Section 3, FR-6.x). **No `tenant_id` column anywhere.** |
| `AuditLog` | (not read in full — file exists, `audit_service.py`/`audit_log_repository.py` present) | Foundation exists; will need a `tenant_id` column added alongside everything else in T-1. |

**Not present at all:** `tenants`, `subscriptions`/`plans`/`plan_versions`/`plan_quotas`, `fleet_assets`, `alerts`/`tickets`, `findings`, `remediations`, `incidents`, `correlation_groups`, `zones`, `ingestion_tokens`, `integrations` (per-tenant external SIEM/notification config — distinct from the existing single `Integration` record which is about Tribot/data-source integrations, not outbound ones).

### 3.3 `app/core/` — auth and config

`rbac.py` exists (`get_current_user` dependency used throughout `api/routes/`) but implements **application-layer role checks only** — there is no database-layer isolation (no PostgreSQL row-level security, no `tenant_id` predicate anywhere). FRD FR-6.2 is explicit that isolation "must not depend solely on application code correctness" and specifically calls out RLS as the expected mechanism. This is a hard requirement, not a nice-to-have, given the OT/critical-infrastructure customer base implied by the rest of the FRD (Section 5, Compliance/Deployment flexibility rows).

`security.py` — not read in full; confirm whether OIDC (FR-6.1) is already implemented here or whether current auth is a simpler username/password scheme (the `UsvUser.password_hash` column suggests the latter — OIDC would typically not need a locally-stored password hash for human users). **Flag as a gap to confirm**, likely full OIDC integration is new work.

### 3.4 The critical architectural gap: ECC does not ingest or store Tribot's data

This is the single most important finding in this document. Two integration mechanisms exist across the two repos, and **neither is wired to the other, and neither matches what the FRD actually asks for**:

- **Tribot side** (`usv_push`, see companion spec Section 3.2): pushes `asset`, `alert`, `ir_case` snapshots/events to a configured HTTP+mTLS destination. **This repo has no endpoint that receives that push.** `sender.py` on the Tribot side is calling *something* — either an endpoint that doesn't exist yet in this repo, or a placeholder/future URL. Confirm which before writing the receiver.
- **ECC side** (`routes/tribot.py`, `services/tribot_service.py`, `services/tribot_client.py`): a **live pull-through proxy** — every ECC API call under `/api/v1/tribot/*` synchronously calls Tribot's read-only pull API and returns the response verbatim, with **no local persistence at all** (`tribot_service.py`'s own docstring: *"No local persistence: every call is a live, read-only proxy to Tribot... there is no USV-side caching or reshaping"*).

The proxy pattern satisfies exactly one thing the FRD wants — showing a single site's data, live, matching what that site's Tribot would show (this is the FRD's "site-wise view," FR-3.1 first half) — **and cannot satisfy anything else the FRD asks for**:

- No compiled/fleet-wide view is possible without local storage (FR-3.1 second half, FR-3.2–3.5) — you cannot aggregate "risk distribution across all sites" by fan-out-calling every Tribot instance synchronously on every dashboard load; that's an availability and latency problem on top of not being what a push architecture is for.
- No cross-site correlation (FR-3.6) is possible without stored, queryable records.
- FRD's own System Context (Section 2) and Interface Contract (Section 7) describe a **push** model explicitly: "TRIBOT periodically... reports a defined subset of its data to ECC... via Push API." The pull proxy is not this.
- FR-2.5 does allow pull "if a site cannot initiate outbound connections" as a fallback — but as a *fallback*, not the primary and only mechanism, and the current proxy isn't even that (it doesn't cache/store on pull either, so a pull-based fallback would still need a storage layer behind it).

**Decided (2026-09-18):** the push receiver becomes the primary ingestion path. See Section 6.1 for the resulting task shape, Section 10 for the decision record.

### 3.5 Deployment topology (decided 2026-09-19 — read before Sections 6/7's tenancy content)

The FRD's "multi-tenant SaaS" framing describes only one of two ways this codebase actually gets deployed. Getting this distinction right is the single biggest architectural fork in the whole project, bigger than the FR-6.2/7.x line items it's buried under:

**Deployment A — Dedicated (large enterprise customers).** A full ECC + Tribot install per customer, on that customer's own infrastructure. There is exactly one customer in this install, so there is no cross-customer isolation problem to solve — the isolation boundary is the entire deployment. What this deployment *does* need, which the FRD doesn't name explicitly but the real requirement calls for, is an internal hierarchy: a large enterprise has multiple **Business Units**, each owning some subset of sites (e.g., a global manufacturer's Chemicals BU and Packaging BU each run their own plants). A BU admin should see only their BU's sites; a corporate/global admin sees all of them. This is **not tenancy** — it's a scoping/RBAC layer one level above Site. **Decided:** a Site belongs to exactly one Business Unit (no many-to-many).

**Deployment B — Shared multi-tenant pool (low-budget customers, vendor-hosted).** One ECC install serving many separate small customers, where the FRD's "even by mistake, no customer sees another's" bar applies for real. **Decided:** enforce this with a **separate logical PostgreSQL database per tenant, within one shared Postgres cluster** (or a small, sharded number of clusters if tenant count ever outgrows one) — not a separate database *server* per tenant, and not row-level security as the isolation boundary. A connection simply cannot cross-query into another tenant's database without deliberately configured cross-database access that nothing here sets up, which is a stronger, harder-to-accidentally-break guarantee than an RLS policy that a query path might forget to apply. This is cheap at low-budget-tenant scale: creating a database and running migrations against it is a fast, scriptable operation inside one cluster, not new infrastructure — the "provisioning job standing up new infrastructure per tenant" framing in the 2026-09-18 draft of this document overstated the cost, because it was picturing separate servers. **Also decided:** Business Units are modeled here too (not just in Deployment A), even though most shared-pool tenants will only ever use one — this keeps the schema identical across both deployment modes, which matters directly for the next point.

**One schema, one codebase, two deployment modes.** Because BU is modeled in both, the actual data hierarchy is the same everywhere: `Tenant → Business Unit → Site → Zone → (assets/alerts/findings/...)`. The only thing that differs between Deployment A and B is deployment topology, governed by a `DEPLOYMENT_MODE` setting:
- `SINGLE_TENANT`: exactly one row in `tenants`, the app runs against the one database this install has, no connection-routing dependency is active (there's nothing to route between).
- `MULTI_TENANT_POOL`: N rows in a lightweight **tenant registry** (tenant_id → logical database name), and a connection-routing dependency resolves which database a request's `tenant_id` claim points to before any tenant-scoped query runs.

This means T-1 (Section 7) is considerably smaller than the 2026-09-18 draft made it look: no per-tenant infrastructure provisioning, no migration-fan-out-across-databases-on-different-hosts problem — just a tenant registry, a connection-router dependency, and a migration script that loops over the (comfortably small number of) databases in one cluster.

**Scale, re-scoped.** The earlier "enterprise scale: 100+ sites/tenant, tens of thousands of sites platform-wide" answer conflated the two deployments' very different scale profiles. Re-reading it against Deployment A vs. B:
- **Deployment A** (one dedicated customer): 100+ sites, many BUs, for that *one* tenant — this is the scale a single dedicated install's schema/query design needs to hold up under. Legitimate and unchanged.
- **Deployment B** (the shared pool): "tens of thousands of sites platform-wide" doesn't fit a *low-budget* customer profile — a small customer plausibly has 1–10 sites. What actually matters here is **tenant count** (how many logical databases share one Postgres cluster, which Postgres handles comfortably into the thousands) rather than sites-per-tenant. Treat Deployment B's real scale question as "how many low-budget tenant databases before we need a second cluster (shard)," not "how many sites."

**Release distribution and licensing — explicitly deferred.** The follow-up finding that Deployment A sends nothing home, but the vendor needs to push updates/patches *down* to it, points to a real requirement: a release channel, a local update/install client in each dedicated deployment, and offline-verifiable licenses (a signed entitlement artifact, since a dedicated deployment can't phone a billing service to ask "am I still entitled" — FR-7.x's enforcement has to work with zero connectivity to the vendor, indefinitely). **This is deferred by explicit decision** — it's vendor-side infrastructure, not code inside Tribot or ECC, and out of scope for this round. It's recorded here, and in Section 10, so it isn't lost: whatever `subscriptions`/quota work T-5 builds should assume the entitlement it checks is a **locally-stored, locally-verifiable record** (however it gets there), never a live call to anything outside the deployment — that constraint is real and in-scope now even though the distribution mechanism around it isn't.

---

## 4. Target requirements for this repo (FRD traceability)

### 4.1 Tenant and Site Management (FR-1.x)

| ID | Requirement | Status |
|---|---|---|
| FR-1.1 | Platform super-admin creates/suspends/deactivates tenants + initial plan | **Gap — no tenant entity** |
| FR-1.2 | Tenant admin creates/edits/deactivates sites within own tenant | **Partial — `Site` exists, no tenant scoping** |
| FR-1.3 | Sites sub-divided into zones (IT/OT/DMZ/Engineering, Purdue-aligned) | **Gap — no zone entity.** Also add a layer the FRD doesn't name explicitly but the real requirement needs: **Business Unit**, sitting between Tenant and Site (Section 3.5) — a Site belongs to exactly one BU, in both deployment modes. |
| FR-1.4 | Unique revocable ingestion credential per site | **Gap** |
| FR-1.5 | Tenant admin views last-sync status per site | **Foundation exists (`SyncState`), unpopulated (Section 3.4)** |

### 4.2 Tribot Feed Ingestion (FR-2.x)

| ID | Requirement | Status |
|---|---|---|
| FR-2.1 | Authenticated ingestion API, mTLS | **Gap — no receiver (Section 3.4)** |
| FR-2.2 | tenant_id/site_id derived from credential, never from body | **Gap** |
| FR-2.3 | Accept asset/risk/CVE/behavioral-alert/incident/topology/compliance summaries | **Gap** |
| FR-2.4 | Store raw_event alongside normalized fields | **Gap** |
| FR-2.5 | Support push and pull/relay fallback | **Decided: push receiver is primary (Section 6.1/10). The existing pull proxy is repurposed as the fallback/drill-down path, not built out as a second storage-backed ingestion mechanism.** |
| FR-2.6 | Never accept raw pcap | Will be true by construction once the ingestion contract (Section 8) is implemented — it doesn't include pcap fields |

### 4.3 Fleet Inventory and Cross-Site Correlation (FR-3.x)

All of FR-3.1–3.7, and the entire site-wise/compiled view duality that Section 4.3's preamble insists is "not a one-off dashboard feature" — **all gap**, blocked entirely on T-1 (tenancy) and T-2 (ingestion/storage). The FRD is explicit (Section 4.3.1) that the `incidents` entity/field must exist from the outset even though Tribot won't populate it yet — build the schema now, do not defer it.

**Extend the FRD's two view modes to three, in Deployment A (Section 3.5):** the FRD's "site-wise" and "compiled (tenant-wide)" pair assumed no Business Unit layer. With BU now in the schema, a dedicated enterprise deployment needs a middle tier — **BU-compiled** (data aggregated across a BU's sites only) — so a BU admin gets the same "fleet view" experience the FRD describes, scoped to their BU rather than the whole tenant. Implement this as the same `?siteId=` / `?siteIds=` convention (Section 7, T-3) plus a `?businessUnitId=` filter, not a third parallel code path. In Deployment B (shared pool), the tenant-wide compiled view and the BU-compiled view coincide for any tenant with only one BU, which is the common case there — no special-casing needed, the filter is just usually a no-op.

### 4.4 Alert, Ticket, and Case Management (FR-4.x)

All gap — no `alerts`/`tickets` storage exists (Section 3.4). Depends on T-2.

### 4.5 Reporting and Compliance (FR-5.x)

All gap — depends on T-2 for data to report on, plus new export tooling (FR-5.2).

### 4.6 Identity, Access, and Tenant Isolation (FR-6.x)

| ID | Requirement | Status |
|---|---|---|
| FR-6.1 | OIDC auth | **Confirm current state (Section 3.3) — likely gap or partial** |
| FR-6.2 | DB-layer tenant isolation (RLS), not application-only | **Decided: enforced via a separate physical database per tenant (Section 6.3/10), not RLS in a shared database — the FRD names RLS as an example mechanism, and separate-DB satisfies the same intent ("must not depend solely on application code correctness") more strongly. Still the biggest single risk item in this document, now as a provisioning/operations problem rather than a policy-correctness one.** |
| FR-6.3 | Role model from Section 3, enforced API+UI | **Partial — roles exist but are not tenant-scoped** |
| FR-6.4 | Cross-tenant super-admin access itself audited | **Gap (no tenant concept to cross)** |

### 4.7 Subscription and Plan Management (FR-7.x, FRD Section 4.7 — extensive)

Entirely new, entirely absent from the codebase. This is the largest single functional area in the FRD by word count and has its own detailed sub-spec — see Section 5.

### 4.8 External Integrations (FR-8.x)

Gap — no per-tenant outbound integration config (email/Teams/SIEM/ticketing) exists; the current `Integration` model is about *inbound* data sources, not outbound notification targets. These are two different concepts that will otherwise collide if you try to reuse one table — see Section 6.4.

### 4.9 Part B — ECC IR (`ECC-IR-001`–`029`)

All gap, depends on T-2 (needs Finding/Remediation/Incident storage) and on Tribot's companion work (T-2 in the Tribot spec) actually emitting Finding/Remediation events. **Sequencing decided:** Tribot builds and ships its Finding/Remediation/Incident schema first; this repo's T-2/T-8 conform to it rather than the two repos negotiating shapes in parallel. Check `TRIBOT_ECC_INTEGRATION_SPEC.md` Section 5.3 for the current shapes before writing migrations.

---

## 5. Subscription & Quota Engine — detailed spec (FRD Section 4.7, FR-7.1–7.19)

This deserves its own section because of its size and because it is architecturally independent of the multi-tenancy/ingestion work (T-1/T-2) other than depending on a `tenant_id` to attach to.

**Data model** (FRD Section 4.7.13): `Plan`, `PlanVersion`, `PlanQuota`, `PlanFeature`/entitlement, `Subscription`, `SubscriptionStatusHistory`, `ResourceUsage`. Key design constraint from the FRD, repeated multiple times (Sections 4.7.2, 4.7.3, 4.7.11, NFR-7.2): **quota dimensions and plan tiers must be data, not code** — adding a plan or a new quota dimension must not require an application deploy. Model this as a `PlanQuota(plan_version_id, dimension_key, limit_value)` row-per-dimension table (dimension_key is a string enum you can extend by inserting a row, not a schema migration) rather than fixed columns per dimension on `Plan`.

**Quota dimensions, minimum set** (Section 4.7.2): total assets, total sites, max assets/site, users, admins, data retention days, concurrent sessions, API transactions, connected data sources, integrated security products, enabled modules, alert/event volume, storage.

**Enforcement** (FR-7.4, Section 4.7.5): server-side only, at the point of resource creation (site creation, asset onboarding via ingestion, user creation) — client-side checks are UX only, never authoritative. This means the ingestion pipeline from T-2 must call into the quota service *before* persisting a new asset, not just before allowing the UI action.

**Downgrade validation** (FR-7.10, Section 4.7.10): compare current utilization against target plan's quotas before allowing a downgrade; if utilization exceeds the target, block the downgrade and surface the specific violated dimension(s) — never silently truncate/delete resources.

**Plan versioning** (FR-7.14, Section 4.7.13): a subscription pins a `plan_version_id`, not a `plan_id`, so editing a plan's quotas later doesn't retroactively change already-issued subscriptions' terms.

**Billing separation** (FR-7.15/16, Section 4.7.14): keep payment/invoice concerns entirely out of this schema — `Subscription` may later gain an `external_subscription_id` for a billing system, but no payment processing logic belongs in this repo per the FRD's explicit design principle (Section 4.7.20).

**Offline enforcement constraint (Section 3.5, decided 2026-09-19):** in `SINGLE_TENANT` deployments, this subscription record cannot be validated against a live vendor service — Deployment A sends nothing home, indefinitely, by decision. Design `Subscription`/`PlanQuota`/entitlement checks so the record they check is always a **local row already present in this deployment's own database**, however it got there (manually configured at install time today; a signed license artifact loaded by an update process is deferred per Section 3.5 and not this repo's problem to solve). Do not build any code path that requires reaching an external endpoint to determine whether an operation is within quota — that would silently break the moment Deployment A's constraint applies.

**Scale (decided 2026-09-18): enterprise** — 100+ sites per tenant, tens of thousands of sites platform-wide. This rules out computed-on-read usage: aggregating "current assets used" across tens of thousands of sites on every quota check would be a live cross-database fan-out once T-1's per-tenant-database decision (Section 6.3) is in place, not a single query. Build `resource_usage_snapshots` as a maintained counter table, updated incrementally at the point of resource creation/deletion (the same write path that enforces the quota — increment/decrement in the same transaction as the create/delete, not a separate reconciliation job as the primary mechanism, though a periodic reconciliation job is still worth having as a drift check).

Tables to add: `plans`, `plan_versions`, `plan_quotas`, `plan_features`, `subscriptions`, `subscription_status_history`, `resource_usage_snapshots` (incrementally maintained, per above).

---

## 6. Decisions (resolved 2026-09-18 — see Section 10 for the full record)

1. **Push-vs-pull — resolved: push is primary.** `usv_push` (event + snapshot push) becomes the primary ingestion path, matching the FRD's explicit architecture. Build a new `POST /api/v1/ingest/tribot` receiver (FRD Section 7.2's example shape) that:
   - Authenticates via a per-site ingestion credential (FR-1.4/FR-2.2) — **not** the existing `tribot_client.py`'s single shared `TRIBOT_API_TOKEN` config value, which has no site-scoping at all today.
   - Persists into the new `fleet_assets`/`alerts`/`findings`/`remediations`/`incidents` tables (T-2), updating `SyncState` per call.
   - Handles the event envelope + idempotent `eventId` from the companion Tribot spec Section 5.2 — de-duplicate on `eventId`, matching FRD Section 35's explicit requirement.
   The existing `tribot_client.py`/`tribot_service.py`/`routes/tribot.py` proxy is **repurposed narrowly** as an on-demand "live drill-down to this one site's Tribot instance" feature for an operator who wants current-second data beyond the last sync, not maintained as a second source of truth for fleet/compiled views.
2. **`Usv` model naming.** Given the product itself is now called ECC (with "USV" as a legacy/interchangeable name per the user), and this model represents "one on-prem instance per site" (closer to FRD's `data_sources`), consider renaming to `DataSource` or folding it into a generalized `data_sources` table per FRD Section 6 — or leave as-is if the team still thinks of it as "the USV box at the site" distinct from "a data source" conceptually. Flag your choice, don't rename silently — `Usv` is referenced by FK from other tables. (Not part of the 2026-09-18 decision round — still open, low stakes, decide at implementation time.)
3. **Tenant isolation mechanism — resolved 2026-09-19 (supersedes the 2026-09-18 answer): scoped to Deployment B only, and lighter-weight than first designed.** See Section 3.5 for the full reasoning. In short: `SINGLE_TENANT` deployments (Deployment A) need no isolation mechanism at all — there is exactly one tenant. `MULTI_TENANT_POOL` deployments (Deployment B, the shared low-budget pool) use a **separate logical database per tenant inside one shared Postgres cluster**, not RLS and not separate database servers. Consequences for T-1, revised down from the previous draft:
   - A **tenant registry** (a small table, not a separate control-plane deployment) holds `tenants`, `business_units`, and a tenant→logical-database-name mapping. This can live in a dedicated "platform" database within the same cluster.
   - The API layer needs a **connection-routing dependency**, active only when `DEPLOYMENT_MODE=MULTI_TENANT_POOL`: resolve `tenant_id` from the authenticated request's JWT claim, look up the tenant's database name in the registry, and bind the request's DB session to it. In `SINGLE_TENANT` mode this dependency is a no-op (one fixed connection, configured once).
   - **Migrations fan out across databases in one cluster**, which is fast (seconds per database) — a scripted loop, not a distributed rollout. Build it as an explicit, monitorable step from the start so a partial failure (some tenant databases migrated, others not) is visible rather than silently inconsistent.
   - **Provisioning a new Deployment-B tenant** is now cheap: create one database, run migrations against it, seed default zones/BU. **Provisioning a new Deployment-A (dedicated) customer** is a separate, infrastructure-level process (standing up a whole new install) that this repo's schema/migrations feed into but doesn't orchestrate — out of scope for this document.
   - Row-level scoping *within* one tenant's database (a Site Responder seeing only their site, a BU admin seeing only their BU) is still an application-layer + query-filter concern in both deployment modes — unaffected by which isolation mechanism separates tenants from each other.
4. **Outbound integrations vs. inbound data-source integrations (FR-8.x vs. existing `Integration` model).** Recommended: keep them as two separate tables (`data_source_integrations` — rename of today's `Integration` — vs. new `outbound_integrations` for email/Teams/SIEM/ticketing), since they have different lifecycles, different credential shapes, and different owners (platform-configured data source vs. tenant-configured notification target). (Not part of the 2026-09-18 decision round.)
5. **OIDC scope.** Confirm whether `security.py`'s current auth is meant to be replaced wholesale by OIDC (FR-6.1) or layered (OIDC for human users, the existing scheme retained for machine/API credentials per the "Integration service (machine actor)" role in FRD Section 3). Recommended: the latter — OIDC for `UsvUser` human logins, separate per-site bearer credentials (FR-1.4) for the ingestion API, which is also how Tribot's own external API (companion spec) already does credential-vs-session separation. (Not part of the 2026-09-18 decision round — still open.)

---

## 7. Phased task list

### T-1: Multi-tenancy + Business Unit foundation (blocks nearly everything else)

Revised 2026-09-19 per Section 3.5 — smaller than the previous draft, because isolation is now a deployment-mode concern rather than something every table needs to carry.

- **Schema, used identically in both deployment modes:** `tenants` (id, name, status, created/suspended/deactivated timestamps, initial plan reference per FR-1.1), `business_units` (id, tenant_id, name, status), `sites` gains a `business_unit_id` FK (NOT NULL — Decision: a Site belongs to exactly one BU), `zones` under `Site` (FR-1.3, Purdue-level-aligned — reuse whatever level vocabulary Tribot's `industrial_zone`/Purdue fields already use, check `TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md` Section 4.4's `zoneId`/`purdue_level` mapping so labels don't drift from what Tribot reports).
- **`DEPLOYMENT_MODE` config flag** (`SINGLE_TENANT` | `MULTI_TENANT_POOL`), read at startup:
  - `SINGLE_TENANT`: exactly one seeded row in `tenants`; no connection-routing dependency is active; the app runs against the one database this install has, same as today. This is the mode a dedicated enterprise customer's install runs in.
  - `MULTI_TENANT_POOL`: a **tenant registry** (tenant_id → logical database name, in a small shared "platform" database within the cluster) backs a **connection-routing dependency** — resolve `tenant_id` from the request's JWT claim, look up its database, bind the session to it, before any tenant-scoped query runs. This is the mode the vendor-hosted shared instance runs in.
- **Tenant provisioning (`MULTI_TENANT_POOL` only)**: on tenant creation (FR-1.1), create one new database in the cluster, run the migration set against it, seed a default Business Unit and default zone vocabulary, register it in the tenant registry. Make it idempotent/resumable — a failure partway through (database created, migrations not yet run) must be safely retryable.
- **Migration fan-out (`MULTI_TENANT_POOL` only)**: a schema change runs once per tenant database in the cluster — fast (seconds each), but build the runner as an explicit, monitorable step (report which databases succeeded/failed) from day one rather than a manual loop.
- **Extend `UsvUser`** to carry a `business_unit_id` (nullable — a BU-scoped admin) and `site_ids: list[UUID]` claim shape (FRD Section 3) instead of the current single nullable `site_id`, for the "Analyst scoped to specific sites" and "BU admin scoped to their BU" role cases (Section 3.5) — this is application-layer/query-filter logic, unaffected by which deployment mode is active.
- **Existing dev data**: `.devdb/` holds today's single-tenant dataset. Under `SINGLE_TENANT` mode this is simply "the deployment's one database" already — no migration needed for that mode. If you also stand up a local `MULTI_TENANT_POOL` dev environment, treat `.devdb/`'s data as the seed for that mode's *first* tenant database rather than retrofitting a `tenant_id` column onto it in place.

### T-2: Ingestion receiver + fleet data model
- Depends on T-1 (needs the connection router to know which tenant DB an ingested payload belongs to) and on Tribot shipping the Finding/Remediation/Incident shapes first (Section 4.9's sequencing decision) before finalizing those three tables' columns.
- New tables (in each tenant's database): `ingestion_tokens` (per-site, revocable, FR-1.4), `fleet_assets`, `alerts`/`tickets`, `findings`, `remediations` (mirroring the companion spec's Tribot-side shape field-for-field once published), `incidents` (placeholder-from-day-one per FR-3.5/Section 4.3.1 — build the column, accept it'll be empty until Tribot's Finding/Remediation work ships), `correlation_groups`.
- `POST /api/v1/ingest/tribot` (or equivalent) receiver: the ingestion credential (FR-1.4) must resolve to both a `tenant_id` (to route to the right database, per T-1's connection router) and a `site_id` within it (FR-2.2 — never trust either from the request body); stores `raw_event` verbatim (FR-2.4) plus normalized fields, updates `SyncState`.
- Idempotent event handling keyed on the companion spec's `eventId` — reject/no-op a replayed `eventId` rather than reprocessing (FRD Section 35).
- **Async receive architecture, still worth building regardless of the Section 3.5 scale re-scoping:** do not process an inbound push synchronously to completion on the request thread. Accept the payload, validate the credential and envelope, persist it to a durable receive-queue/staging table immediately, return `202`-equivalent fast, and process (normalize, quota-check, write to `fleet_assets`/etc., update `resource_usage_snapshots`) via a worker pool — this is the receiving-side mirror of the durable outbox the companion Tribot spec's T-3 builds on the sending side. It matters most for a large Deployment-A customer (Section 3.5) with 100+ sites all pushing on their own schedules into one install, and it's cheap insurance for Deployment B regardless of tenant count.
- Quota check (Section 5) on every new asset/site before persisting, incrementing `resource_usage_snapshots` in the same transaction as the write, not just on the UI action that triggered it.

### T-3: Site-wise / BU-compiled / tenant-compiled views (FR-3.1–3.7, extended per Section 4.3)
- Every list/dashboard endpoint for assets, risk, vulnerabilities, alerts, (eventually) incidents needs three modes, not two: `?siteId=` (site-wise), `?businessUnitId=` (BU-compiled — new, Section 4.3), and tenant-wide with optional `?siteIds=`/`?businessUnitIds=` filtering (compiled) — implement this as one query-parameter convention applied consistently, per the FRD's explicit instruction that this is "not a one-off dashboard feature" (Section 4.3 preamble).
- Cross-site correlation (FR-3.6): group alerts/incidents sharing CVE/vendor-firmware/attack-pattern into `correlation_groups` — a scheduled job or on-write trigger, confirm which with the user based on expected data volume.
- Do **not** re-run Tribot's detection logic here (FR-3.7) — correlation operates only on already-reported fields.

### T-4: Alert/Ticket/Case management (FR-4.x)
- Unified queue across sites with tenant/site/zone/severity filtering (FR-4.1).
- Assign/comment/status-change on tickets spanning multiple sites (FR-4.2).
- **Critical constraint (FR-4.3):** ECC-side status changes must never write back to or alter the Tribot-originating record — Tribot remains source of truth for local detection state. If T-5 (ECC→Tribot commands, per companion spec) is active, a status change may *trigger* a command, but the local ECC ticket status and Tribot's local alert/case status are independent fields that must not be silently synced in either direction (mirrors FRD Section 25/38's "neither system blindly overwrites the other").

### T-5: Subscription & Quota engine (Section 5 above, full detail there)

### T-6: RBAC completion + audit (FR-6.x)
- OIDC integration per Decision 5.
- Enforce role model consistently across every new API surface from T-2–T-5, not just existing routes.
- Cross-tenant super-admin access audit (FR-6.4) — this only becomes meaningful once T-1 exists; add it as part of T-1's audit-log tenant_id work.

### T-7: Reporting & external integrations (FR-5.x, FR-8.x)
- Compliance report aggregation across sites' Tribot-reported compliance mapping (needs T-2's stored data).
- PDF/Excel export (FR-5.2).
- Per-tenant outbound integrations table (Decision 4) — email/Teams/SIEM/ticketing, independently revocable credentials per tenant (FR-8.3).

### T-8: ECC IR (`ECC-IR-001`–`029`)
- Depends on T-2's Finding/Remediation/Incident tables being populated, which depends on the companion Tribot spec's T-2/T-4 actually shipping and emitting the new event types. Sequence this after confirming Tribot-side progress.
- Central incident creation from one or many Tribot alerts, possibly cross-site (ECC-IR-018–020).
- ECC incident independent of / associable-with Tribot incidents (ECC-IR-021–024) — needs the `ecc_incident_id`/`tribot_incident_id` cross-reference fields defined identically on both sides (companion spec Section 5.3).
- Central remediation/finding visibility (ECC-IR-009–017), including full planning-history display (ECC-IR-015) — read-only rollup of what Tribot's T-2 pushes, do not let ECC's UI imply it can edit Tribot's remediation plan directly unless the ECC→Tribot command channel (companion spec T-5) is live and that specific command is implemented.

---

## 8. The wire contract ECC must speak (must match `TRIBOT_ECC_INTEGRATION_SPEC.md` Section 5 exactly)

Duplicated here deliberately so this repo's Claude Code session doesn't need to cross-reference the other file mid-implementation — but if you change anything, update both.

- **Event envelope**: `eventId, eventType, siteId, objectType, objectId, occurredAt, payload`. De-duplicate strictly on `eventId`.
- **Event types**: see companion spec Section 5.1 for the full list (`FINDING_*`, `REMEDIATION_*`, `INCIDENT_*`, `INVESTIGATION_*`, `RESPONSE_*`, `EVIDENCE_*`, plus existing `ALERT_*`/asset snapshots).
- **Object shapes**: Finding, Remediation (with append-only planning-history array), Incident — field lists in companion spec Section 5.3. Store `raw_event` verbatim per FR-2.4 regardless of how you normalize.
- **Attribution fields**: `ecc_incident_id` / `tribot_incident_id` cross-references must round-trip losslessly in both directions.

---

## 9. Non-functional requirements carried over from the FRD

- Tenant isolation enforced at the database layer, not just application code (FR-6.2) — **decided (revised 2026-09-19, Section 3.5):** applies only within `MULTI_TENANT_POOL` deployments, via a separate logical database per tenant in a shared cluster. `SINGLE_TENANT` deployments have no cross-tenant isolation problem to solve. Still the single most safety-critical NFR for the shared pool, given it's explicitly the deployment shape serving customers who couldn't otherwise justify dedicated infrastructure.
- ECC availability must never be a dependency for Tribot's local operation (Section 5, Availability row) — this is Tribot's property to uphold, but ECC's ingestion receiver (T-2) should be built so a slow/erroring receiver doesn't cause Tribot-side backpressure either (return fast, queue/persist-then-process internally — see T-2's async-receive note).
- Scalability — **re-scoped 2026-09-19 (Section 3.5):** the two deployment modes have different scale profiles, not one shared number. Deployment A (dedicated): size for one large enterprise's 100+ sites and multiple BUs in a single install. Deployment B (shared pool): size for tenant *count* in one Postgres cluster (comfortably into the thousands), not sites-per-tenant, which is expected to be small per low-budget customer. Both drive T-1's (much lighter, post-revision) tenant-registry/connection-router work and Section 5's incrementally-maintained usage counters.
- Deployment flexibility — **resolved via two explicit deployment modes (Section 3.5), not one universal mechanism:** `SINGLE_TENANT` for dedicated enterprise installs, `MULTI_TENANT_POOL` (database-per-tenant-in-shared-cluster) for the vendor-hosted low-budget pool. Same schema and codebase, different topology.
- Compliance — **decided: IEC 62443 / NIST 800-82 only** for the first release (FR-5.1's named frameworks). No additional data-residency requirement is being built in now.
- **Offline licensing/entitlement (new, 2026-09-19, Section 3.5):** `SINGLE_TENANT` deployments must be able to enforce their subscription/quota limits (FR-7.4) indefinitely with zero connectivity to any vendor service — design every quota/entitlement check to read a local row, never a remote call. The mechanism for *getting* that local record updated (a signed license artifact, a release/update channel) is a deferred, separate vendor-side effort — not this repo's problem — but the local-only enforcement constraint it implies is in scope now.

---

## 10. Decisions log (resolved 2026-09-18)

All five open questions from the previous draft have been answered by the user. This is now the authoritative record — Sections 3–9 above have been edited to reflect each one; if you find a stale sentence elsewhere in this document that contradicts this table, this table wins.

| # | Question | Decision | Primary impact |
|---|---|---|---|
| 1 | Push receiver vs. keep the live pull proxy as primary ingestion | **Push receiver is primary.** Pull proxy repurposed narrowly as an on-demand single-site drill-down, not a second source of truth. | Section 6.1, T-2 |
| 2 | Target scale for ingestion + quota engine | **Enterprise**: 100+ sites/tenant, tens of thousands of sites platform-wide. | Section 5 (incrementally-maintained usage counters), T-1 (provisioning/migration automation), T-2 (async receive-and-process, not synchronous) |
| 3 | Dedicated-deployment isolation mechanism | **Separate physical database per tenant** for every tenant, not RLS in a shared database. | Section 6.3 (new), T-1 (rewritten as control-plane + provisioning + connection-routing + migration fan-out) |
| 4 | Compliance/data-residency scope for first release | **IEC 62443 / NIST 800-82 only.** No explicit data-residency feature built now (the per-tenant-DB model makes adding region-pinning later comparatively cheap if needed). | Section 9 |
| 5 | Which repo defines Finding/Remediation/Incident field shapes first | **Tribot builds first** (its `app/ir/` module is further along); this repo's T-2/T-8 conform to `TRIBOT_ECC_INTEGRATION_SPEC.md` Section 5.3 once published, rather than negotiating shapes in parallel. | Section 4.9, T-2, T-8 |

**Still open (lower stakes, not part of either decision round — decide at implementation time and note the choice in your summary):** the `Usv` model rename (Section 6, item 2), the outbound-vs-inbound integrations table split (Section 6, item 4), and OIDC scope/layering (Section 6, item 5).

### 10.1 Decisions log (resolved 2026-09-19 — supersedes row 2 and 3 above)

A deployment-model clarification arrived after the 2026-09-18 round and changed the tenancy design materially. Full reasoning in Section 3.5; this table is the quick reference.

| # | Question | Decision | Primary impact |
|---|---|---|---|
| 6 | How many deployment shapes actually exist, and does "enterprise scale" apply uniformly? | **Two shapes, not one:** dedicated single-tenant installs per large enterprise customer, and one shared vendor-hosted pool for low-budget customers. The 2026-09-18 "enterprise scale" answer was really describing Deployment A's per-tenant scale (100+ sites for one customer), not a platform-wide number — re-scoped, doesn't change per se, just clarified. | Section 3.5, supersedes row 2's platform-wide framing |
| 7 | Is database-per-tenant still right for the low-budget shared pool given the cost concern raised for row 3? | **Yes, but as logical databases within one shared Postgres cluster, not separate database servers per tenant.** This keeps the strong isolation guarantee (a connection can't cross-query into another tenant's database) while staying cheap enough for low-budget customers — the operational-cost objection to row 3's original design was about picturing separate infrastructure per tenant, which this doesn't require. | Section 3.5, 6.3 (rewritten), T-1 (substantially lighter) |
| 8 | Does Deployment A need internal segmentation below Tenant? | **Yes — Business Unit, new entity**, sitting between Tenant and Site. A Site belongs to exactly one BU. | Section 4.1, 4.3 (new BU-compiled view tier), T-1, T-3 |
| 9 | Does the shared pool (Deployment B) need Business Units too? | **Yes — modeled in both deployment modes**, even though most shared-pool tenants will only ever use one, so the schema stays identical across both modes. | Section 3.5, T-1 |
| 10 | Should dedicated deployments report health/usage up to a vendor-side umbrella system? | **No — they send nothing.** Instead, the vendor needs to push updates/patches *down* to them. This reframes "umbrella visibility" as a release-and-licensing distribution problem, not a telemetry system. | Section 3.5 |
| 11 | Should the release/licensing distribution system be designed now? | **Deferred entirely.** It's vendor-side infrastructure (a release server, signed license issuance), not code inside Tribot or ECC, and out of scope for this round. Only its downstream constraint is in scope now: subscription/quota enforcement in `SINGLE_TENANT` deployments must work against a local record with zero live connectivity, indefinitely. | Section 5, Section 9 |
