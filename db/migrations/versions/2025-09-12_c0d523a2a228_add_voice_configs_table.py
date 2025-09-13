"""add_voice_configs_table

Revision ID: c0d523a2a228
Revises: 9a45a07f17a5
Create Date: 2025-09-12 18:48:13.221856

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c0d523a2a228"
down_revision: Union[str, None] = "9a45a07f17a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create voice_configs table
    op.create_table(
        "voice_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("voice_id", sa.String(), nullable=False),
        sa.Column(
            "replacements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("first_message", sa.String(), nullable=False),
        sa.Column("transfer_message", sa.String(), nullable=False),
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
    )
    op.create_index(op.f("ix_voice_configs_id"), "voice_configs", ["id"], unique=False)
    op.create_index(
        op.f("ix_voice_configs_project_id"),
        "voice_configs",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop voice_configs table
    op.drop_index(op.f("ix_voice_configs_project_id"), table_name="voice_configs")
    op.drop_index(op.f("ix_voice_configs_id"), table_name="voice_configs")
    op.drop_table("voice_configs")
