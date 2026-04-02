"""add_pronunciation_dict_id_to_voice_configs

Revision ID: 30f17b410e14
Revises: 00bdc822b20e
Create Date: 2026-04-02 00:48:46.930562

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30f17b410e14"
down_revision: Union[str, None] = "00bdc822b20e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_configs",
        sa.Column("pronunciation_dict_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("voice_configs", "pronunciation_dict_id")
