"""add call_forwarding_setup_completed to projects

Revision ID: 3c9d4f8b2e1a
Revises: a8a0f1e30d06
Create Date: 2026-02-22 17:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c9d4f8b2e1a"
down_revision: Union[str, None] = "a8a0f1e30d06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "call_forwarding_setup_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "call_forwarding_setup_completed")
