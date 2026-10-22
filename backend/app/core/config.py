from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "usv"
    database_user: str = "usv_app"
    database_password: str = ""
    app_env: str = "development"

    auth_secret_key: str = "dev-only-insecure-secret-change-me"
    auth_token_expiry_minutes: int = 30

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_allowed_origins: str = "http://localhost:4200"

    # Tribot External Data API (see Triot_Detection-Engine_Api/Specifications/
    # TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md). tribot_api_token is a
    # credential issued from Tribot's own Integration admin page
    # (POST /api/integration-credentials), shaped "<credential_id>.<secret>".
    tribot_base_url: str = ""
    tribot_api_token: str = ""
    tribot_request_timeout_seconds: float = 10.0

    # Deployment topology (ECC_USV_PLATFORM_SPEC.md Section 3.5).
    # SINGLE_TENANT: one dedicated install (large enterprise customer, or this
    #   on-premise install). Exactly one row in `tenant`; no connection routing.
    # MULTI_TENANT_POOL: one shared, vendor-hosted install serving many small
    #   customers, each isolated in its own logical database inside this same
    #   Postgres cluster. Only meaningful in that mode:
    deployment_mode: str = "SINGLE_TENANT"
    # Where the `tenant_registry` table lives (tenant_id -> logical DB name).
    # In SINGLE_TENANT mode this is unused. In MULTI_TENANT_POOL mode this is
    # the one "platform" database all tenant-routing decisions are read from;
    # defaults to the primary database so a single Postgres cluster with one
    # extra database-per-tenant is all that's required (Section 3.5 -- no
    # separate control-plane deployment).
    platform_database_url_override: str = ""
    # Superuser-capable DSN used only to CREATE DATABASE for a new tenant
    # (MULTI_TENANT_POOL provisioning). Defaults to the main connection's
    # server with the maintenance "postgres" database, which is enough to
    # issue CREATE DATABASE against the same cluster.
    admin_database_url_override: str = ""
    # Connection pool per customer database in MULTI_TENANT_POOL mode. Idle
    # connections = customers x pool size, so keep it small; for ~100
    # customers raise Postgres max_connections or put PgBouncer in front.
    tenant_pool_size: int = 1
    # Where USV keeps its single-sign-on signing key and its encryption key
    # (break-glass passwords, secure shares). Created on first use; back it up
    # and keep it private -- losing it invalidates open shares and break-glass
    # passwords (rotate them), leaking it means rotating everything.
    secrets_dir: str = ".secrets"
    sso_assertion_seconds: int = 120
    # USV's web address as people open it; Tribot's "Sign in with USV" sends them here.
    ui_base_url: str = "http://localhost:4200"
    tenant_max_overflow: int = 4

    # Processed/skipped rows in the ingested_event staging table are deleted
    # after this many days (their content lives on in fleet_*). Failed rows
    # are kept for inspection.
    ingested_event_retention_days: int = 7
    # Pauses the background ingestion worker (events stay staged); for maintenance and tests.
    ingestion_worker_enabled: bool = True

    # ── USV monitoring (O&M Manual section 7). Platform defaults; a customer
    # default and per-site overrides live in monitoring_setting. ──
    monitor_loop_enabled: bool = True                    # tests switch the background loop off
    monitor_check_in_minutes: int = 15
    monitor_silent_after_intervals: int = 2
    monitor_disconnected_after_intervals: int = 4
    monitor_first_data_hours: int = 24
    monitor_escalation_minutes: int = 30
    monitor_clock_skew_seconds: int = 600
    monitor_rejected_connections_limit: int = 5          # per site in 10 minutes
    monitor_volume_drop_ratio: float = 0.1                # below 10% of the site's normal hourly volume
    monitor_volume_spike_ratio: float = 10.0              # above 10x its normal
    monitor_volume_min_baseline_per_hour: int = 20        # ignore sites too quiet to judge
    monitor_backlog_warning_minutes: int = 5
    monitor_backlog_critical_minutes: int = 30
    monitor_backlog_count_limit: int = 50000
    monitor_failed_events_per_hour: int = 100
    monitor_worker_stall_minutes: int = 2
    monitor_db_slow_ms: int = 2000
    monitor_api_error_rate_percent: float = 5.0
    monitor_api_error_min_requests: int = 50
    monitor_login_failure_limit: int = 5                  # per user in 15 minutes
    # Optional checks, skipped (and shown as "not configured") when empty:
    monitor_database_disk_path: str = ""                  # a path on the database's disk
    monitor_tls_cert_path: str = ""                       # PEM file of USV's certificate
    monitor_tls_check_host: str = ""                      # or host:port to read it from
    monitor_backup_status_path: str = ""                  # file (or folder) touched by each successful backup

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def database_url(self) -> str:
        return self.database_url_for("")

    def database_url_for(self, database_name: str) -> str:
        name = database_name or self.database_name
        return (
            f"postgresql+psycopg2://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{name}"
        )

    @property
    def platform_database_url(self) -> str:
        return self.platform_database_url_override or self.database_url

    @property
    def admin_database_url(self) -> str:
        return self.admin_database_url_override or self.database_url_for("postgres")


settings = Settings()
