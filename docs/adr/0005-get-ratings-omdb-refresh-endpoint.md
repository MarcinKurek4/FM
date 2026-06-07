# ADR-0005 — GET Ratings Endpoint for OMDb Rating Refresh

**Date:** 2026-06-05
**Status:** Accepted

## Problem

IMDb ratings and vote counts change over time. The DWH stores historical
snapshots in ``fact_movie_rating`` using SCD Type 2, but there is no
operational path to refresh those values from the OMDb API for movies
already loaded in ``dim_movie``. Operators need an HTTP trigger that walks
all movies in PostgreSQL, fetches current ``imdbRating`` and ``imdbVotes``
from OMDb, and inserts new fact rows only when values differ.

## Options Considered

### Option A — Re-run the full OMDb enrichment and DWH init load CLI scripts

Use existing batch scripts that read CSV titles and JSON intermediates.

**Pros:**
- No new application code.

**Cons:**
- Does not use ``dim_movie`` as the source of truth.
- Rewrites dimensions and bridges unnecessarily.
- Not exposed via API; unsuitable for on-demand refresh.

### Option B — Dedicated refresh service and GET endpoint

A new service loads every row from ``dim_movie``, calls OMDb per movie
(preferring ``imdb_id`` via the ``i=`` parameter), and applies SCD Type 2
inserts through the existing rating fact repository.

**Pros:**
- Minimal scope: ratings and votes only.
- Reuses ``insert_new_rating`` and comparison logic aligned with init load.
- Clear HTTP contract and structured summary response.

**Cons:**
- GET with side effects is unconventional; acceptable for an internal
  operator tool in v1.
- Long-running when ``dim_movie`` is large; may exceed HTTP timeouts.

## Decision

Option B is chosen. The endpoint is ``GET /api/v1/ratings``. It aborts
the entire run on OMDb HTTP 401 or rate-limit signals (mapped to
``OmdbApiError`` and HTTP 422). Per-movie not-found or missing rating
fields are logged and skipped. A 0.1 second delay between OMDb calls
reduces burst load against the free tier (1 000 requests/day).

Lookup order per movie: ``imdb_id`` when present; otherwise ``title`` via
the title search parameter.

## Consequences

- New repository method to list all movies.
- OMDb client extended with ``fetch_by_imdb_id_detailed``.
- New service, router, and unit tests.
- Operators must not invoke this endpoint more often than the OMDb quota
  allows; full refresh of N movies consumes N API calls.
