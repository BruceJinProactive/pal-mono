"""rename transactions to orders

Revision ID: f3a4b5c6d7e8
Revises: e2102dc11719
Create Date: 2025-08-19 19:41:26.651120

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "01b994cecb12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the transactions table to orders
    op.rename_table("transactions", "orders")

    # Rename external_transaction_number to order_id (skip payment_id creation)
    op.alter_column("orders", "external_transaction_number", new_column_name="order_id")

    # Drop columns that are no longer needed
    op.drop_column("orders", "external_transaction_id")  # Don't create payment_id
    op.drop_column("orders", "project_id")
    op.drop_column("orders", "user_id")
    op.drop_column("orders", "integration_type")
    op.drop_column("orders", "table_size")
    op.drop_column("orders", "notes")  # Remove notes column

    # Update indexes
    op.drop_index("ix_transactions_id", table_name="orders")
    # Don't recreate id index - rely on primary key index

    op.drop_index("ix_transactions_conversation_id", table_name="orders")
    op.create_index(
        op.f("ix_orders_conversation_id"), "orders", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    # Revert indexes
    op.drop_index(op.f("ix_orders_conversation_id"), table_name="orders")
    op.create_index(
        "ix_transactions_conversation_id", "orders", ["conversation_id"], unique=False
    )

    # Don't recreate id index - rely on primary key index
    # (No need to drop ix_orders_id since we didn't create it)

    # Add back dropped columns
    op.add_column("orders", sa.Column("notes", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("table_size", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "integration_type",
            sa.Enum("ordering", "reservation", name="integrationtype"),
            nullable=True,
        ),
    )
    op.add_column(
        "orders",
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "project_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "orders",
        sa.Column("external_transaction_id", sa.String(), nullable=True),
    )

    # Create indexes for restored columns
    op.create_index("ix_transactions_user_id", "orders", ["user_id"], unique=False)
    op.create_index(
        "ix_transactions_project_id", "orders", ["project_id"], unique=False
    )
    op.create_index("ix_transactions_id", "orders", ["id"], unique=False)

    # Revert column renames
    op.alter_column("orders", "order_id", new_column_name="external_transaction_number")

    # Rename table back
    op.rename_table("orders", "transactions")
