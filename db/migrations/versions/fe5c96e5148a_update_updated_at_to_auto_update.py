"""Update updated_at to auto-update

Revision ID: fe5c96e5148a
Revises: f29d88d5d714
Create Date: 2024-05-23 16:18:00.352112

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe5c96e5148a"
down_revision: Union[str, None] = "f29d88d5d714"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=True,
        onupdate=sa.func.now(),
    )

    op.alter_column(
        "projects",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=True,
        onupdate=sa.func.now(),
    )
    op.alter_column(
        "assistants",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=True,
        onupdate=sa.func.now(),
    )


def downgrade() -> None:
    op.alter_column(
        "accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=True,
        onupdate=None,
    )
    op.alter_column(
        "projects",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=True,
        onupdate=None,
    )
    op.alter_column(
        "assistants",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=True,
        onupdate=None,
    )
