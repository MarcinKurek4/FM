"""Data access layer for the FM data warehouse.

This package contains repository implementations that handle all persistence
operations against the PostgreSQL ``dwh`` schema. Repositories accept injected
``AsyncSession`` instances and return DTOs defined in ``src.models.dwh``.

Each repository implements its corresponding Protocol from ``src.interfaces``.
"""
