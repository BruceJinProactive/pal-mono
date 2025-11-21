"""add minitable and resy to integrationprovider enum

Revision ID: d0cf4b215638
Revises: 4019e4683033
Create Date: 2025-11-21 07:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0cf4b215638"
down_revision: Union[str, None] = "4019e4683033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new providers to the existing integrationprovider enum
    op.execute("ALTER TYPE integrationprovider ADD VALUE IF NOT EXISTS 'minitable'")
    op.execute("ALTER TYPE integrationprovider ADD VALUE IF NOT EXISTS 'resy'")


def downgrade() -> None:
    # Enum value removal is not supported in PostgreSQL without recreating the type.
    # This downgrade is intentionally left empty.
    pass
