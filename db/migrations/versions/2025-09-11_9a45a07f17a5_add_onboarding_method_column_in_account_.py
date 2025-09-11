"""add onboarding method column in account table

Revision ID: 9a45a07f17a5
Revises: 288f45c4c261
Create Date: 2025-09-11 21:15:22.829380

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a45a07f17a5"
down_revision: Union[str, None] = "288f45c4c261"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    onboarding_method_enum = sa.Enum(
        "self_onboarding", "manage_onboarding", name="onboardingmethod"
    )
    onboarding_method_enum.create(op.get_bind())

    # Then add the column using the enum
    op.add_column(
        "accounts",
        sa.Column(
            "onboarding_method",
            onboarding_method_enum,
            server_default="manage_onboarding",
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Drop the column first
    op.drop_column("accounts", "onboarding_method")

    # Then drop the enum type
    sa.Enum(name="onboardingmethod").drop(op.get_bind())
