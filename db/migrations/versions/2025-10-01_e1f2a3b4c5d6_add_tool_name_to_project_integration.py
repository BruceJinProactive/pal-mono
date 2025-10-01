"""add tool_name to project_integration

Revision ID: e1f2a3b4c5d6
Revises: c201797270fb
Create Date: 2025-10-01 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "c201797270fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_integration",
        sa.Column("tool_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_integration", "tool_name")
