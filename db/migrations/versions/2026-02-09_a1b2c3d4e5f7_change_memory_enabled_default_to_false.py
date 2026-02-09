"""change memory_enabled default to false

Revision ID: a1b2c3d4e5f7
Revises: 8fc3bde5c547
Create Date: 2026-02-09 14:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "8fc3bde5c547"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change the server_default for memory_enabled column from true to false.
    This only affects NEW agents created after this migration.
    Existing agents retain their current memory_enabled value.
    """
    # Alter the column to change the server_default
    op.alter_column(
        "agents",
        "memory_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )


def downgrade() -> None:
    """
    Revert the server_default back to true.
    """
    op.alter_column(
        "agents",
        "memory_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )
