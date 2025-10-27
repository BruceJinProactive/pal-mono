"""make checklist_id nullable in checkpoints

Revision ID: make_checklist_id_nullable
Revises: 3d00c22ffa6c
Create Date: 2025-10-27 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "make_checklist_id_nullable"
down_revision: Union[str, None] = "3d00c22ffa6c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make checklist_id nullable in checkpoints table
    op.alter_column(
        "checkpoints",
        "checklist_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    # For checkpoints with NULL checklist_id, assign them to use their project_id
    # as a placeholder before making the column NOT NULL
    op.execute(
        """
        UPDATE checkpoints
        SET checklist_id = project_id
        WHERE checklist_id IS NULL
        """
    )

    # Make checklist_id non-nullable again
    op.alter_column(
        "checkpoints",
        "checklist_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )
