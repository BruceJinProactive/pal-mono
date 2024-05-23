"""Add assistants table and relationship in projects

Revision ID: f29d88d5d714
Revises: c40b5a6e029d
Create Date: 2024-05-23 06:09:08.313064

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f29d88d5d714"
down_revision: Union[str, None] = "c40b5a6e029d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistants",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False
        ),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
    )
    op.create_index(op.f("ix_assistants_id"), "assistants", ["id"], unique=False)
    op.create_index(
        op.f("ix_assistants_project_id"), "assistants", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assistants_project_id"), table_name="assistants")
    op.drop_index(op.f("ix_assistants_id"), table_name="assistants")
    op.drop_table("assistants")
