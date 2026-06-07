# ADR-0004 — Incremental Revenue Upload Endpoint with On-the-Fly OMDb Enrichment

**Date:** 2026-06-05
**Status:** Accepted

## Problem

The initial load pipeline (`RevenueInitLoadService`) is a one-time CLI batch
process that reads a fixed CSV file, expects all movie titles to already exist
in `dim_movie`, and writes unmatched titles to an error log. As new revenue
periods arrive, operators need to upload incremental CSV files through an HTTP
interface without manual pre-enrichment steps. Titles that have not yet been
seen by the system must be fetched from the OMDb API and loaded into the
dimension and bridge tables before the corresponding fact rows are inserted.
Rate-limit and authentication errors from OMDb must surface to the caller
immediately, because continuing with partial data would produce an inconsistent
fact table.

## Options Considered

### Option A — Reuse the existing CLI services via a thin HTTP wrapper

Expose the existing `RevenueInitLoadService` and `OmdbDwhInitLoadService`
directly from a FastAPI handler. The handler would orchestrate two serial
calls: enrichment followed by revenue load.

**Pros:**
- No new service class; minimal code duplication.

**Cons:**
- `RevenueInitLoadService` reads from a hardcoded file path; adapting it for
  bytes received from an HTTP upload requires modifying a stable service that
  already has integration tests.
- `OmdbDwhInitLoadService` reads from a JSON result file produced by a prior
  enrichment run; feeding it individual responses requires further surgery.
- The two services hold independent in-memory state (title maps, lookup maps)
  built in separate passes; combining them into a coherent single-transaction
  pipeline is not possible without coupling the two service classes.

### Option B — New dedicated service with per-title OMDb enrichment

Create `RevenueUploadEtlService`, a new service class that accepts CSV bytes
at runtime, resolves all dimension keys in a single session, performs OMDb
lookups only for titles absent from `dim_movie`, persists enriched records
through the existing repository layer, and inserts revenue facts — all in one
coordinated async pipeline. The existing init-load services remain untouched.

**Pros:**
- Existing services are not modified; their tests remain valid.
- The new service owns the incremental use case end-to-end, making it trivial
  to test in isolation.
- OMDb errors (401, 429) abort the pipeline immediately and propagate to the
  HTTP layer with a precise error code.
- Idempotency is handled by the existing `bulk_insert` ON CONFLICT DO NOTHING
  contract on `fact_revenue`.

**Cons:**
- Upsert logic for OMDb dimensions (rated, genre, director, movie, bridges,
  ratings) must be duplicated as private free functions in the new service file
  rather than called from `OmdbDwhInitLoadService`. This is a deliberate
  trade-off to avoid modifying a stable service.

## Decision

Option B is chosen. A new `RevenueUploadEtlService` is introduced in
`src/services/revenue_upload_etl_service.py`. It is exposed via a FastAPI
`POST /api/v1/revenue/upload` endpoint that accepts a multipart CSV file
upload.

The OMDb dimension upsert logic is extracted into private free functions within
the new service module. These functions mirror the behaviour of the
corresponding methods in `OmdbDwhInitLoadService` but accept a single
`OmdbMovieResponse` object directly, eliminating the need to materialise an
intermediate JSON file.

The `OmdbClientProtocol` already exists in `src/interfaces/`; it is reused
without modification. A new `OmdbApiError` domain exception is added to
`src/models/exceptions.py` to carry the HTTP status code and error message
back to the handler.

## Consequences

- `src/services/revenue_upload_etl_service.py` is a new production module.
- `src/models/exceptions.py` is a new module (or extended if it already
  exists) with `OmdbApiError`.
- `src/api/v1/revenue_upload.py` is a new router module registered in
  `src/app.py`.
- `src/api/dependencies.py` is a new module providing FastAPI dependency
  functions for the async session and the shared `httpx.AsyncClient`.
- The OMDb free-tier daily limit (1 000 requests) constrains the number of
  new titles that can be onboarded per day. Operators must not upload files
  with more than ~1 000 new titles per calendar day, or the endpoint will
  return HTTP 422.
- Future refactoring may consolidate the duplicated dimension upsert logic
  into a shared utility; doing so is deferred to avoid scope creep and
  premature abstraction.
