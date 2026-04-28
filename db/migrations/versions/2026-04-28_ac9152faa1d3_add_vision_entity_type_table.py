"""add vision_entity_type table

Revision ID: ac9152faa1d3
Revises: ba3efdb08672
Create Date: 2026-04-28 11:42:41.435626

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac9152faa1d3"
down_revision: Union[str, None] = "ba3efdb08672"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_entity_type",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=10), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.UniqueConstraint("account_id", "name"),
    )
    op.create_index(
        op.f("ix_vision_entity_type_account_id"),
        "vision_entity_type",
        ["account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_vision_entity_type_account_id"), table_name="vision_entity_type"
    )
    op.drop_table("vision_entity_type")
