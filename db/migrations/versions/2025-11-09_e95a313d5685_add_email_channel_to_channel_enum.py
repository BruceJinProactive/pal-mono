"""Add EMAIL channel to Channel enum

Revision ID: e95a313d5685
Revises: 68308e7cc7a4
Create Date: 2025-11-09 15:16:12.638118

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e95a313d5685"
down_revision: Union[str, None] = "68308e7cc7a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add EMAIL to Channel enum
    op.execute("ALTER TYPE channel ADD VALUE 'email'")
    # ### end Alembic commands ###


def downgrade() -> None:
    # NOTE: PostgreSQL does not support removing enum values.
    # This migration cannot be safely downgraded.
    # If you need to remove the 'email' value, you would need to:
    # 1. Drop all columns that use the Channel enum
    # 2. Drop the enum type
    # 3. Recreate the enum without 'email'
    # 4. Recreate the columns
    # This is not implemented due to the complexity and risk involved.
    pass
    # ### end Alembic commands ###
