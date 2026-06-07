#!/usr/bin/env sh
set -eu

echo "[entrypoint] Waiting for PostgreSQL..."
python <<'PY'
import sys
import time

import psycopg

from src.config.settings import get_settings

settings = get_settings()
dsn = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)
for attempt in range(1, 31):
    try:
        with psycopg.connect(dsn, connect_timeout=3):
            print("[entrypoint] PostgreSQL is ready")
            sys.exit(0)
    except psycopg.OperationalError:
        print(f"[entrypoint] PostgreSQL not ready (attempt {attempt}/30)")
        time.sleep(2)
print("[entrypoint] PostgreSQL did not become ready in time", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] Loading dim_date from CSV..."
python scripts/load_dim_date.py

if [ -f "data/raw/omdb_titles_init_result.json" ]; then
    echo "[entrypoint] OMDb result file found, skipping enrichment ETL."
else
    echo "[entrypoint] Running OMDb enrichment ETL (fetches from API)..."
    python scripts/run_omdb_enrichment_etl.py
fi

echo "[entrypoint] Loading OMDb master data into DWH..."
python scripts/run_omdb_dwh_init_load.py

echo "[entrypoint] Loading revenue facts from CSV..."
python scripts/run_revenue_init_load.py

echo "[entrypoint] Starting application: $*"
exec "$@"
