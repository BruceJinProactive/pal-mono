"""add vision_entity table

Revision ID: 5302550f9bc6
Revises: 278221f29de8
Create Date: 2026-04-28 16:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5302550f9bc6"
down_revision: Union[str, None] = "278221f29de8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_entity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("entity_type_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("current_state_id", sa.UUID(), nullable=True),
        sa.Column("current_state_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "entity_type_id", "name"),
    )
    op.create_index(
        op.f("ix_vision_entity_project_id"),
        "vision_entity",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vision_entity_entity_type_id"),
        "vision_entity",
        ["entity_type_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vision_entity_current_state_id"),
        "vision_entity",
        ["current_state_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_vision_entity_current_state_id"),
        table_name="vision_entity",
    )
    op.drop_index(
        op.f("ix_vision_entity_entity_type_id"),
        table_name="vision_entity",
    )
    op.drop_index(
        op.f("ix_vision_entity_project_id"),
        table_name="vision_entity",
    )
    op.drop_table("vision_entity")
