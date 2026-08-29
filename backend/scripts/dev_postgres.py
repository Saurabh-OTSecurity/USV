"""Optional dev helper: bootstrap a local PostgreSQL instance for machines that
don't have PostgreSQL installed system-wide.

This is NOT part of the application. The application always connects via the
DATABASE_* environment variables (see .env.example) to a standard PostgreSQL
server, exactly as it would in any other environment. This script exists only
to make local development possible on a machine with no PostgreSQL install and
no admin rights, by running real PostgreSQL binaries (via the optional
`pgserver` package) against a data directory under backend/.devdb (gitignored).

Usage:
    python scripts/dev_postgres.py

Prints the DATABASE_* values to put in backend/.env, and writes them there
directly for convenience.
"""

from pathlib import Path

import pgserver
import psycopg2

BACKEND_DIR = Path(__file__).resolve().parent.parent
PGDATA_DIR = BACKEND_DIR / ".devdb" / "pgdata"
APP_DB = "usv"
APP_USER = "usv_app"
APP_PASSWORD = "usv_app_dev_password"


def main() -> None:
    PGDATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(PGDATA_DIR, cleanup_mode=None)

    postmaster = server.get_postmaster_info()
    host = "127.0.0.1"
    port = postmaster.port

    conn = psycopg2.connect(host=host, port=port, user="postgres", dbname="postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (APP_USER,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {APP_USER} LOGIN PASSWORD %s", (APP_PASSWORD,))

        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (APP_DB,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {APP_DB} OWNER {APP_USER}")
    conn.close()

    env_path = BACKEND_DIR / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"DATABASE_HOST={host}",
                f"DATABASE_PORT={port}",
                f"DATABASE_NAME={APP_DB}",
                f"DATABASE_USER={APP_USER}",
                f"DATABASE_PASSWORD={APP_PASSWORD}",
                "APP_ENV=development",
                "",
            ]
        )
    )

    print(f"Dev PostgreSQL running at {host}:{port}, database={APP_DB}, user={APP_USER}")
    print(f"Wrote connection settings to {env_path}")


if __name__ == "__main__":
    main()
