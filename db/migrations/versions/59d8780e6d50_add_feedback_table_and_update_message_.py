"""Add Feedback Table and Update Message Relationships

Revision ID: 59d8780e6d50
Revises: 821e62f08430
Create Date: 2024-11-14 06:58:40.095694

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "59d8780e6d50"
down_revision: Union[str, None] = "821e62f08430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create feedback table
    op.create_table(
        "feedback",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("author_identifier", sa.String(), nullable=True),
        sa.Column("reaction", sa.String(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
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
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public.messages.id"),
            nullable=False,
        ),
        schema="public",
    )

    # Create indexes for feedback table
    op.create_index(
        op.f("ix_public_feedback_id"), "feedback", ["id"], unique=False, schema="public"
    )
    op.create_index(
        op.f("ix_public_feedback_message_id"),
        "feedback",
        ["message_id"],
        unique=False,
        schema="public",
    )


def downgrade() -> None:
    # Drop feedback table and indexes
    op.drop_index(
        op.f("ix_public_feedback_message_id"), table_name="feedback", schema="public"
    )
    op.drop_index(op.f("ix_public_feedback_id"), table_name="feedback", schema="public")
    op.drop_table("feedback", schema="public")
