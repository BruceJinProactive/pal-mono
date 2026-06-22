"""add manually adjusted to vision rule events

Revision ID: 3fa8e1aa036a
Revises: a91c4f2e8b7d, 128e03e17ca5
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3fa8e1aa036a"
down_revision: Union[str, Sequence[str], None] = (
    "a91c4f2e8b7d",
    "128e03e17ca5",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vision_rule_event",
        sa.Column(
            "manually_adjusted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vision_rule_event", "manually_adjusted")
