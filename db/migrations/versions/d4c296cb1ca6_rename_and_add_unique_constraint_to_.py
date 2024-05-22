"""Rename and add unique constraint to account_name

Revision ID: d4c296cb1ca6
Revises: 038100802b26
Create Date: 2024-05-21 21:42:51.608069

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4c296cb1ca6"
down_revision: Union[str, None] = "038100802b26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the column from cognito_user_group_name to account_name
    op.alter_column(
        "accounts",
        "cognito_user_group_name",
        new_column_name="account_name",
        existing_type=sa.String(),
        nullable=False,
    )

    # Add unique constraint to account_name
    op.create_unique_constraint("uq_account_name", "accounts", ["account_name"])


def downgrade() -> None:
    # Remove unique constraint from account_name
    op.drop_constraint("uq_account_name", "accounts", type_="unique")

    # Rename the column back from account_name to cognito_user_group_name
    op.alter_column(
        "accounts",
        "account_name",
        new_column_name="cognito_user_group_name",
        existing_type=sa.String(),
        nullable=True,
    )
