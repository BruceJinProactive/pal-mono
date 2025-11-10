"""add name and email columns to account_users table

Revision ID: 0bb461b2187d
Revises: e95a313d5685
Create Date: 2025-11-08 02:42:59.279293

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0bb461b2187d"
down_revision: Union[str, None] = "e95a313d5685"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "account_users", sa.Column("name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "account_users", sa.Column("email", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("account_users", "email")
    op.drop_column("account_users", "name")
