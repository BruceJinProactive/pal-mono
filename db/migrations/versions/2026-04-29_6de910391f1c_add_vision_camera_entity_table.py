"""add vision_camera_entity table

Revision ID: 6de910391f1c
Revises: dce8e39a4f7e
Create Date: 2026-04-29 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6de910391f1c"
down_revision: Union[str, None] = "dce8e39a4f7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_camera_entity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("camera_config_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "roi_hint",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_config_id", "entity_id"),
    )
    op.create_index(
        op.f("ix_vision_camera_entity_camera_config_id"),
        "vision_camera_entity",
        ["camera_config_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vision_camera_entity_entity_id"),
        "vision_camera_entity",
        ["entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_vision_camera_entity_entity_id"),
        table_name="vision_camera_entity",
    )
    op.drop_index(
        op.f("ix_vision_camera_entity_camera_config_id"),
        table_name="vision_camera_entity",
    )
    op.drop_table("vision_camera_entity")
