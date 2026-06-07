"""Create DWH star schema.

Revision ID: 0001
Revises:
Create Date: 2026-06-05

Creates schema ``dwh`` with dimension, bridge, and fact tables for box
office analytics (including ``fact_movie_rating`` with SCD Type 2).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DWH_SCHEMA: str = "dwh"


def upgrade() -> None:
    """Create all star-schema tables in ``dwh`` (schema created by ``alembic/env.py``)."""
    op.create_table(
        "dim_rated",
        sa.Column("rated_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rating_code", sa.String(length=20), nullable=False),
        sa.Column("rating_description", sa.String(length=200), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("rated_id", name="pk_dim_rated"),
        sa.UniqueConstraint("rating_code", name="uq_dim_rated_rating_code"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_rated_rating_code",
        "dim_rated",
        ["rating_code"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "dim_distributor",
        sa.Column("distributor_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("distributor_name", sa.String(length=200), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("distributor_id", name="pk_dim_distributor"),
        sa.UniqueConstraint("distributor_name", name="uq_dim_distributor_distributor_name"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_distributor_distributor_name",
        "dim_distributor",
        ["distributor_name"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "dim_genre",
        sa.Column("genre_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("genre_name", sa.String(length=100), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("genre_id", name="pk_dim_genre"),
        sa.UniqueConstraint("genre_name", name="uq_dim_genre_genre_name"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_genre_genre_name",
        "dim_genre",
        ["genre_name"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "dim_director",
        sa.Column("director_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("director_name", sa.String(length=200), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("director_id", name="pk_dim_director"),
        sa.UniqueConstraint("director_name", name="uq_dim_director_director_name"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_director_director_name",
        "dim_director",
        ["director_name"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "dim_date",
        sa.Column("date_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("month_name", sa.String(length=20), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("day_of_week_name", sa.String(length=20), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("is_weekend", sa.Boolean(), nullable=False),
        sa.Column("is_holiday", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("date_id", name="pk_dim_date"),
        sa.UniqueConstraint("date", name="uq_dim_date_date"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_date_date",
        "dim_date",
        ["date"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "dim_movie",
        sa.Column("movie_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("imdb_id", sa.String(length=15), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("rated_id", sa.Integer(), nullable=True),
        sa.Column("runtime_min", sa.Integer(), nullable=True),
        sa.Column("plot", sa.Text(), nullable=True),
        sa.Column("awards", sa.Text(), nullable=True),
        sa.Column("box_office_omdb", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("omdb_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rated_id"],
            [f"{DWH_SCHEMA}.dim_rated.rated_id"],
            name="fk_dim_movie_dim_rated",
        ),
        sa.PrimaryKeyConstraint("movie_id", name="pk_dim_movie"),
        sa.UniqueConstraint("imdb_id", name="uq_dim_movie_imdb_id"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_movie_imdb_id",
        "dim_movie",
        ["imdb_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_dim_movie_rated_id",
        "dim_movie",
        ["rated_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "bridge_movie_genre",
        sa.Column("movie_id", sa.BigInteger(), nullable=False),
        sa.Column("genre_id", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["genre_id"],
            [f"{DWH_SCHEMA}.dim_genre.genre_id"],
            name="fk_bridge_movie_genre_dim_genre",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            [f"{DWH_SCHEMA}.dim_movie.movie_id"],
            name="fk_bridge_movie_genre_dim_movie",
        ),
        sa.PrimaryKeyConstraint("movie_id", "genre_id", name="pk_bridge_movie_genre"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_bridge_movie_genre_movie_id",
        "bridge_movie_genre",
        ["movie_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_bridge_movie_genre_genre_id",
        "bridge_movie_genre",
        ["genre_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "bridge_movie_director",
        sa.Column("movie_id", sa.BigInteger(), nullable=False),
        sa.Column("director_id", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["director_id"],
            [f"{DWH_SCHEMA}.dim_director.director_id"],
            name="fk_bridge_movie_director_dim_director",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            [f"{DWH_SCHEMA}.dim_movie.movie_id"],
            name="fk_bridge_movie_director_dim_movie",
        ),
        sa.PrimaryKeyConstraint("movie_id", "director_id", name="pk_bridge_movie_director"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_bridge_movie_director_movie_id",
        "bridge_movie_director",
        ["movie_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_bridge_movie_director_director_id",
        "bridge_movie_director",
        ["director_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "fact_revenue",
        sa.Column("revenue_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_row_id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.BigInteger(), nullable=False),
        sa.Column("date_id", sa.BigInteger(), nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("revenue", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("theaters", sa.Integer(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["date_id"],
            [f"{DWH_SCHEMA}.dim_date.date_id"],
            name="fk_fact_revenue_dim_date",
        ),
        sa.ForeignKeyConstraint(
            ["distributor_id"],
            [f"{DWH_SCHEMA}.dim_distributor.distributor_id"],
            name="fk_fact_revenue_dim_distributor",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            [f"{DWH_SCHEMA}.dim_movie.movie_id"],
            name="fk_fact_revenue_dim_movie",
        ),
        sa.PrimaryKeyConstraint("revenue_id", name="pk_fact_revenue"),
        sa.UniqueConstraint("source_row_id", name="uq_fact_revenue_source_row_id"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_revenue_source_row_id",
        "fact_revenue",
        ["source_row_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_revenue_movie_id",
        "fact_revenue",
        ["movie_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_revenue_date_id",
        "fact_revenue",
        ["date_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_revenue_distributor_id",
        "fact_revenue",
        ["distributor_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )

    op.create_table(
        "fact_movie_rating",
        sa.Column("rating_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("movie_id", sa.BigInteger(), nullable=False),
        sa.Column("imdb_rating", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("imdb_votes", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            [f"{DWH_SCHEMA}.dim_movie.movie_id"],
            name="fk_fact_movie_rating_dim_movie",
        ),
        sa.PrimaryKeyConstraint("rating_id", name="pk_fact_movie_rating"),
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_movie_rating_movie_id",
        "fact_movie_rating",
        ["movie_id"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_movie_rating_valid_from",
        "fact_movie_rating",
        ["valid_from"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_movie_rating_valid_to",
        "fact_movie_rating",
        ["valid_to"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_movie_rating_is_current",
        "fact_movie_rating",
        ["is_current"],
        unique=False,
        schema=DWH_SCHEMA,
    )
    op.create_index(
        "ix_dwh_fact_movie_rating_movie_id_is_current",
        "fact_movie_rating",
        ["movie_id", "is_current"],
        unique=False,
        schema=DWH_SCHEMA,
    )


def downgrade() -> None:
    """Drop all ``dwh`` tables and the schema."""
    op.drop_index(
        "ix_dwh_fact_movie_rating_movie_id_is_current",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_fact_movie_rating_is_current",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_fact_movie_rating_valid_to",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_fact_movie_rating_valid_from",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_fact_movie_rating_movie_id",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_table("fact_movie_rating", schema=DWH_SCHEMA)

    op.drop_index("ix_dwh_fact_revenue_distributor_id", table_name="fact_revenue", schema=DWH_SCHEMA)
    op.drop_index("ix_dwh_fact_revenue_date_id", table_name="fact_revenue", schema=DWH_SCHEMA)
    op.drop_index("ix_dwh_fact_revenue_movie_id", table_name="fact_revenue", schema=DWH_SCHEMA)
    op.drop_index("ix_dwh_fact_revenue_source_row_id", table_name="fact_revenue", schema=DWH_SCHEMA)
    op.drop_table("fact_revenue", schema=DWH_SCHEMA)

    op.drop_index(
        "ix_dwh_bridge_movie_director_director_id",
        table_name="bridge_movie_director",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_bridge_movie_director_movie_id",
        table_name="bridge_movie_director",
        schema=DWH_SCHEMA,
    )
    op.drop_table("bridge_movie_director", schema=DWH_SCHEMA)

    op.drop_index(
        "ix_dwh_bridge_movie_genre_genre_id",
        table_name="bridge_movie_genre",
        schema=DWH_SCHEMA,
    )
    op.drop_index(
        "ix_dwh_bridge_movie_genre_movie_id",
        table_name="bridge_movie_genre",
        schema=DWH_SCHEMA,
    )
    op.drop_table("bridge_movie_genre", schema=DWH_SCHEMA)

    op.drop_index("ix_dwh_dim_movie_rated_id", table_name="dim_movie", schema=DWH_SCHEMA)
    op.drop_index("ix_dwh_dim_movie_imdb_id", table_name="dim_movie", schema=DWH_SCHEMA)
    op.drop_table("dim_movie", schema=DWH_SCHEMA)

    op.drop_index("ix_dwh_dim_date_date", table_name="dim_date", schema=DWH_SCHEMA)
    op.drop_table("dim_date", schema=DWH_SCHEMA)

    op.drop_index(
        "ix_dwh_dim_director_director_name",
        table_name="dim_director",
        schema=DWH_SCHEMA,
    )
    op.drop_table("dim_director", schema=DWH_SCHEMA)

    op.drop_index("ix_dwh_dim_genre_genre_name", table_name="dim_genre", schema=DWH_SCHEMA)
    op.drop_table("dim_genre", schema=DWH_SCHEMA)

    op.drop_index(
        "ix_dwh_dim_distributor_distributor_name",
        table_name="dim_distributor",
        schema=DWH_SCHEMA,
    )
    op.drop_table("dim_distributor", schema=DWH_SCHEMA)

    op.drop_index("ix_dwh_dim_rated_rating_code", table_name="dim_rated", schema=DWH_SCHEMA)
    op.drop_table("dim_rated", schema=DWH_SCHEMA)
