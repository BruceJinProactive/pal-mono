"""add project status live_at

Revision ID: a6a147b427f8
Revises: e62c73367f57
Create Date: 2026-06-15 15:04:35.336890

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a6a147b427f8"
down_revision: Union[str, None] = "e62c73367f57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    project_status = postgresql.ENUM(
        "pending",
        "onboarding",
        "live",
        name="projectstatus",
    )
    project_status.create(op.get_bind())

    op.add_column(
        "projects",
        sa.Column(
            "status",
            project_status,
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_index("ix_projects_status", "projects", ["status"], unique=False)
    op.add_column(
        "projects",
        sa.Column(
            "live_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE projects SET live_at = COALESCE(created_at, now()) WHERE live_at IS NULL"
    )
    op.alter_column(
        "projects",
        "live_at",
        server_default=sa.text("now()"),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("projects", "live_at")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_column("projects", "status")

    project_status = postgresql.ENUM(
        "pending",
        "onboarding",
        "live",
        name="projectstatus",
    )
    project_status.drop(op.get_bind())
