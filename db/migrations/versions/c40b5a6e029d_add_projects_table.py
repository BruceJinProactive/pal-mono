"""Add projects table

Revision ID: c40b5a6e029d
Revises: 541b23a8e944
Create Date: 2024-05-23 04:53:54.622655

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c40b5a6e029d"
down_revision: Union[str, None] = "541b23a8e944"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False, server_default="default"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "account_id", sa.BigInteger(), sa.ForeignKey("accounts.id"), nullable=False
        ),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_index(
        op.f("ix_projects_account_id"), "projects", ["account_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_account_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")
