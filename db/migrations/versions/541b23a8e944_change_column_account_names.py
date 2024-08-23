"""Change column account names

Revision ID: 541b23a8e944
Revises: d4c296cb1ca6
Create Date: 2024-05-23 04:33:47.093081

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "541b23a8e944"
down_revision: Union[str, None] = "d4c296cb1ca6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("accounts", "account_id", new_column_name="id")
    op.alter_column("accounts", "account_name", new_column_name="name")


def downgrade() -> None:
    op.alter_column("accounts", "id", new_column_name="account_id")
    op.alter_column("accounts", "name", new_column_name="account_name")
