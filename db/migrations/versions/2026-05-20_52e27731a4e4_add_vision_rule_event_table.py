"""add vision_rule_event table

Revision ID: 52e27731a4e4
Revises: daceb91f0ce4
Create Date: 2026-05-20 15:10:36.691092

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "52e27731a4e4"
down_revision: Union[str, None] = "daceb91f0ce4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_rule_event",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("state_change_event_id", sa.UUID(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", "triggered_at"),
        postgresql_partition_by="RANGE (triggered_at)",
    )
    op.create_index(
        "idx_vre_entity_time",
        "vision_rule_event",
        ["entity_id", "triggered_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_vre_rule_time",
        "vision_rule_event",
        ["rule_id", "triggered_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_vre_triggered",
        "vision_rule_event",
        ["triggered_at"],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_vre_triggered", table_name="vision_rule_event", postgresql_using="btree"
    )
    op.drop_index(
        "idx_vre_rule_time", table_name="vision_rule_event", postgresql_using="btree"
    )
    op.drop_index(
        "idx_vre_entity_time", table_name="vision_rule_event", postgresql_using="btree"
    )
    op.drop_table("vision_rule_event")
