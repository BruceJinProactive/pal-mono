"""add google business hours to projects

Revision ID: 4019e4683033
Revises: e5e6d03f576
Create Date: 2025-11-13 17:36:49.836724

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4019e4683033"
down_revision: Union[str, None] = "e5e6d03f576"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("google_place_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "projects",
        sa.Column(
            "business_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "business_hours_last_updated", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # Add indexes for Google Business Hours fields
    op.create_index(
        "idx_projects_google_place_id",
        "projects",
        ["google_place_id"],
        postgresql_where=sa.text("google_place_id IS NOT NULL"),
    )
    op.create_index(
        "idx_projects_business_hours_last_updated",
        "projects",
        ["business_hours_last_updated"],
        postgresql_where=sa.text("google_place_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("idx_projects_business_hours_last_updated", table_name="projects")
    op.drop_index("idx_projects_google_place_id", table_name="projects")

    op.drop_column("projects", "business_hours_last_updated")
    op.drop_column("projects", "business_hours")
    op.drop_column("projects", "google_place_id")
