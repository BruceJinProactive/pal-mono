"""make checklist_id nullable in checkpoints

Revision ID: f39bc24fd9a2
Revises: b69d5712ac47
Create Date: 2025-10-28 20:33:46.352832

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f39bc24fd9a2"
down_revision: Union[str, None] = "b69d5712ac47"
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
    # For checkpoints with NULL checklist_id, assign them random UUIDs
    # before making the column NOT NULL again
    op.execute(
        """
        UPDATE checkpoints
        SET checklist_id = gen_random_uuid()
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
