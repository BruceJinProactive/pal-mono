"""add_idempotency_key_to_catering_requests

Revision ID: 4d4688aa4682
Revises: 72e2e172a879
Create Date: 2025-10-18 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d4688aa4682"
down_revision: Union[str, None] = "72e2e172a879"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add idempotency_key column to catering_requests table
    op.add_column(
        "catering_requests",
        sa.Column(
            "idempotency_key",
            sa.String(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )

    # Add unique constraint to prevent duplicate requests (this automatically creates an index)
    op.create_unique_constraint(
        "uq_catering_requests_idempotency_key", "catering_requests", ["idempotency_key"]
    )


def downgrade() -> None:
    # Remove unique constraint (this also removes the associated index)
    op.drop_constraint(
        "uq_catering_requests_idempotency_key", "catering_requests", type_="unique"
    )

    # Remove column
    op.drop_column("catering_requests", "idempotency_key")
