# ADR-0002 — OMDb DWH Init Load ETL

**Date:** 2026-06-05
**Status:** Accepted

## Problem

The FM pipeline enriches unique movie titles from the revenues CSV via the
OMDb API and persists successful lookups to
``data/raw/omdb_titles_init_result.json``. That file must be loaded into the
DWH star schema before revenue facts can reference ``dim_movie`` and related
master data.

A separate incremental path will later resolve missing movies during revenue
loads (live OMDb lookup per title). The initial load must therefore be
explicitly scoped as a one-time, file-based bootstrap — not coupled to the
OMDb HTTP client.

Constraints:

- Load order must respect foreign keys across dimensions, bridge tables, and
  ``fact_movie_rating``.
- Re-running the init load on the same JSON must not create duplicate rows.
- IMDb ratings use SCD Type 2 in ``fact_movie_rating``; static movie
  attributes use SCD Type 1 in ``dim_movie``.

## Options Considered

### Option A — File-first init load service

A dedicated ``OmdbDwhInitLoadService`` reads the init JSON from disk, maps
records to DWH DTOs, and persists via existing repository upsert methods. No
API calls during load.

**Pros:**

- Clear separation from future per-title master-data resolution.
- Idempotent replays from a stable artefact.
- No API quota consumption during database load.
- Aligns with the existing repository and DTO layer.

**Cons:**

- Requires a prior enrichment step to produce the JSON file.
- Stale JSON does not reflect later OMDb changes until re-enrichment.

### Option B — API-first load (skip JSON, call OMDb during DB load)

Load master data by re-querying OMDb for each title at database insert time.

**Pros:**

- Always fetches the latest metadata.

**Cons:**

- Couples init load to API availability and rate limits.
- Duplicates logic already implemented in ``OmdbEnrichmentEtlService``.
- Slower and harder to replay deterministically.

### Option C — Direct SQL bulk COPY

Bypass repositories and bulk-load via PostgreSQL ``COPY``.

**Pros:**

- Highest throughput for very large files.

**Cons:**

- Breaks the repository boundary and DTO contract.
- Harder to implement SCD Type 2 rating logic and bridge idempotency.
- Inconsistent with the rest of the codebase.

## Decision

Option A is adopted. ``OmdbDwhInitLoadService`` performs a file-first init
load from ``omdb_titles_init_result.json`` into:

1. ``dim_rated``, ``dim_genre``, ``dim_director`` (lookup dimensions)
2. ``dim_movie`` (SCD Type 1, natural key ``imdb_id``)
3. ``bridge_movie_genre``, ``bridge_movie_director``
4. ``fact_movie_rating`` (SCD Type 2, ``valid_from`` from JSON ``fetched_at``)

Mapping and parsing live in ``src/utils/omdb_json_reader.py`` and
``src/utils/rated_descriptions.py``. Bridge persistence uses new bridge
repositories with composite-key idempotent upsert.

Future revenue ETL will use a separate resolver service for titles absent
from ``dim_movie``; it is out of scope for this ADR.

## Consequences

- New modules: ``omdb_dwh_init_load_service``, ``omdb_json_reader``,
  ``rated_descriptions``, bridge repositories and protocols, CLI script
  ``run_omdb_dwh_init_load.py``.
- Init load depends on enrichment JSON existing and on Alembic migrations
  being applied.
- ``OmdbDwhInitLoadResult`` summarises counts for observability; reruns
  increment upsert counts only where data changed.
- Rating history during init: new snapshots are inserted only when
  ``imdb_rating`` or ``imdb_votes`` differ from the current row; identical
  values are skipped.
