"""add index

Revision ID: 72d513c4bfcd
Revises: f214ca5fb318
Create Date: 2025-09-02 19:36:01.911144
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "72d513c4bfcd"
down_revision: Union[str, None] = "f214ca5fb318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Run CONCURRENTLY outside a transaction
    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_conversations_created_at "
                    "ON conversations (created_at)"
                )
            )
            op.execute(
                sa.text(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_created_at "
                    "ON orders (created_at)"
                )
            )
            op.execute(
                sa.text(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phone_calls_created_at "
                    "ON phone_calls (created_at)"
                )
            )
    except AttributeError:
        # Fallback: Use regular index creation if autocommit_block not available
        op.create_index("ix_conversations_created_at", "conversations", ["created_at"])
        op.create_index("ix_orders_created_at", "orders", ["created_at"])
        op.create_index("ix_phone_calls_created_at", "phone_calls", ["created_at"])


def downgrade() -> None:
    # Drop concurrently outside a transaction
    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text("DROP INDEX CONCURRENTLY IF EXISTS ix_phone_calls_created_at")
            )
            op.execute(
                sa.text("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_created_at")
            )
            op.execute(
                sa.text("DROP INDEX CONCURRENTLY IF EXISTS ix_conversations_created_at")
            )
    except AttributeError:
        # Fallback: Use regular index drop if autocommit_block not available
        op.drop_index("ix_phone_calls_created_at", table_name="phone_calls")
        op.drop_index("ix_orders_created_at", table_name="orders")
        op.drop_index("ix_conversations_created_at", table_name="conversations")
