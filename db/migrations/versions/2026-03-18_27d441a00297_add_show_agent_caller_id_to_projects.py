"""add show_agent_caller_id to projects

Revision ID: 27d441a00297
Revises: 1e67b46a4933
Create Date: 2026-03-18 14:13:42.275823

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "27d441a00297"
down_revision: Union[str, None] = "1e67b46a4933"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "show_agent_caller_id",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "show_agent_caller_id")
