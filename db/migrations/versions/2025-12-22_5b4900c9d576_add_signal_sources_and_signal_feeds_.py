"""add signal_sources and signal_feeds tables

Revision ID: 5b4900c9d576
Revises: 24e88c4e029f
Create Date: 2025-12-22 15:26:13.518456

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5b4900c9d576"
down_revision: Union[str, None] = "24e88c4e029f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column(
            "signal_type",
            sa.Enum("camera", name="signaltype"),
            server_default=sa.text("'camera'"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "error", name="signalsourcestatus"),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
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
    )
    op.create_table(
        "signal_feeds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column(
            "feed_type",
            sa.Enum("image_snapshot", "video_stream", name="feedtype"),
            nullable=False,
        ),
        sa.Column(
            "capture_mode", sa.Enum("pull", "push", name="capturemode"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("active", "paused", "error", name="signalfeedstatus"),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("last_capture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "capture_count", sa.Integer(), server_default=sa.text("0"), nullable=False
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
    )


def downgrade() -> None:
    op.drop_table("signal_feeds")
    op.drop_table("signal_sources")
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS signalsourcestatus")
    op.execute("DROP TYPE IF EXISTS signaltype")
    op.execute("DROP TYPE IF EXISTS signalfeedstatus")
    op.execute("DROP TYPE IF EXISTS feedtype")
    op.execute("DROP TYPE IF EXISTS capturemode")
