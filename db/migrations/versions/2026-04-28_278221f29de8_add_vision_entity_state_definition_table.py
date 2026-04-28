"""add vision_entity_state_definition table

Revision ID: 278221f29de8
Revises: ac9152faa1d3
Create Date: 2026-04-28 15:45:36.943146

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "278221f29de8"
down_revision: Union[str, None] = "ac9152faa1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_entity_state_definition",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entity_type_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column(
            "sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type_id", "name"),
    )
    op.create_index(
        op.f("ix_vision_entity_state_definition_entity_type_id"),
        "vision_entity_state_definition",
        ["entity_type_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_vision_entity_state_definition_entity_type_id"),
        table_name="vision_entity_state_definition",
    )
    op.drop_table("vision_entity_state_definition")
