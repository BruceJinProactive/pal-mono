"""merge orders and subscription branches

Revision ID: 02b3bdabb2e9
Revises: abcfc2079f4a, f3e2846498ee
Create Date: 2025-06-18 15:01:42.174962

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "02b3bdabb2e9"
down_revision: Union[str, Sequence[str], None] = ("abcfc2079f4a", "f3e2846498ee")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
