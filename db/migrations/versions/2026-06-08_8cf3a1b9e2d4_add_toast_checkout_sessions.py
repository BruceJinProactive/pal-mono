"""add toast checkout sessions

Revision ID: 8cf3a1b9e2d4
Revises: 4caa090da0f5
Create Date: 2026-06-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8cf3a1b9e2d4"
down_revision: Union[str, None] = "4caa090da0f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "toast_checkout_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("token", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("external_reference_id", sa.String(), nullable=False),
        sa.Column("order_external_id", sa.String(), nullable=False),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "session_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("checkout_url", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'ready'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_reference_id",
            name="uq_toast_checkout_sessions_external_reference_id",
        ),
        sa.UniqueConstraint("token", name="uq_toast_checkout_sessions_token"),
    )
    op.create_index(
        "idx_toast_checkout_sessions_conversation",
        "toast_checkout_sessions",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "idx_toast_checkout_sessions_order_external_id",
        "toast_checkout_sessions",
        ["order_external_id"],
        unique=False,
    )
    op.create_index(
        "idx_toast_checkout_sessions_expires_at",
        "toast_checkout_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_toast_checkout_sessions_expires_at",
        table_name="toast_checkout_sessions",
    )
    op.drop_index(
        "idx_toast_checkout_sessions_order_external_id",
        table_name="toast_checkout_sessions",
    )
    op.drop_index(
        "idx_toast_checkout_sessions_conversation",
        table_name="toast_checkout_sessions",
    )
    op.drop_table("toast_checkout_sessions")
