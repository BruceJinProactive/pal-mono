"""add voice_model and transcriber to voice_configs

Revision ID: d8e3dc647178
Revises: e3b4fce055cc
Create Date: 2026-01-06 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8e3dc647178"
down_revision: Union[str, None] = "e3b4fce055cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_configs",
        sa.Column(
            "voice_model",
            sa.String(),
            server_default=sa.text("'sonic-2'"),
            nullable=False,
        ),
    )
    op.add_column(
        "voice_configs",
        sa.Column(
            "transcriber",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("voice_configs", "transcriber")
    op.drop_column("voice_configs", "voice_model")
