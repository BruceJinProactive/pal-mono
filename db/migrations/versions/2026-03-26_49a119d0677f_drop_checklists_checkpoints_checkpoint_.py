"""drop checklists checkpoints checkpoint_runs tables

Revision ID: 49a119d0677f
Revises: 27d441a00297
Create Date: 2026-03-26 19:57:32.114262

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "49a119d0677f"
down_revision: Union[str, None] = "27d441a00297"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop checkpoint_runs table and its indexes
    op.drop_index(
        op.f("ix_checkpoint_runs_checkpoint_id"), table_name="checkpoint_runs"
    )
    op.drop_index(op.f("ix_checkpoint_runs_created_at"), table_name="checkpoint_runs")
    op.drop_index(op.f("ix_checkpoint_runs_id"), table_name="checkpoint_runs")
    op.drop_index(op.f("ix_checkpoint_runs_status"), table_name="checkpoint_runs")
    op.drop_index(
        op.f("ix_checkpoint_runs_submission_id"), table_name="checkpoint_runs"
    )
    op.drop_index(op.f("ix_checkpoint_runs_timestamp"), table_name="checkpoint_runs")
    op.drop_table("checkpoint_runs")

    # Drop checkpoints table and its indexes
    op.drop_index(op.f("ix_checkpoints_checklist_id"), table_name="checkpoints")
    op.drop_index(op.f("ix_checkpoints_id"), table_name="checkpoints")
    op.drop_index(op.f("ix_checkpoints_project_id"), table_name="checkpoints")
    op.drop_table("checkpoints")

    # Drop checklists table and its indexes
    op.drop_index(op.f("ix_checklists_id"), table_name="checklists")
    op.drop_index(op.f("ix_checklists_project_id"), table_name="checklists")
    op.drop_table("checklists")

    # Drop the orphaned checkstatus enum type
    op.execute(sa.text("DROP TYPE IF EXISTS checkstatus"))


def downgrade() -> None:
    # Recreate the checkstatus enum type (needed by checkpoint_runs.status)
    op.execute(
        sa.text(
            "DO $$ BEGIN"
            " CREATE TYPE checkstatus AS ENUM"
            " ('processing', 'active', 'failed', 'expired', 'error', 'overdue');"
            " EXCEPTION WHEN duplicate_object THEN NULL;"
            " END $$"
        )
    )

    # Recreate checklists table
    op.create_table(
        "checklists",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "ai_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checklists_project_id"), "checklists", ["project_id"])
    op.create_index(op.f("ix_checklists_id"), "checklists", ["id"])

    # Recreate checkpoints table
    op.create_table(
        "checkpoints",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("checklist_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("group", sa.String(), nullable=True),
        sa.Column(
            "rules",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            server_default="{}",
        ),
        sa.Column(
            "requires_image",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checkpoints_project_id"), "checkpoints", ["project_id"])
    op.create_index(op.f("ix_checkpoints_id"), "checkpoints", ["id"])
    op.create_index(
        op.f("ix_checkpoints_checklist_id"), "checkpoints", ["checklist_id"]
    )

    # Recreate checkpoint_runs table
    op.create_table(
        "checkpoint_runs",
        sa.Column(
            "id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("checkpoint_id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "processing",
                "active",
                "failed",
                "expired",
                "error",
                "overdue",
                name="checkstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("review", sa.String(), nullable=True),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column(
            "is_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checkpoint_runs_timestamp"), "checkpoint_runs", ["timestamp"]
    )
    op.create_index(
        op.f("ix_checkpoint_runs_submission_id"), "checkpoint_runs", ["submission_id"]
    )
    op.create_index(op.f("ix_checkpoint_runs_status"), "checkpoint_runs", ["status"])
    op.create_index(op.f("ix_checkpoint_runs_id"), "checkpoint_runs", ["id"])
    op.create_index(
        op.f("ix_checkpoint_runs_created_at"), "checkpoint_runs", ["created_at"]
    )
    op.create_index(
        op.f("ix_checkpoint_runs_checkpoint_id"), "checkpoint_runs", ["checkpoint_id"]
    )
