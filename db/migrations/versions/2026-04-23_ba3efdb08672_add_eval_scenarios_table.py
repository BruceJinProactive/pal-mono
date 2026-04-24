"""add eval_scenarios table

Revision ID: ba3efdb08672
Revises: ee35d4d8911f
Create Date: 2026-04-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba3efdb08672"
down_revision: Union[str, None] = "ee35d4d8911f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_scenarios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("scenario_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("raw_yaml", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "name", name="uq_eval_scenarios_project_name"
        ),
    )
    op.create_index(
        "ix_eval_scenarios_id",
        "eval_scenarios",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_scenarios_project_id",
        "eval_scenarios",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_scenarios_scenario_type",
        "eval_scenarios",
        ["scenario_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eval_scenarios_scenario_type",
        table_name="eval_scenarios",
        if_exists=True,
    )
    op.drop_index(
        "ix_eval_scenarios_project_id",
        table_name="eval_scenarios",
        if_exists=True,
    )
    op.drop_index(
        "ix_eval_scenarios_id",
        table_name="eval_scenarios",
        if_exists=True,
    )
    op.drop_table("eval_scenarios")
