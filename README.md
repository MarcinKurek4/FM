# FM - Movie Box Office Analytics Pipeline

FM is a Python analytics pipeline for loading daily box office revenue,
enriching movie titles with OMDb metadata, storing the result in a PostgreSQL
data warehouse, and exposing FastAPI endpoints for incremental updates.

## Architecture Overview

The solution ingests daily revenue rows from `data/raw/revenues_per_day (1).csv`,
builds master data from the most valuable titles first, enriches those titles
through the OMDb API, and loads the result into the PostgreSQL `dwh` schema.
The free OMDb API key is limited to 1,000 requests per day, as documented on
the [OMDb API key page](https://www.omdbapi.com/apikey.aspx), so the initial
enrichment is resumable and ordered by total revenue.

The application follows the layered `src/` layout:

- `api/` exposes FastAPI routers and request/response schemas.
- `services/` contains ETL orchestration and business workflows.
- `repositories/` contains async SQLModel persistence operations.
- `models/` defines SQLModel DWH tables and DTOs.
- `interfaces/` defines Protocol-based contracts.
- `factories/` centralizes shared resource construction.
- `utils/` contains parsing, mapping, and conversion helpers.
- `config/` owns settings and structured logging initialization.

```mermaid
flowchart LR
    RawRevenue["data/raw/revenues_per_day (1).csv"]
    TitleMaster["data/master/revenue_by_title.csv"]
    OMDb["OMDb API"]
    OMDbJson["data/raw/omdb_titles_init_result.json"]
    DateCsv["data/reference/dim_date.csv"]
    API["FastAPI application"]
    DWH["PostgreSQL dwh schema"]
    Dashboard["Streamlit Dashboard\n(analytics/)"]

    RawRevenue --> TitleMaster
    TitleMaster --> OMDb
    OMDb --> OMDbJson
    RawRevenue --> DateCsv
    DateCsv --> DWH
    OMDbJson --> DWH
    RawRevenue --> DWH
    API --> OMDb
    API --> DWH
    DWH --> Dashboard
```

## Stack

| Component | Library |
|-----------|---------|
| Python | 3.14 |
| API framework | FastAPI + Uvicorn |
| Database | PostgreSQL + asyncpg |
| ORM | SQLModel + SQLAlchemy |
| Migrations | Alembic |
| Data processing | Polars, Pandas |
| HTTP client | httpx |
| Configuration | Pydantic Settings |
| Logging | Loguru |
| Testing | pytest + pytest-asyncio |
| Analytics dashboard | Streamlit + Plotly |
| Container runtime | Docker + Docker Compose |

## Setup

The local setup installs dependencies, prepares environment variables, starts
PostgreSQL, applies migrations, and starts the development server.

```bash
poetry install
cp .env.example .env
docker compose up -d db
poetry run alembic upgrade head
poetry run uvicorn src.app:app --reload
```

The Docker PostgreSQL service defaults to host port `5433` to avoid conflicts
with a locally installed PostgreSQL instance on port `5432`. Configure runtime
values in `.env` using `.env.example` as the reference. Do not commit `.env`.

## Running Locally

The application can be run either directly with Poetry or through Docker
Compose.

Run the API directly:

```bash
poetry run uvicorn src.app:app --reload
```

Run the full Docker environment:

```bash
docker compose build
docker compose up -d
```

Run tests:

```bash
poetry run pytest --cov=src --cov-report=term-missing
poetry run pytest tests/unit
poetry run pytest tests/integration
```

## Configuration Reference

Runtime configuration is loaded by `src/config/settings.py` through Pydantic
Settings. Sensitive values must be supplied through environment variables or
`.env` and must not be written into source files or documentation.

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `OMDB_API_KEY` | string | none | yes | OMDb API key used for metadata enrichment. |
| `OMDB_BASE_URL` | string | `https://www.omdbapi.com/` | no | Base URL for the OMDb REST API. |
| `POSTGRES_PASSWORD` | string | none | yes | PostgreSQL password. |
| `POSTGRES_HOST` | string | `localhost` | no | PostgreSQL hostname. Docker overrides it to `db`. |
| `POSTGRES_PORT` | integer | `5433` | no | PostgreSQL port used by local execution. |
| `POSTGRES_DB` | string | `fm` | no | PostgreSQL database name. |
| `POSTGRES_USER` | string | `fm_user` | no | PostgreSQL user. |
| `LOG_LEVEL` | string | `INFO` | no | Loguru log level. |

## Database Migrations

Schema changes are managed exclusively through Alembic. Dimensional and fact
tables live in the PostgreSQL `dwh` schema.

```bash
poetry run alembic upgrade head
poetry run alembic current
poetry run alembic downgrade -1
poetry run alembic revision --autogenerate -m "describe change"
```

## Data Warehouse Model

The model in `src/models/dwh_tables.py` is a star schema implemented in the
PostgreSQL `dwh` schema. Repositories map SQLModel table instances to DTOs, so
SQLModel tables are not exposed outside the data access layer.

The DWH contains these dimensions:

- `dim_movie` is the central movie dimension. It stores `imdb_id`, title,
  release year, runtime, plot, awards, OMDb box office amount, OMDb fetch
  timestamp, load timestamp, and a foreign key to `dim_rated`.
- `dim_date` is the calendar dimension. Its `date_id` is a `YYYYMMDD` integer
  key, and the table stores date, year, quarter, month, month name, day,
  day-of-week attributes, week number, weekend flag, and holiday flag.
- `dim_distributor` stores distribution companies with the natural unique key
  `distributor_name`.
- `dim_genre` stores movie genres extracted from OMDb comma-separated fields.
- `dim_director` stores directors extracted from OMDb comma-separated fields.
- `dim_rated` stores rating codes such as `PG-13` and `R` with human-readable
  descriptions.

The model uses bridge tables for many-to-many relationships:

- `bridge_movie_genre` links movies to one or more genres.
- `bridge_movie_director` links movies to one or more directors.

The model has two fact categories:

- `fact_revenue` stores daily revenue facts from `revenues_per_day (1).csv`.
  Its grain is one source row per movie, date, and distributor. It stores
  `source_row_id` for idempotency, foreign keys to `dim_movie`, `dim_date`, and
  `dim_distributor`, `revenue` as `NUMERIC(18, 2)`, theater count, and load
  timestamp.
- `fact_movie_rating` stores rating snapshots derived from OMDb master data.
  It is modeled as Slowly Changing Dimension Type 2 with `imdb_rating`,
  `imdb_votes`, `valid_from`, `valid_to`, and `is_current`. When a rating or
  vote count changes, the previous current row is closed and a new current
  snapshot is inserted.

Key persistence characteristics:

- Natural keys such as `imdb_id`, `source_row_id`, and dictionary names are
  used for idempotent upserts.
- `fact_revenue.source_row_id` prevents duplicate fact rows on repeated loads.
- `fact_movie_rating` keeps historical rating changes rather than overwriting
  previous values.
- All persistence is performed through repository classes with injected async
  sessions.

## Input Data Preparation

The data folders separate raw inputs, generated master data, and reference
dimensions.

- `data/raw/` contains unprocessed source data, including
  `data/raw/revenues_per_day (1).csv`, OMDb result JSON files, and error logs.
- `data/master/` contains master files derived from raw data, including
  `data/master/revenue_by_title.csv`.
- `data/reference/` contains reusable reference files, including
  `data/reference/dim_date.csv`.

## Initial Load Pipeline

The initial load prepares title master data, downloads OMDb metadata, maps that
metadata into DWH structures, builds the date dimension, and finally loads
daily revenue facts.

```mermaid
flowchart TD
    SourceCsv["Raw revenue CSV"]
    BuildTitleMaster["Build revenue_by_title.csv"]
    FetchOMDb["Fetch OMDb metadata with --resume"]
    OMDbJson["Persist OMDb result JSON and error log"]
    SeedDate["Generate dim_date.csv"]
    LoadDate["Load dim_date"]
    LoadMaster["Load OMDb dimensions, bridges, and rating facts"]
    LoadRevenue["Load fact_revenue"]
    ErrorLog["Write revenue_init_load_errorlog.json for unresolved movies"]

    SourceCsv --> BuildTitleMaster
    BuildTitleMaster --> FetchOMDb
    FetchOMDb --> OMDbJson
    SourceCsv --> SeedDate
    SeedDate --> LoadDate
    OMDbJson --> LoadMaster
    LoadDate --> LoadRevenue
    LoadMaster --> LoadRevenue
    LoadRevenue --> ErrorLog
```

### Step 1: Build `revenue_by_title.csv`

`scripts/build_revenue_by_title_master.py` reads
`data/raw/revenues_per_day (1).csv`, optionally fixes embedded Unicode escape
artifacts in titles, aggregates total revenue by title, sorts by
`total_revenue` descending, and writes `data/master/revenue_by_title.csv`.
Processing the highest-grossing titles first makes the OMDb request budget more
useful under the free-tier limit.

```bash
poetry run python scripts/build_revenue_by_title_master.py
```

### Step 2: Fetch Initial OMDb Metadata

`scripts/run_omdb_enrichment_etl.py` reads titles from
`data/master/revenue_by_title.csv`, calls the OMDb API, writes successful
responses to `data/raw/omdb_titles_init_result.json`, and records failed or
not-found titles in `data/raw/omdb_titles_init_errorlog.json`.

The `--resume` mode skips titles already present in the result JSON, merges new
records into existing output files, and retries previously failed titles.

```bash
poetry run python scripts/run_omdb_enrichment_etl.py --resume
```

### Step 3: Load OMDb Master And Dimensional Data

`scripts/run_omdb_dwh_init_load.py` runs `OmdbDwhInitLoadService`. This step
does not call the OMDb API. It reads `data/raw/omdb_titles_init_result.json`,
parses validated OMDb records, and maps them into DWH structures.

The service loads data in foreign-key order:

- Upserts `dim_rated`, `dim_genre`, and `dim_director`.
- Upserts `dim_movie`.
- Upserts `bridge_movie_genre` and `bridge_movie_director`.
- Inserts initial rating snapshots into `fact_movie_rating`.

The process is idempotent because dictionary tables and movies are upserted,
bridge rows are upserted, and rating facts are inserted only when the current
rating values require a new snapshot.

```bash
poetry run python scripts/run_omdb_dwh_init_load.py
```

### Step 4: Build `dim_date`

`scripts/seed_dim_date.py` generates `data/reference/dim_date.csv`. The range
starts at the minimum revenue date found in the source revenue data and ends at
`2030-12-31`. The `date_id` is built as a `YYYYMMDD` integer key.

```bash
poetry run python scripts/seed_dim_date.py
```

During container startup, `scripts/load_dim_date.py` is used instead. It loads
the already generated `data/reference/dim_date.csv` into PostgreSQL without
regenerating the file.

### Step 5: Load Initial Revenue Facts

`scripts/run_revenue_init_load.py` runs `RevenueInitLoadService`. The service
reads `data/raw/revenues_per_day (1).csv`, upserts missing distributors into
`dim_distributor`, ensures all dates exist in `dim_date`, loads the title map
from `dim_movie`, resolves each source row to `movie_id`, `date_id`, and
`distributor_id`, and inserts resolved rows into `fact_revenue`.

The load is incremental and idempotent because `source_row_id` is unique and
duplicate inserts are skipped. Rows whose titles cannot be resolved to
`dim_movie` are not loaded into `fact_revenue`; they are written to
`data/raw/revenue_init_load_errorlog.json`.

```bash
poetry run python scripts/run_revenue_init_load.py
```

## Docker Deployment

The Docker distribution starts PostgreSQL and the FastAPI application with the
same DWH bootstrap sequence used by the local ETL scripts.

`docker-compose.yml` defines:

- `db`, a PostgreSQL 17 container using the `fm_pgdata` volume for persistent
  database storage.
- `app`, the FastAPI service built from `Dockerfile`.
- `fm_network`, an explicit bridge network shared by both containers.

The application image contains source code, Alembic migrations, scripts, and
the `data` directory. The distribution can include the generated master data
and `data/reference/dim_date.csv`; therefore the costly OMDb enrichment process
does not need to run again when `data/raw/omdb_titles_init_result.json` already
exists.

At each application container startup, `docker/entrypoint.sh` performs this
sequence:

1. Wait for PostgreSQL to accept connections.
2. Run `alembic upgrade head`.
3. Load `dim_date` from `data/reference/dim_date.csv`.
4. Skip OMDb enrichment if `data/raw/omdb_titles_init_result.json` exists, or
   run `scripts/run_omdb_enrichment_etl.py` if it does not exist.
5. Load OMDb master data into the DWH with
   `scripts/run_omdb_dwh_init_load.py`.
6. Load revenue facts with `scripts/run_revenue_init_load.py`.
7. Start `uvicorn src.app:app`.

```bash
docker compose build
docker compose up -d
```

## API Endpoints

The running application exposes endpoints for refreshing rating facts and
loading new revenue data. Both endpoints call the OMDb API during processing.

### OMDb daily quota — partial completion

The free OMDb tier allows 1,000 requests per day. When the quota is exhausted,
OMDb returns `Request limit reached!`. The API does **not** abort the whole
request in that case. Each endpoint finishes the work it can perform with data
already available in the warehouse or already fetched in the current run.

| Condition | HTTP status | Behaviour |
|-----------|-------------|-----------|
| OMDb daily quota exhausted | **200 OK** | Partial success; `stopped_due_to_rate_limit: true` in the JSON body |
| Invalid OMDb API key | **422** | Entire request aborted; no partial commit |
| Invalid CSV (upload only) | **400** | Entire request aborted |

The flag `stopped_due_to_rate_limit` signals that OMDb enrichment stopped
early. Counters in the response describe what was actually persisted. Re-run the
endpoint after the quota resets to process the remaining movies or titles.

### `GET /api/v1/ratings`

Refreshes IMDb ratings for movies in `dim_movie`. For each movie, the service
looks up the current rating in OMDb by `imdb_id` when available, otherwise by
title, compares the result with the current `fact_movie_rating` row, and inserts
a new SCD Type 2 snapshot only when the rating or vote count changed.

**When the daily quota is hit during the movie loop:**

- Ratings for movies **already processed** in this run are committed.
- The loop stops; remaining movies are left unchanged until the next run.
- The endpoint returns **HTTP 200** with `stopped_due_to_rate_limit: true`.
- `omdb_calls_made` shows how many OMDb lookups were attempted;
  `ratings_inserted` and `ratings_unchanged` reflect only completed movies.

**Response fields** (`RatingsRefreshResponseDto`):

| Field | Meaning |
|-------|---------|
| `total_movies` | Movies loaded from `dim_movie` at the start of the run |
| `omdb_calls_made` | OMDb HTTP lookups performed before stop or completion |
| `ratings_inserted` | New `fact_movie_rating` snapshots written |
| `ratings_unchanged` | Movies whose OMDb rating matched the current row |
| `omdb_not_found` | Movies OMDb could not match |
| `omdb_errors` | Non-fatal per-movie failures |
| `stopped_due_to_rate_limit` | `true` when the daily quota stopped the loop early |
| `duration_ms` | Wall-clock duration of the run |

```mermaid
flowchart TD
    Request["GET /api/v1/ratings"]
    LoadMovies["Load all movies from dim_movie"]
    NextMovie{"More movies to process?"}
    FetchOMDb["Fetch current rating from OMDb"]
    FatalError{"Invalid API key?"}
    RateLimit{"Daily quota exhausted?"}
    StopFetch["Stop fetching remaining movies"]
    Compare["Compare with current fact_movie_rating"]
    Changed{"Rating or votes changed?"}
    Insert["Insert new SCD Type 2 snapshot"]
    Skip["Skip unchanged rating"]
    Response200["HTTP 200 — counters + stopped_due_to_rate_limit"]
    Error422["HTTP 422"]

    Request --> LoadMovies
    LoadMovies --> NextMovie
    NextMovie -- yes --> FetchOMDb
    FetchOMDb --> FatalError
    FatalError -- yes --> Error422
    FatalError -- no --> RateLimit
    RateLimit -- yes --> StopFetch
    StopFetch --> Response200
    RateLimit -- no --> Compare
    Compare --> Changed
    Changed -- yes --> Insert
    Changed -- no --> Skip
    Insert --> NextMovie
    Skip --> NextMovie
    NextMovie -- no --> Response200
```

### `POST /api/v1/revenue/upload`

Accepts a multipart CSV file in the same format as `revenues_per_day.csv`.
The pipeline:

1. Parses and validates the CSV.
2. Upserts `dim_distributor` and ensures `dim_date` rows exist (no OMDb).
3. Loads the `dim_movie` title map from the database.
4. Fetches OMDb metadata only for titles **missing** from `dim_movie`.
5. Resolves foreign keys and inserts new `fact_revenue` rows (`source_row_id`
   deduplication).

For titles successfully enriched in step 4, the service also upserts
`dim_rated`, `dim_genre`, `dim_director`, `dim_movie`, bridge tables, and the
first `fact_movie_rating` snapshot.

**When the daily quota is hit during step 4:**

- Steps 1–3 always complete (they do not call OMDb).
- For each missing title, OMDb is called one at a time. When a call succeeds,
  the full enrichment for that title runs **immediately** in the same iteration:
  `dim_rated`, `dim_genre`, `dim_director`, `dim_movie`, bridge tables, and the
  first `fact_movie_rating` snapshot are upserted, and the in-memory title map
  is updated. Titles processed this way before the quota error are fully loaded
  into the DWH — enrichment is not deferred and is not rolled back when the
  limit is hit on a later title.
- Step 5 then runs for **all** CSV rows whose title resolves against
  `dim_movie`, including titles that were already in the database and titles
  enriched in the steps above. Their `fact_revenue` rows are inserted.
- Only titles that were **not yet fetched** from OMDb when the quota was
  reached remain without a `dim_movie` row; matching CSV lines are counted in
  `rows_error_movie_not_found` and are **not** inserted.
- The endpoint returns **HTTP 200** with `stopped_due_to_rate_limit: true`.

In short, after a quota stop the upload covers three groups:

| Title group | Enrichment (step 4) | `fact_revenue` (step 5) |
|-------------|---------------------|-------------------------|
| Already in `dim_movie` before upload | Skipped (no OMDb call) | Inserted when row is new |
| Fetched from OMDb before quota error | Completed in full | Inserted when row is new |
| Not yet fetched when quota error occurs | Not started | Skipped (`rows_error_movie_not_found`) |

**Response fields** (`RevenueUploadResponseDto`):

| Field | Meaning |
|-------|---------|
| `facts_inserted` | New `fact_revenue` rows inserted |
| `facts_skipped_duplicate` | Rows skipped because `source_row_id` already exists |
| `distributors_upserted` | `dim_distributor` rows created or updated |
| `dates_created` | `dim_date` rows created on the fly |
| `movies_enriched_from_omdb` | New movies loaded from OMDb in this run |
| `titles_not_found_in_omdb` | Distinct titles OMDb could not match |
| `rows_error_movie_not_found` | CSV rows with no matching `dim_movie` row |
| `stopped_due_to_rate_limit` | `true` when enrichment stopped due to quota |
| `duration_ms` | Wall-clock duration of the run |

```mermaid
flowchart TD
    Request["POST /api/v1/revenue/upload"]
    Parse["Parse uploaded CSV"]
    ValidCsv{"CSV valid?"}
    UpsertDistributors["Upsert dim_distributor"]
    EnsureDates["Ensure dim_date rows"]
    LoadTitleMap["Load dim_movie title map"]
    MissingTitles{"Missing titles in CSV?"}
    FetchMissing["Fetch next missing title from OMDb"]
    FatalError{"Invalid API key?"}
    RateLimit{"Daily quota exhausted?"}
    StopFetchTitles["Stop fetching new titles"]
    PersistMaster["Enrich title: upsert dim_*, bridges, dim_movie, rating"]
    MoreMissing{"More missing titles to fetch?"}
    ResolveFacts["Resolve fact foreign keys for all resolvable titles"]
    InsertFacts["Insert new fact_revenue rows"]
    Response200["HTTP 200 — counters + stopped_due_to_rate_limit"]
    Error400["HTTP 400"]
    Error422["HTTP 422"]

    Request --> Parse
    Parse --> ValidCsv
    ValidCsv -- no --> Error400
    ValidCsv -- yes --> UpsertDistributors
    UpsertDistributors --> EnsureDates
    EnsureDates --> LoadTitleMap
    LoadTitleMap --> MissingTitles
    MissingTitles -- no --> ResolveFacts
    MissingTitles -- yes --> FetchMissing
    FetchMissing --> FatalError
    FatalError -- yes --> Error422
    FatalError -- no --> RateLimit
    RateLimit -- yes --> StopFetchTitles
    StopFetchTitles --> ResolveFacts
    RateLimit -- no --> PersistMaster
    PersistMaster --> MoreMissing
    MoreMissing -- yes --> FetchMissing
    MoreMissing -- no --> ResolveFacts
    ResolveFacts --> InsertFacts
    InsertFacts --> Response200
```

## Analytics Dashboard

The `analytics/` directory contains a standalone Streamlit application that
queries the DWH PostgreSQL schema directly and renders interactive box-office
rankings. It is independent of the `src/` production layer — no imports cross
the boundary.

### Rankings

| Section | Description |
|---|---|
| TOP 10 Movies — OMDb Box Office | Horizontal bar chart and table ranked by the OMDb-reported box office figure. |
| TOP 10 Movies — Tracked Revenue / OMDb Ratio | Bar chart and table showing the ratio of cumulative tracked revenue to the OMDb box office value. |
| TOP 10 Movies — Total Tracked Revenue | Horizontal bar chart and table of the 10 highest-grossing titles by cumulative tracked revenue. |
| TOP 10 Directors — Revenue & Film Count | Bar chart, bubble chart, and table showing cumulative revenue and distinct movie count per director. |
| TOP 10 Distributors | Donut chart, horizontal bar chart, and table of the top 10 distribution companies by revenue. |
| TOP 3 per Release Year | Individual bar chart and table generated dynamically for each release year, year descending. |
| TOP 3 per Genre | Individual bar chart and table generated dynamically for each genre, genre name ascending. |

### Running the Dashboard — Local

1. Install analytics dependencies (first time only):

```bash
poetry install --with analytics
```

2. Ensure a valid `.env` is present at the project root with `POSTGRES_*` variables set.

3. Start the dashboard:

```bash
poetry run streamlit run analytics/dashboard.py
```

The application opens at `http://localhost:8501`. All data is cached for
5 minutes; click **Refresh data** in the sidebar to force a reload.

### Running the Dashboard — Docker

Build and start the dedicated `dashboard` service alongside PostgreSQL:

```bash
docker compose up -d db dashboard
```

The dashboard is accessible at `http://localhost:8501` (or the port set in
`DASHBOARD_PORT`). The service uses `Dockerfile.analytics` — a separate,
lightweight image that installs only the `analytics` dependency group and
does not include the FastAPI application or ETL tooling.

To build the image in isolation:

```bash
docker build -f Dockerfile.analytics -t fm-dashboard .
```

### Module Layout

```
analytics/
├── queries.py          # Parameterised SQL ranking queries (psycopg2)
└── dashboard.py        # Streamlit entrypoint; charts rendered with Plotly

Dockerfile.analytics    # Standalone Docker image for the dashboard
```

---

## Dasboards
