"""add-tray-queue-floor-cleaness-vision-rule-types

Revision ID: d3b0731aa483
Revises: 3b581347a98c
Create Date: 2026-06-03 23:41:35.865524

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3b0731aa483"
down_revision: Union[str, None] = "3b581347a98c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'empty_tray'")
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'people_queued_up'")
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'floor_cleanness'")


def downgrade() -> None:
    pass
