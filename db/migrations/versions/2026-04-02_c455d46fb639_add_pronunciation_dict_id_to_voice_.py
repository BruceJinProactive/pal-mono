"""add_pronunciation_dict_id_to_voice_configs

Revision ID: c455d46fb639
Revises: 9b3b68035ed2
Create Date: 2026-04-02 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c455d46fb639"
down_revision: Union[str, None] = "9b3b68035ed2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_configs",
        sa.Column("pronunciation_dict_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("voice_configs", "pronunciation_dict_id")
