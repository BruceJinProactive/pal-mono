"""add_all_items_to_catering_requests

Revision ID: f2b5c6a7d8e9
Revises: e47857895e0f
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f2b5c6a7d8e9"
down_revision: Union[str, None] = "e47857895e0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catering_requests",
        sa.Column(
            "all_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("catering_requests", "all_items")
