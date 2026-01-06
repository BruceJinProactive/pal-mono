"""add_channel_to_conversations

Revision ID: b9c573a824df
Revises: e3b4fce055cc
Create Date: 2026-01-06 09:06:08.816791

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c573a824df"
down_revision: Union[str, None] = "e3b4fce055cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

channel_enum = sa.Enum(
    "api",
    "email",
    "instagram",
    "internal_app",
    "sms",
    "voice",
    "whatsapp",
    name="channel",
)


def upgrade() -> None:
    channel_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("conversations", sa.Column("channel", channel_enum, nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "channel")
    op.execute(sa.text("DROP TYPE IF EXISTS channel"))
