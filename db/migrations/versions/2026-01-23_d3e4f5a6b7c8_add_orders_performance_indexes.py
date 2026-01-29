"""add orders performance indexes

Revision ID: d3e4f5a6b7c8
Revises: b1c2d3e4f5a6
Create Date: 2026-01-23 12:00:00.000000

Performance optimization based on Postgres best practices audit:
- idx_orders_vendor_store: Composite index for vendor+store_id lookups
- idx_orders_status: Index for status filtering (e.g., exclude pending orders)
- idx_orders_order_time: Index for date range queries on order_time

Common query patterns these indexes optimize:
- get_order_by_vendor_and_store_id (vendor + store_id equality)
- get_order_value (order_time range + status filtering)
- get_order_conversation_counts_by_account (status filtering)

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for vendor + store_id lookups
    # Used by: get_order_by_vendor_and_store_id, get_orders_by_vendor_and_store_id
    op.create_index(
        "idx_orders_vendor_store",
        "orders",
        ["vendor", "store_id"],
        unique=False,
    )

    # Index for status filtering
    # Used by: get_order_value (status != 'pending'), get_order_conversation_counts
    op.create_index(
        "idx_orders_status",
        "orders",
        ["status"],
        unique=False,
    )

    # Index for order_time date range queries
    # Used by: get_order_value, get_order_conversation_counts_by_account
    op.create_index(
        "idx_orders_order_time",
        "orders",
        ["order_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_orders_order_time", table_name="orders")
    op.drop_index("idx_orders_status", table_name="orders")
    op.drop_index("idx_orders_vendor_store", table_name="orders")
