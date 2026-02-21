"""add last_capture_url to signal_feeds

Revision ID: a8a0f1e30d06
Revises: a1b2c3d4e5f7
Create Date: 2026-02-20 16:18:54.445380

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8a0f1e30d06"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "signal_feeds", sa.Column("last_capture_url", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("signal_feeds", "last_capture_url")
