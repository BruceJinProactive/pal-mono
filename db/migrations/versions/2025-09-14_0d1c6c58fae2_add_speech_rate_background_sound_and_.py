"""add_speech_rate_background_sound_and_raw_config_to_voice_configs

Revision ID: 0d1c6c58fae2
Revises: c0d523a2a228
Create Date: 2025-09-14 00:42:15.151150

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0d1c6c58fae2"
down_revision: Union[str, None] = "c0d523a2a228"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reference the existing enum (do not create it again here)
speechrate = sa.Enum(
    "slowest", "slower", "normal", "faster", "fastest", name="speechrate"
)


def upgrade() -> None:
    # Add new columns to voice_configs table
    with op.batch_alter_table("voice_configs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "speech_rate",
                speechrate,
                nullable=False,
                server_default=sa.text("'normal'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "background_sound", sa.String(), nullable=False, server_default="office"
            )
        )
        batch_op.add_column(
            sa.Column(
                "raw_config",
                JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            )
        )


def downgrade() -> None:
    # Remove columns from voice_configs table
    with op.batch_alter_table("voice_configs", schema=None) as batch_op:
        batch_op.drop_column("raw_config")
        batch_op.drop_column("background_sound")
        batch_op.drop_column("speech_rate")

    # ⚠️ Do not drop `speechrate` here — it was introduced earlier
    # and might be used in other tables.
