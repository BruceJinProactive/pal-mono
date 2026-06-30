"""add structured_observations_enabled to vision camera config

Revision ID: 8b7c6d5e4f3a
Revises: f2fc2243cb69
Create Date: 2026-06-26 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b7c6d5e4f3a"
down_revision: Union[str, None] = "f2fc2243cb69"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "structured_observations_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("vision_camera_configuration", "structured_observations_enabled")
