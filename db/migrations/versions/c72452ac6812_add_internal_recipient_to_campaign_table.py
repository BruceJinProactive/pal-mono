"""add internal_recipient to campaign table

Revision ID: c72452ac6812
Revises: f4e911c7947a
Create Date: 2025-05-13 17:30:29.765471

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c72452ac6812"
down_revision: Union[str, None] = "f4e911c7947a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add internal_recipient column with default value of False
    op.add_column(
        "campaign",
        sa.Column(
            "internal_recipient", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    # Remove the internal_recipient column
    op.drop_column("campaign", "internal_recipient")
