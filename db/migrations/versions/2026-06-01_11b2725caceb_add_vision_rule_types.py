"""add-vision-rule-types

Revision ID: 11b2725caceb
Revises: 3742a24deea6
Create Date: 2026-06-01 21:24:29.431504

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11b2725caceb"
down_revision: Union[str, None] = "3742a24deea6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'table_occupied'")
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'table_touch'")
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'glove_usage'")
    op.execute(
        "ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS "
        "'food_container_on_ground'"
    )
    op.execute("ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'manager_in_room'")
    op.execute(
        "ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS 'staff_at_front_desk'"
    )


def downgrade() -> None:
    pass
