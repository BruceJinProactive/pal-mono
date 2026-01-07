"""add voice_model and transcriber columns to voice_configs db table

Revision ID: d8e3dc647178
Revises: b9c573a824df
Create Date: 2026-01-06

"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8e3dc647178"
down_revision: Union[str, None] = "b9c573a824df"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Add voice_model column with default value 'sonic-2'
    op.add_column(
        "voice_configs",
        sa.Column(
            "voice_model",
            sa.String(),
            nullable=False,
            server_default=sa.text("'sonic-2'"),
        ),
    )

    # Add transcriber column as JSONB, nullable
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
