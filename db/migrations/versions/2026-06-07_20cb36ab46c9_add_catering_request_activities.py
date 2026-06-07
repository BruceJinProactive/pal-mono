"""add catering request activities

Revision ID: 20cb36ab46c9
Revises: d27a86f44484
Create Date: 2026-06-07 12:16:15.895033

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20cb36ab46c9"
down_revision: Union[str, None] = "d27a86f44484"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catering_request_activities",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("catering_request_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "activity_type",
            sa.Enum(
                "REQUEST_CREATED",
                "REQUEST_UPDATED",
                "STATUS_CHANGED",
                "ACTION_ITEM_COMPLETED",
                "ACTION_ITEM_REOPENED",
                "PROPOSAL_CREATED",
                "PROPOSAL_SENT",
                "PROPOSAL_APPROVED",
                "SMS_SENT",
                "SMS_RECEIVED",
                "PAYMENT_RECEIVED",
                "NOTE_ADDED",
                "DEADLINE_SCHEDULED",
                "ORDER_LOCKED",
                "TOAST_ORDER_CREATED",
                name="cateringrequestactivitytype",
            ),
            nullable=False,
        ),
        sa.Column(
            "actor_type",
            sa.Enum(
                "CUSTOMER",
                "CATERING_MANAGER",
                "INTERNAL_USER",
                "SYSTEM",
                "AI_AGENT",
                "INTEGRATION",
                name="cateringrequestactivityactortype",
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_display_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "ADMIN_CONSOLE",
                "CUSTOMER_SMS",
                "SYSTEM_JOB",
                "AI_AGENT",
                "TOAST",
                "API",
                name="cateringrequestactivitysource",
            ),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_catering_request_activities_actor",
        "catering_request_activities",
        ["actor_type", "actor_id"],
        unique=False,
    )
    op.create_index(
        "idx_catering_request_activities_project_time",
        "catering_request_activities",
        ["project_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "idx_catering_request_activities_request_time",
        "catering_request_activities",
        ["catering_request_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catering_request_activities_actor_id"),
        "catering_request_activities",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catering_request_activities_catering_request_id"),
        "catering_request_activities",
        ["catering_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catering_request_activities_id"),
        "catering_request_activities",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_catering_request_activities_project_id"),
        "catering_request_activities",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_catering_request_activities_project_id"),
        table_name="catering_request_activities",
    )
    op.drop_index(
        op.f("ix_catering_request_activities_id"),
        table_name="catering_request_activities",
    )
    op.drop_index(
        op.f("ix_catering_request_activities_catering_request_id"),
        table_name="catering_request_activities",
    )
    op.drop_index(
        op.f("ix_catering_request_activities_actor_id"),
        table_name="catering_request_activities",
    )
    op.drop_index(
        "idx_catering_request_activities_request_time",
        table_name="catering_request_activities",
    )
    op.drop_index(
        "idx_catering_request_activities_project_time",
        table_name="catering_request_activities",
    )
    op.drop_index(
        "idx_catering_request_activities_actor",
        table_name="catering_request_activities",
    )
    op.drop_table("catering_request_activities")
    op.execute("DROP TYPE IF EXISTS cateringrequestactivitysource")
    op.execute("DROP TYPE IF EXISTS cateringrequestactivityactortype")
    op.execute("DROP TYPE IF EXISTS cateringrequestactivitytype")
