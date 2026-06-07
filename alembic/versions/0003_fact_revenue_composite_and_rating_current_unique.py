"""Add composite unique keys on fact_revenue and fact_movie_rating.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-07

Adds a business-grain unique constraint on ``fact_revenue`` for
``(movie_id, date_id, distributor_id)`` with ``NULLS NOT DISTINCT`` so that
rows with a missing distributor still participate in uniqueness.

Adds a partial unique index on ``fact_movie_rating`` ensuring at most one
current rating row per movie (SCD Type 2 integrity).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DWH_SCHEMA: str = "dwh"


def upgrade() -> None:
    """Create composite and partial unique constraints on fact tables."""
    op.create_unique_constraint(
        "uq_fact_revenue_movie_date_distributor",
        "fact_revenue",
        ["movie_id", "date_id", "distributor_id"],
        schema=DWH_SCHEMA,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "uq_fact_movie_rating_movie_id_current",
        "fact_movie_rating",
        ["movie_id"],
        unique=True,
        schema=DWH_SCHEMA,
        postgresql_where=sa.text("is_current = true"),
    )


def downgrade() -> None:
    """Drop composite and partial unique constraints on fact tables."""
    op.drop_index(
        "uq_fact_movie_rating_movie_id_current",
        table_name="fact_movie_rating",
        schema=DWH_SCHEMA,
    )
    op.drop_constraint(
        "uq_fact_revenue_movie_date_distributor",
        "fact_revenue",
        schema=DWH_SCHEMA,
        type_="unique",
    )
