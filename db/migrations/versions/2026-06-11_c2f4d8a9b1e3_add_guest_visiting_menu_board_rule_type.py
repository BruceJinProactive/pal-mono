"""add guest visiting menu board vision rule type

Revision ID: c2f4d8a9b1e3
Revises: b7f43f8aac6e
Create Date: 2026-06-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f4d8a9b1e3"
down_revision: Union[str, None] = "b7f43f8aac6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE visionruletype ADD VALUE IF NOT EXISTS "
        "'guest_visiting_menu_board'"
    )


def downgrade() -> None:
    pass
