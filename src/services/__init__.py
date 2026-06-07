"""Service layer for the FM pipeline."""

from src.services.omdb_client import OmdbClient

__all__: list[str] = ["OmdbClient"]
