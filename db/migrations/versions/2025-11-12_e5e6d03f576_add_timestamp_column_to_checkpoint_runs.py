"""Add timestamp column to checkpoint_runs

Revision ID: e5e6d03f576
Revises: 0bb461b2187d
Create Date: 2025-11-12 15:11:26.257074

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5e6d03f576"
down_revision: Union[str, None] = "0bb461b2187d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timestamp column to checkpoint_runs table
    # Set default to created_at for existing rows, then set default to now() for new rows
    op.add_column(
        "checkpoint_runs",
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Create index on timestamp column
    op.create_index(
        op.f("ix_checkpoint_runs_timestamp"),
        "checkpoint_runs",
        ["timestamp"],
        unique=False,
    )

    # Update existing rows to set timestamp = created_at
    op.execute("UPDATE checkpoint_runs SET timestamp = created_at")


def downgrade() -> None:
    # Drop index and column
    op.drop_index(op.f("ix_checkpoint_runs_timestamp"), table_name="checkpoint_runs")
    op.drop_column("checkpoint_runs", "timestamp")
