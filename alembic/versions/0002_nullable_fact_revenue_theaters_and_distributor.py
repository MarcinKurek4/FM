"""Allow null theaters and distributor on fact_revenue.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07

Source CSV rows may omit theater counts or distributor names. The fact table
stores ``NULL`` for those measures instead of rejecting the row.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DWH_SCHEMA: str = "dwh"


def upgrade() -> None:
    """Make ``fact_revenue.theaters`` and ``fact_revenue.distributor_id`` nullable."""
    op.alter_column(
        "fact_revenue",
        "distributor_id",
        existing_type=sa.Integer(),
        nullable=True,
        schema=DWH_SCHEMA,
    )
    op.alter_column(
        "fact_revenue",
        "theaters",
        existing_type=sa.Integer(),
        nullable=True,
        schema=DWH_SCHEMA,
    )


def downgrade() -> None:
    """Restore NOT NULL constraints on ``fact_revenue`` optional columns."""
    op.alter_column(
        "fact_revenue",
        "theaters",
        existing_type=sa.Integer(),
        nullable=False,
        schema=DWH_SCHEMA,
    )
    op.alter_column(
        "fact_revenue",
        "distributor_id",
        existing_type=sa.Integer(),
        nullable=False,
        schema=DWH_SCHEMA,
    )
