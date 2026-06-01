"""add state definition type and active flag

Revision ID: 3742a24deea6
Revises: ff69bf83de9e
Create Date: 2026-06-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3742a24deea6"
down_revision: Union[str, None] = "ff69bf83de9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vision_entity_state_definition",
        sa.Column(
            "definition_type",
            sa.String(length=50),
            server_default="cleanliness",
            nullable=False,
        ),
    )
    op.add_column(
        "vision_entity_state_definition",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vision_entity_state_definition", "is_active")
    op.drop_column("vision_entity_state_definition", "definition_type")
