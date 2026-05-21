"""add catering request plan statuses

Revision ID: 3b8d12e3664f
Revises: 52e27731a4e4
Create Date: 2026-05-21 14:29:27.988009

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b8d12e3664f"
down_revision: Union[str, None] = "52e27731a4e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'LEAD'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'PROPOSAL'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'LOCKED'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'IN_PREPARATION'")
        op.execute("ALTER TYPE requeststatus ADD VALUE IF NOT EXISTS 'CLOSED'")


def downgrade() -> None:
    op.execute(
        "UPDATE catering_requests SET status = 'INQUIRY' "
        "WHERE status IN ('LEAD', 'PROPOSAL', 'LOCKED', 'IN_PREPARATION', 'CLOSED')"
    )
