"""add missing values to changeresourcetype enum

Revision ID: 9b3b68035ed2
Revises: 00bdc822b20e
Create Date: 2026-04-01 11:06:10.117787

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3b68035ed2"
down_revision: Union[str, None] = "00bdc822b20e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            "ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'OrderIntegration'"
        )
    )
    connection.execute(
        sa.text(
            "ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'POSIntegration'"
        )
    )
    connection.execute(
        sa.text(
            "ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'CapabilityAction'"
        )
    )


def downgrade() -> None:
    # PostgreSQL does not support removing values from enum types
    pass
