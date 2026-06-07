# ADR-0001 — Technology Stack

**Date:** 2026-06-05
**Status:** Accepted

## Problem

The FM project requires a clearly defined technology stack to ensure
consistency across development, code review, and future onboarding. All
technology choices must be explicit and traceable.

## Decision

The following stack is adopted as the organisational standard for this project.
No trade-off analysis is required — each choice reflects an established
convention within the organisation.

| Concern | Technology | Version |
|---------|-----------|---------|
| Language | Python | 3.14 |
| Dependency management | Poetry | 2.x |
| API framework | FastAPI | >= 0.115 |
| ASGI server / workers | Uvicorn | >= 0.34 |
| Database schema and ORM | SQLModel | >= 0.0.22 |
| Domain and DTO modelling | Python Dataclasses | stdlib (3.14) |
| File and data processing | Polars | >= 1.20 |
| Configuration validation | Pydantic Settings | >= 2.7 |
| HTTP client | httpx | >= 0.28 |
| Structured logging | Loguru | >= 0.7 |
| Containerisation | Docker | latest stable |
| Multi-container orchestration | Docker Compose | v2 |

### Notes

- **SQLModel** is the standard for table definitions and async database
  sessions. It is added to the project when the persistence layer is
  introduced.
- **Dataclasses** (`@dataclass`) are used for lightweight domain objects and
  DTOs that do not require Pydantic validation overhead.
- **Polars** is the primary DataFrame library. All new data processing
  pipelines use `LazyFrame` with `collect()`. Pandas is permitted only for
  interoperability with libraries that require it.
- **Loguru** replaces the standard `logging` module. The global logger is
  initialised once in `src/app.py` via `setup_logging(app_version=...)`.
  Every module imports the pre-configured logger with `from loguru import
  logger` — no `getLogger(__name__)` calls. All records are emitted as
  structured JSON to stdout (`serialize=True`) and include the
  `app_version` field on every line.
- **Uvicorn** runs with the `standard` extras (includes `uvloop` and
  `httptools`) for production-grade async performance.
- **Docker** — every service or runnable component of the project must have
  its own `Dockerfile`. Multi-stage builds are required to keep final images
  lean: a `builder` stage installs dependencies with Poetry, a `runtime`
  stage copies only the installed packages and application source.
- **Docker Compose** — when the project runs more than one container (e.g.,
  application + database + cache), all services are declared in a single
  `docker-compose.yml` at the repository root. All services must be attached
  to one explicit `bridge` network; no service relies on the default network
  created by Compose.

```yaml
networks:
  fm_network:
    driver: bridge

services:
  api:
    build: .
    networks:
      - fm_network
  db:
    image: postgres:17
    networks:
      - fm_network
```

## Consequences

- All contributors must use Python 3.14 managed via `pyenv` or equivalent.
- `pyproject.toml` is the single source of truth for dependencies; no
  `requirements.txt` files are maintained.
- Direct use of `flask`, `django`, `requests`, `aiohttp`, or `asyncio.run`
  inside FastAPI handlers is prohibited.
- Every runnable component must ship with a `Dockerfile`. Running the
  application outside Docker is permitted only during local development.
- When multiple containers are required, `docker-compose.yml` at the
  repository root is the single entry point. All services share one explicit
  `bridge` network named `fm_network`. Inter-service communication uses
  Docker Compose service names as hostnames.
- Any deviation from this stack requires a new ADR superseding this one.
