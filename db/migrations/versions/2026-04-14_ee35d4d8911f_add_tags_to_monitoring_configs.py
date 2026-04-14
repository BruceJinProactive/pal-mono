"""add tags column to monitoring_configs

Revision ID: ee35d4d8911f
Revises: 20ca2b357e47
Create Date: 2026-04-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "ee35d4d8911f"
down_revision: Union[str, None] = "20ca2b357e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitoring_configs",
        sa.Column(
            "tags",
            ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_monitoring_configs_tags",
        "monitoring_configs",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_monitoring_configs_tags", table_name="monitoring_configs")
    op.drop_column("monitoring_configs", "tags")
