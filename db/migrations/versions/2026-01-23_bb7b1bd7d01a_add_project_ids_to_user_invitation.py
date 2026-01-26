"""add_project_ids_to_user_invitation

Revision ID: bb7b1bd7d01a
Revises: a7b8c9d0e1f2
Create Date: 2026-01-23 19:00:19.060758

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "bb7b1bd7d01a"
down_revision: Union[str, None] = "bfcbeb052890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_invitations",
        sa.Column(
            "project_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=True,
            comment="Project IDs to assign on acceptance, NULL = account-level access",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_invitations", "project_ids")
