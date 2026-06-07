"""Alembic migration environment for the FM project.

Loads application settings, registers all SQLModel table metadata, and
runs migrations against PostgreSQL. Dimensional tables live in the ``dwh``
schema; the Alembic version table uses the default ``public`` schema.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

from src.config.settings import get_settings
from src.models.dwh_tables import (  # noqa: F401
    BridgeMovieDirectorTable,
    BridgeMovieGenreTable,
    DimDateTable,
    DimDirectorTable,
    DimDistributorTable,
    DimGenreTable,
    DimMovieTable,
    DimRatedTable,
    FactMovieRatingTable,
    FactRevenueTable,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = SQLModel.metadata

DWH_SCHEMA: str = "dwh"


def _ensure_dwh_schema(connection: object) -> None:
    """Create the ``dwh`` schema if it does not yet exist.

    Args:
        connection: Active SQLAlchemy connection.
    """
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DWH_SCHEMA}"'))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with a URL only and emits SQL to the script
    output without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_dwh_schema(connection)
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table="alembic_version",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
