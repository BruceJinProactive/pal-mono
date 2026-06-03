"""add duration and label columns to vision rules

Revision ID: 3b581347a98c
Revises: 11b2725caceb
Create Date: 2026-06-03 17:19:52.861965

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b581347a98c"
down_revision: Union[str, None] = "11b2725caceb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vision_rule",
        sa.Column(
            "label",
            sa.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )
    op.add_column(
        "vision_rule_event",
        sa.Column(
            "duration",
            sa.Numeric(precision=12, scale=4),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vision_rule_event", "duration")
    op.drop_column("vision_rule", "label")
