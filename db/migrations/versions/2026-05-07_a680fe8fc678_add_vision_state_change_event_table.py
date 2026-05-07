"""add vision_state_change_event table

Revision ID: a680fe8fc678
Revises: 6de910391f1c
Create Date: 2026-05-07 11:57:00.208229

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a680fe8fc678"
down_revision: Union[str, None] = "6de910391f1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_state_change_event",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("camera_config_id", sa.UUID(), nullable=True),
        sa.Column("previous_state_id", sa.UUID(), nullable=True),
        sa.Column("new_state_id", sa.UUID(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("frame_s3_key", sa.String(), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", "observed_at"),
        postgresql_partition_by="RANGE (observed_at)",
    )
    op.create_index(
        "idx_sce_entity_time",
        "vision_state_change_event",
        ["entity_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "idx_sce_observed", "vision_state_change_event", ["observed_at"], unique=False
    )
    op.execute(
        "CREATE TABLE vision_state_change_event_default "
        "PARTITION OF vision_state_change_event DEFAULT"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vision_state_change_event_default")
    op.drop_index("idx_sce_observed", table_name="vision_state_change_event")
    op.drop_index("idx_sce_entity_time", table_name="vision_state_change_event")
    op.drop_table("vision_state_change_event")
