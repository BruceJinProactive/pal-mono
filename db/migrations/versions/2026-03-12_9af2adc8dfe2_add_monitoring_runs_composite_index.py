"""add_monitoring_runs_composite_index

Revision ID: 9af2adc8dfe2
Revises: 8127367fc4fd
Create Date: 2026-03-12 16:02:05.496311

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9af2adc8dfe2"
down_revision: Union[str, None] = "8127367fc4fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Run CONCURRENTLY outside a transaction
    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_monitoring_runs_config_started "
                    "ON monitoring_runs (monitoring_config_id, started_at DESC)"
                )
            )
    except AttributeError:
        # Fallback: Use regular index creation if autocommit_block not available
        op.create_index(
            "ix_monitoring_runs_config_started",
            "monitoring_runs",
            ["monitoring_config_id", sa.text("started_at DESC")],
            unique=False,
        )


def downgrade() -> None:
    # Drop concurrently outside a transaction
    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "DROP INDEX CONCURRENTLY IF EXISTS ix_monitoring_runs_config_started"
                )
            )
    except AttributeError:
        # Fallback: Use regular index drop if autocommit_block not available
        op.drop_index("ix_monitoring_runs_config_started", table_name="monitoring_runs")
