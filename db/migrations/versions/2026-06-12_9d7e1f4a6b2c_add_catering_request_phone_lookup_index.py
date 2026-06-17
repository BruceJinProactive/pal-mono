"""add catering request phone lookup index

Revision ID: 9d7e1f4a6b2c
Revises: a6a147b427f8
Create Date: 2026-06-12 10:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d7e1f4a6b2c"
down_revision: Union[str, None] = "a6a147b427f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_catering_requests_project_phone_digits_created_at"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                "ON catering_requests ("
                "project_id, "
                "(regexp_replace(coalesce(contact_phone_number, ''), '\\D', '', 'g')), "
                "created_at DESC"
                ")"
            )
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"))
