"""add criteria to vision_entity_state_definition

Revision ID: 5ca029ff7265
Revises: a680fe8fc678
Create Date: 2026-05-07 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ca029ff7265"
down_revision: Union[str, None] = "a680fe8fc678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vision_entity_state_definition",
        sa.Column("criteria", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vision_entity_state_definition", "criteria")
