import argparse
import os
import subprocess
import sys
import time
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description="Reset the database")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation for destructive operation")
    args = parser.parse_args()

    env = os.getenv("ENVIRONMENT", "development")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://forge:forge@localhost:5432/forge_test")

    # 1. Environment must be explicitly 'test'
    if env != "test":
        print(f"ERROR: Cannot reset database in environment '{env}'. Must be 'test'.")
        sys.exit(1)

    # 2. Explicit confirmation
    if not args.confirm:
        print("ERROR: Must provide --confirm flag to execute destructive reset.")
        sys.exit(1)

    # 3. Deny production/staging hosts
    parsed = urlparse(db_url)
    host = parsed.hostname
    if host not in ["localhost", "127.0.0.1", "::1"]:
        print(f"ERROR: Cannot reset database on remote host '{host}'.")
        sys.exit(1)

    # 4. Database name must be test-only
    db_name = parsed.path.lstrip("/")
    if "test" not in db_name:
        print(f"ERROR: Database name '{db_name}' does not appear to be a test database. Must contain 'test'.")
        sys.exit(1)

    # Start Postgres
    postgres_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin")
    pg_ctl = os.path.join(postgres_bin, "pg_ctl.exe")
    pg_isready = os.path.join(postgres_bin, "pg_isready.exe")
    psql = os.path.join(postgres_bin, "psql.exe")
    data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")

    print("Starting Postgres...")
    subprocess.run([pg_ctl, "start", "-D", data_dir], check=False)

    print("Waiting for Postgres...")
    while True:
        res = subprocess.run([pg_isready, "-q"])
        if res.returncode == 0:
            break
        time.sleep(1)

    print("Postgres is ready. Dropping and creating DB...")
    # Strip query parameters if any
    db_name_clean = db_name.split("?")[0]

    # We must terminate existing connections to drop it
    subprocess.run(
        [
            psql,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name_clean}';",
        ],
        check=False,
    )

    subprocess.run(
        [
            psql,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {db_name_clean};",
        ]
    )
    subprocess.run(
        [
            psql,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {db_name_clean} OWNER forge;",
        ]
    )
    subprocess.run([psql, "-U", "postgres", "-d", db_name_clean, "-c", "GRANT ALL ON SCHEMA public TO forge;"])

    alembic = r".\.venv_official\Scripts\alembic.exe"

    print("Upgrading...")
    # Use env to pass the db url to alembic so it upgrades the test db
    env_vars = os.environ.copy()
    env_vars["DATABASE_URL"] = db_url
    subprocess.run([alembic, "upgrade", "head"], check=True, env=env_vars)

    print("Done!")


if __name__ == "__main__":
    main()
