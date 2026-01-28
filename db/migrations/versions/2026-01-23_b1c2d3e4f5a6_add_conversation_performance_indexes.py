"""add conversation performance indexes

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-01-23 10:00:00.000000

Performance optimization based on Postgres best practices audit:
- idx_conversations_status: Speeds up frequent status filtering (WHERE status != 'closed')
- idx_conversations_project_created_desc: Composite index for project-based queries with date ordering
  Uses partial index (WHERE project_id IS NOT NULL) per Postgres rule 1.5

Note: Uses CONCURRENTLY to avoid blocking writes during index creation.
Requires autocommit block since concurrent operations cannot run inside a transaction.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use autocommit block for CONCURRENTLY operations (cannot run in transaction)
    with op.get_context().autocommit_block():
        # Index on status for frequent status filtering queries
        # Common patterns: WHERE status != 'closed', WHERE status = 'active'
        op.create_index(
            "idx_conversations_status",
            "conversations",
            ["status"],
            unique=False,
            postgresql_concurrently=True,
        )

        # Composite index for project-based queries with date ordering
        # Partial index excludes NULL project_ids (historical data) for smaller index size
        # Supports: WHERE project_id = X ORDER BY created_at DESC
        op.create_index(
            "idx_conversations_project_created_desc",
            "conversations",
            [sa.text("project_id"), sa.text("created_at DESC")],
            unique=False,
            postgresql_where=sa.text("project_id IS NOT NULL"),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    # Use autocommit block for CONCURRENTLY operations (cannot run in transaction)
    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_conversations_project_created_desc",
            table_name="conversations",
            postgresql_concurrently=True,
        )
        op.drop_index(
            "idx_conversations_status",
            table_name="conversations",
            postgresql_concurrently=True,
        )
