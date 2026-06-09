"""add order idempotency key

Revision ID: e47857895e0f
Revises: 8cf3a1b9e2d4
Create Date: 2026-05-31 15:41:42.449166

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e47857895e0f"
down_revision: Union[str, None] = "8cf3a1b9e2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("idempotency_key", sa.String(), nullable=True))

    # Backfill the newest canonical row per external order identity. Historical
    # duplicates intentionally keep NULL so this migration can run before cleanup.
    op.execute(
        sa.text(
            """
            WITH canonical_orders AS (
                SELECT
                    id,
                    'order:external:v1:'
                        || vendor::text
                        || ':'
                        || replace(
                            replace(btrim(store_id), chr(92), chr(92) || chr(92)),
                            ':',
                            chr(92) || ':'
                        )
                        || ':'
                        || replace(
                            replace(btrim(order_id), chr(92), chr(92) || chr(92)),
                            ':',
                            chr(92) || ':'
                        ) AS canonical_idempotency_key,
                    row_number() OVER (
                        PARTITION BY vendor, btrim(store_id), btrim(order_id)
                        ORDER BY created_at DESC, id DESC
                    ) AS row_number
                FROM orders
                WHERE vendor IS NOT NULL
                    AND store_id IS NOT NULL
                    AND order_id IS NOT NULL
                    AND btrim(store_id) <> ''
                    AND btrim(order_id) <> ''
            )
            UPDATE orders
            SET idempotency_key = canonical_orders.canonical_idempotency_key
            FROM canonical_orders
            WHERE orders.id = canonical_orders.id
                AND canonical_orders.row_number = 1
            """
        )
    )

    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
                    "ix_orders_idempotency_key_unique "
                    "ON orders (idempotency_key) "
                    "WHERE idempotency_key IS NOT NULL"
                )
            )
    except AttributeError:
        op.create_index(
            "ix_orders_idempotency_key_unique",
            "orders",
            ["idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    try:
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(
                    "DROP INDEX CONCURRENTLY IF EXISTS "
                    "ix_orders_idempotency_key_unique"
                )
            )
    except AttributeError:
        op.drop_index("ix_orders_idempotency_key_unique", table_name="orders")

    op.drop_column("orders", "idempotency_key")
