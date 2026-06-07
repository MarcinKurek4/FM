# FM — Box Office Analytics API
#
# Multi-stage build:
#   1. builder  — install Poetry dependencies and prepare dim_date.csv
#   2. runtime  — slim image with app, migrations, seed data, and entrypoint
#
# Container startup sequence (see docker/entrypoint.sh):
#   1. Wait until PostgreSQL accepts connections
#   2. alembic upgrade head
#   3. python scripts/load_dim_date.py              (upsert data/reference/dim_date.csv)
#   4. python scripts/run_omdb_enrichment_etl.py    (fetch OMDb metadata → JSON
#                                                    from data/master/revenue_by_title.csv;
#                                                    skipped when result file exists)
#   5. python scripts/run_omdb_dwh_init_load.py     (load OMDb master data into DWH)
#   6. python scripts/run_revenue_init_load.py      (load revenue facts from CSV)
#   7. uvicorn src.app:app
#
# Build:
#   docker compose build app
#   # or
#   docker build -t fm-app .
#
# Run (with PostgreSQL from compose):
#   docker compose up -d
#
# Build context must include one of:
#   - data/reference/dim_date.csv          (pre-generated dimension file), or
#   - data/raw/revenues_per_day (1).csv  (used to generate dim_date.csv and
#                                         revenue_by_title.csv at build time)
#
# The following files are optional in the build context but skip costly
# network steps when present:
#   - data/raw/omdb_titles_init_result.json  (skips OMDb enrichment ETL)

# ---- Builder -----------------------------------------------------------------

FROM python:3.14-slim AS builder

ENV POETRY_VERSION=2.1.1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY data ./data

RUN poetry install --only main

RUN set -eu; \
    if [ -f "data/reference/dim_date.csv" ]; then \
        echo "Builder: using existing data/reference/dim_date.csv"; \
    elif [ -f "data/raw/revenues_per_day (1).csv" ]; then \
        echo "Builder: generating data/reference/dim_date.csv from revenues CSV"; \
        python -c "\
from src.services.dim_date_seed_service import DimDateSeedService; \
DimDateSeedService().generate_csv()"; \
    else \
        echo "Builder ERROR: provide data/reference/dim_date.csv or revenues CSV in build context" >&2; \
        exit 1; \
    fi

RUN set -eu; \
    if [ -f "data/master/revenue_by_title.csv" ]; then \
        echo "Builder: using existing data/master/revenue_by_title.csv"; \
    elif [ -f "data/raw/revenues_per_day (1).csv" ]; then \
        echo "Builder: generating data/master/revenue_by_title.csv from revenues CSV"; \
        python scripts/build_revenue_by_title_master.py; \
    else \
        echo "Builder ERROR: provide data/master/revenue_by_title.csv or revenues CSV in build context" >&2; \
        exit 1; \
    fi

# ---- Runtime -----------------------------------------------------------------

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN addgroup --system fm && adduser --system --ingroup fm fm

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/data /app/data
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && chown -R fm:fm /app

USER fm

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
