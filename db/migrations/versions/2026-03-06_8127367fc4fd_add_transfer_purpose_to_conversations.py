"""add_transfer_purpose_to_conversations

Revision ID: 8127367fc4fd
Revises: c91b2f8a4d7e
Create Date: 2026-03-06 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8127367fc4fd"
down_revision: Union[str, None] = "c91b2f8a4d7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "transfer_purpose",
            sa.String(),
            nullable=True,
            comment="Reason for transferring call to human (from call_transfer tool)",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "transfer_purpose")
