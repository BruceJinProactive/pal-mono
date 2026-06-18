"""add catering request activity sources

Revision ID: a91c4f2e8b7d
Revises: a4d9c8e7b6a5
Create Date: 2026-06-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a91c4f2e8b7d"
down_revision: Union[str, None] = "a4d9c8e7b6a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE cateringrequestactivitysource ADD VALUE IF NOT EXISTS "
        "'CUSTOMER_EMAIL'"
    )
    op.execute(
        "ALTER TYPE cateringrequestactivitysource ADD VALUE IF NOT EXISTS "
        "'CUSTOMER_VOICE'"
    )
    op.execute(
        "ALTER TYPE cateringrequestactivitysource ADD VALUE IF NOT EXISTS "
        "'INTERNAL_APP'"
    )


def downgrade() -> None:
    pass
