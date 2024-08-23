"""Add raw_config to Project, make raw_config of Assistant nonull

Revision ID: a0220bd81319
Revises: fe5c96e5148a
Create Date: 2024-08-01 17:07:42.915399

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0220bd81319"
down_revision: Union[str, None] = "fe5c96e5148a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add raw_config column to Project table
    op.add_column(
        "projects",
        sa.Column(
            "raw_config",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )

    # Update existing NULL values in assistants table
    op.execute("UPDATE assistants SET raw_config = '{}' WHERE raw_config IS NULL")

    # Modify existing raw_config column in Assistant table
    op.alter_column(
        "assistants",
        "raw_config",
        existing_type=sa.JSON().with_variant(
            sa.dialects.postgresql.JSONB(), "postgresql"
        ),
        nullable=False,
        server_default=sa.text("'{}'"),
    )


def downgrade():
    # Remove raw_config column from Project table
    op.drop_column("projects", "raw_config")

    # Revert changes to raw_config column in Assistant table
    op.alter_column(
        "assistants",
        "raw_config",
        existing_type=sa.JSON().with_variant(
            sa.dialects.postgresql.JSONB(), "postgresql"
        ),
        nullable=True,
        server_default=None,
    )
