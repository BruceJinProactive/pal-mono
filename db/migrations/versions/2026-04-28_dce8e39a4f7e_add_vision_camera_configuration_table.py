"""add vision_camera_configuration table

Revision ID: dce8e39a4f7e
Revises: 5302550f9bc6
Create Date: 2026-04-28 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "dce8e39a4f7e"
down_revision: Union[str, None] = "5302550f9bc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_camera_configuration",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("signal_source_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("llm_prompt", sa.Text(), nullable=False),
        sa.Column(
            "llm_provider",
            sa.String(length=20),
            server_default=sa.text("'azure'"),
            nullable=False,
        ),
        sa.Column(
            "llm_model",
            sa.String(length=100),
            server_default=sa.text("'gpt-4o'"),
            nullable=False,
        ),
        sa.Column(
            "processing_interval_seconds",
            sa.Integer(),
            server_default=sa.text("15"),
            nullable=False,
        ),
        sa.Column(
            "reference_images",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
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
        sa.UniqueConstraint("signal_source_id"),
    )
    op.create_index(
        op.f("ix_vision_camera_configuration_signal_source_id"),
        "vision_camera_configuration",
        ["signal_source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vision_camera_configuration_project_id"),
        "vision_camera_configuration",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_vision_camera_configuration_project_id"),
        table_name="vision_camera_configuration",
    )
    op.drop_index(
        op.f("ix_vision_camera_configuration_signal_source_id"),
        table_name="vision_camera_configuration",
    )
    op.drop_table("vision_camera_configuration")
