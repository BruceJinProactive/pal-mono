"""add_waitlist_fields_to_reservations

Revision ID: 4937ffff306a
Revises: 25f0453d74e1
Create Date: 2026-01-09 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4937ffff306a"
down_revision: Union[str, None] = "25f0453d74e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add waitlist tracking fields to reservations table
    op.add_column(
        "reservations",
        sa.Column(
            "entry_type",
            sa.String(length=20),
            server_default=sa.text("'reservation'"),
            nullable=False,
        ),
    )
    op.add_column(
        "reservations",
        sa.Column("arrive_by_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("expected_seating_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_reservations_entry_type"), "reservations", ["entry_type"], unique=False
    )


def downgrade() -> None:
    # Remove waitlist tracking fields from reservations table
    op.drop_index(op.f("ix_reservations_entry_type"), table_name="reservations")
    op.drop_column("reservations", "expected_seating_time")
    op.drop_column("reservations", "arrive_by_time")
    op.drop_column("reservations", "entry_type")
