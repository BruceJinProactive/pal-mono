"""Add delivery to CallPurpose enum

Revision ID: bfcbeb052890
Revises: a7b8c9d0e1f2
Create Date: 2026-01-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bfcbeb052890"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add delivery to CallPurpose enum
    op.execute("ALTER TYPE callpurpose ADD VALUE 'delivery'")


def downgrade() -> None:
    # NOTE: PostgreSQL does not support removing enum values.
    # This migration cannot be safely downgraded.
    pass
