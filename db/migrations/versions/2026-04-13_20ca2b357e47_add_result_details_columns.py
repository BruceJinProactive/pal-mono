"""add result details columns tags and indexes to monitoring tables

Revision ID: 20ca2b357e47
Revises: 51e1be7bca04
Create Date: 2026-04-13 16:57:03.462338

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20ca2b357e47"
down_revision: Union[str, None] = "51e1be7bca04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # monitoring_runs: add denormalized result columns
    op.add_column("monitoring_runs", sa.Column("result", sa.Text(), nullable=True))
    op.add_column("monitoring_runs", sa.Column("details", sa.Text(), nullable=True))
    op.add_column(
        "monitoring_runs", sa.Column("confidence", sa.Integer(), nullable=True)
    )
    op.create_index(
        "ix_monitoring_runs_result", "monitoring_runs", ["result"], unique=False
    )
    op.create_index(
        "ix_monitoring_runs_started_at",
        "monitoring_runs",
        [sa.text("started_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_monitoring_runs_started_at", table_name="monitoring_runs")
    op.drop_index("ix_monitoring_runs_result", table_name="monitoring_runs")
    op.drop_column("monitoring_runs", "confidence")
    op.drop_column("monitoring_runs", "details")
    op.drop_column("monitoring_runs", "result")
