"""Application settings loaded from environment variables.

All configuration is validated on first access via ``get_settings()``.
The application fails fast with a descriptive error if any mandatory
variable is absent or malformed.

Usage::

    from src.config.settings import get_settings

    settings = get_settings()
    print(settings.omdb_api_key)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

MANDATORY_FIELDS: list[str] = [
    "omdb_api_key",
    "postgres_password",
]

OPTIONAL_FIELDS: list[str] = [
    "log_level",
    "omdb_base_url",
    "postgres_host",
    "postgres_port",
    "postgres_db",
    "postgres_user",
]

FIELD_DESCRIPTIONS: dict[str, str] = {
    "log_level": "Loguru log level: DEBUG | INFO | WARNING | ERROR | CRITICAL",
    "omdb_api_key": "OMDb API key obtained from https://www.omdbapi.com/apikey.aspx",
    "omdb_base_url": "Base URL of the OMDb REST API",
    "postgres_host": "PostgreSQL server hostname or IP address",
    "postgres_port": "PostgreSQL server port",
    "postgres_db": "PostgreSQL database name",
    "postgres_user": "PostgreSQL login username",
    "postgres_password": "PostgreSQL login password",
}

SENSITIVE_FIELDS: frozenset[str] = frozenset({"omdb_api_key", "postgres_password"})


class Settings(BaseSettings):
    """Application-wide configuration derived from environment variables.

    All fields are read from the process environment or from the ``.env``
    file located at the project root. Sensitive fields (``omdb_api_key``,
    ``postgres_password``) are never logged.

    Attributes:
        log_level: Minimum log level emitted by Loguru. Must be one of
            ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, or ``CRITICAL``.
            Validated by Pydantic — an invalid value raises
            ``ValidationError`` on startup.
        omdb_api_key: OMDb API key for movie metadata enrichment.
        omdb_base_url: Base URL for the OMDb REST API.
        postgres_host: PostgreSQL server hostname.
        postgres_port: PostgreSQL server port number.
        postgres_db: Target database name.
        postgres_user: Database login username.
        postgres_password: Database login password.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    log_level: LogLevel = Field(
        default="INFO",
        description=FIELD_DESCRIPTIONS["log_level"],
    )

    omdb_api_key: str = Field(description=FIELD_DESCRIPTIONS["omdb_api_key"])
    omdb_base_url: str = Field(
        default="https://www.omdbapi.com/",
        description=FIELD_DESCRIPTIONS["omdb_base_url"],
    )

    postgres_host: str = Field(
        default="localhost",
        description=FIELD_DESCRIPTIONS["postgres_host"],
    )
    postgres_port: int = Field(
        default=5433,
        description=FIELD_DESCRIPTIONS["postgres_port"],
    )
    postgres_db: str = Field(
        default="fm",
        description=FIELD_DESCRIPTIONS["postgres_db"],
    )
    postgres_user: str = Field(
        default="fm_user",
        description=FIELD_DESCRIPTIONS["postgres_user"],
    )
    postgres_password: str = Field(
        description=FIELD_DESCRIPTIONS["postgres_password"],
    )

    @property
    def database_url(self) -> str:
        """Construct the async PostgreSQL connection URL.

        Returns:
            A ``postgresql+asyncpg://`` connection string built from the
            individual host, port, user, password, and database fields.
        """
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct the synchronous PostgreSQL connection URL for Alembic.

        Alembic runs migrations with a synchronous driver. The application
        runtime uses ``database_url`` (asyncpg); schema management uses this
        property (psycopg).

        Returns:
            A ``postgresql+psycopg://`` connection string built from the
            individual host, port, user, password, and database fields.
        """
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    The ``Settings`` object is constructed and validated once on first call.
    Subsequent calls return the same cached instance.

    Returns:
        Validated ``Settings`` instance.

    Raises:
        pydantic.ValidationError: When a mandatory environment variable is
            absent or has an incompatible type.

    Example:
        settings = get_settings()
        print(settings.omdb_base_url)
    """
    return Settings()
