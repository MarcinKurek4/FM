# ADR-0003 — Revenue Init Load ETL

**Date:** 2026-06-05
**Status:** Accepted

## Problem

The revenues source file (`revenues_per_day.csv`) contains approximately
337 000 rows spanning from 2004 through the present. Before revenue facts can
be loaded into `fact_revenue`, the following conditions must hold:

- `dim_movie` rows exist for each movie title present in the CSV.
- `dim_distributor` rows exist for each distribution company.
- `dim_date` rows exist for every date present in the CSV.

The init load is a one-time, file-based bootstrap. A separate, incremental
endpoint will later handle subsequent CSV uploads — it will perform inserts
only for rows whose `source_row_id` is not yet present in `fact_revenue`.

Key constraints:

- `source_row_id` (UUID from column `id`) is the natural key for idempotency.
- Revenue and theater count are measures; no aggregation happens here.
- Movie lookup must match CSV titles against `dim_movie.title` in a
  case-insensitive manner via uppercase normalisation on both sides.

## Options Considered

### Option A — Single-pass with per-row lookups

Process each CSV row individually, performing a database lookup per unique
dimension value.

**Pros:**
- Simple logic; minimal memory footprint.

**Cons:**
- O(N) database round-trips for 337 000 rows. Unacceptable performance.

### Option B — Pre-load dimension maps, batch-insert facts

Load all dimension data into in-memory maps before iterating rows, then
batch-insert fact records.

**Pros:**
- O(1) lookups during row iteration after initial setup.
- Separates dimension resolution from fact loading cleanly.
- Consistent with the pattern established by `OmdbDwhInitLoadService`.

**Cons:**
- Loads entire `dim_movie` title map into memory (~918 rows — negligible).

### Option C — Polars join against dimension snapshots

Export dimensions to DataFrames and join CSV against them in Polars.

**Pros:**
- Maximum throughput for very large datasets.

**Cons:**
- Requires materialising dimension tables outside the repository layer,
  breaking the DTO/repository contract.
- Error-log generation is harder in a columnar pipeline.

## Decision

Option B is adopted. `RevenueInitLoadService` operates in four phases:

1. **Distributor phase** — collect distinct distributor names from the CSV
   (sentinel `"-"` → `"Unknown"`), upsert all into `dim_distributor`, build
   a `name → distributor_id` map.
2. **Date phase** — collect distinct dates, look up each in `dim_date` by
   `date_id`; create missing rows via `build_dim_date_dto` + upsert.
3. **Movie lookup** — load all `dim_movie` rows as an uppercase-normalised
   map `TITLE.upper() → movie_id` in one query. CSV title lookups key on
   `title.upper()`.
4. **Fact insert** — iterate CSV rows; rows without a `movie_id` match are
   written to an error log JSON; matched rows are batch-inserted into
   `fact_revenue` with `source_row_id` idempotency.

## Consequences

- New modules: `revenue_csv_reader`, `revenue_init_load_service`, CLI script
  `run_revenue_init_load.py`.
- `dim_movie_repository` gains `bulk_load_title_map() -> dict[str, int]`
  which returns an uppercase-keyed title → movie_id map.
- `dim_distributor_repository.upsert` receives the same session-refresh fix
  applied to other dimension repositories.
- Rows with unresolved `movie_id` are written to
  `data/raw/revenue_init_load_errorlog.json` and are never inserted into
  `fact_revenue`. They can be manually resolved and re-run.
- Idempotency is guaranteed by `fact_revenue.source_row_id` unique constraint;
  the repository's `bulk_insert` skips existing UUIDs.
- The init load does not call the OMDb API; live title resolution is out of
  scope and handled by a future resolver service.
