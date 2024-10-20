"""Add channel_identifiers to users and projects

Revision ID: aeb9be41b437
Revises: 9058a93e1b40
Create Date: 2024-10-20 05:29:16.543064

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "aeb9be41b437"
down_revision: Union[str, None] = "9058a93e1b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add channel_identifiers column to projects
    op.add_column(
        "projects",
        sa.Column(
            "channel_identifiers",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::VARCHAR[]"),  # Default to an empty array
        ),
    )

    # Create a GIN index on channel_identifiers for projects
    op.create_index(
        "ix_projects_channel_identifiers",
        "projects",
        ["channel_identifiers"],
        postgresql_using="gin",
    )

    # Add channel_identifiers column to users
    op.add_column(
        "users",
        sa.Column(
            "channel_identifiers",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::VARCHAR[]"),  # Default to an empty array
        ),
    )

    # Create a GIN index on channel_identifiers for users
    op.create_index(
        "ix_users_channel_identifiers",
        "users",
        ["channel_identifiers"],
        postgresql_using="gin",
    )


def downgrade():
    # Remove GIN index from projects
    op.drop_index("ix_projects_channel_identifiers", table_name="projects")

    # Remove channel_identifiers column from projects
    op.drop_column("projects", "channel_identifiers")

    # Remove GIN index from users
    op.drop_index("ix_users_channel_identifiers", table_name="users")

    # Remove channel_identifiers column from users
    op.drop_column("users", "channel_identifiers")
