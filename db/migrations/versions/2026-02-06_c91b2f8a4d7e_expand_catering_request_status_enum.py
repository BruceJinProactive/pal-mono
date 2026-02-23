"""Expand catering request statuses

Revision ID: c91b2f8a4d7e
Revises: 3c9d4f8b2e1a
Create Date: 2026-02-06 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c91b2f8a4d7e"
down_revision: Union[str, None] = "3c9d4f8b2e1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new values
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'INQUIRY'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'QUOTE_SENT'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'IN_PREP'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'READY'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'FULFILLED'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'ISSUE'")

    # Migrate legacy values to the new naming.
    op.execute(
        "UPDATE catering_requests SET status = 'INQUIRY' WHERE status = 'PENDING'"
    )
    op.execute(
        "UPDATE catering_requests SET status = 'FULFILLED' WHERE status = 'COMPLETED'"
    )

    # New requests should start as INQUIRY.
    op.execute(
        "ALTER TABLE catering_requests "
        "ALTER COLUMN status SET DEFAULT 'INQUIRY'::requeststatus"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely once added.
    # Map values back to legacy statuses so older app code can keep running.
    op.execute(
        "UPDATE catering_requests SET status = 'PENDING' WHERE status = 'INQUIRY'"
    )
    op.execute(
        "UPDATE catering_requests SET status = 'PENDING' "
        "WHERE status IN ('QUOTE_SENT', 'ISSUE')"
    )
    op.execute(
        "UPDATE catering_requests SET status = 'CONFIRMED' "
        "WHERE status IN ('IN_PREP', 'READY')"
    )
    op.execute(
        "UPDATE catering_requests SET status = 'COMPLETED' WHERE status = 'FULFILLED'"
    )

    op.execute(
        "ALTER TABLE catering_requests "
        "ALTER COLUMN status SET DEFAULT 'PENDING'::requeststatus"
    )
