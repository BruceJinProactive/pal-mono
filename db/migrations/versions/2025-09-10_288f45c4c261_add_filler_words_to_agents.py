"""add_filler_words_to_agents

Revision ID: 288f45c4c261
Revises: de4d38bb6f61
Create Date: 2025-09-10 14:07:17.470550

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "288f45c4c261"
down_revision: Union[str, None] = "de4d38bb6f61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column("agents", sa.Column("filler_words", JSONB(), nullable=True))

    # Update all existing rows with empty JSON object
    op.execute("UPDATE agents SET filler_words = '{}'::jsonb")

    # Make column non-nullable with empty default
    op.alter_column(
        "agents",
        "filler_words",
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.drop_column("agents", "filler_words")
