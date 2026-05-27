"""add vision rule event default partition

Revision ID: ff69bf83de9e
Revises: 3b8d12e3664f
Create Date: 2026-05-27 11:10:03.477096

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff69bf83de9e"
down_revision: Union[str, None] = "3b8d12e3664f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE vision_rule_event_default "
        "PARTITION OF vision_rule_event DEFAULT"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vision_rule_event_default")
