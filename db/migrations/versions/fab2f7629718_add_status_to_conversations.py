"""Add status to conversations

Revision ID: fab2f7629718
Revises: 59d8780e6d50
Create Date: 2025-02-23 22:06:58.005592
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fab2f7629718"
down_revision: Union[str, None] = "59d8780e6d50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type in Postgres
    op.execute(
        "CREATE TYPE public.conversationstatus AS ENUM "
        + "('ACTIVE', 'INACTIVE', 'EXPIRED', 'CLOSING', 'CLOSED')"
    )

    # Add column as non-nullable with default value
    op.add_column(
        "conversations",
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "EXPIRED",
                "CLOSING",
                "CLOSED",
                name="conversationstatus",
                schema="public",
            ),
            nullable=False,
            server_default="ACTIVE",
        ),
        schema="public",
    )


def downgrade() -> None:
    # Remove the column first
    op.drop_column("conversations", "status", schema="public")

    # Drop the enum type
    op.execute("DROP TYPE public.conversationstatus")
