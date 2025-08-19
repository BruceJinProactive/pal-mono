"""rename orders table to adora_orders

Revision ID: e2102dc11719
Revises: 119575fd269c
Create Date: 2025-08-19 16:24:12.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2102dc11719"
down_revision: Union[str, None] = "119575fd269c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the orders table to adora_orders
    op.rename_table("orders", "adora_orders")

    # Update the index name to match the new table name
    op.drop_index("ix_orders_id", table_name="adora_orders")
    op.create_index(op.f("ix_adora_orders_id"), "adora_orders", ["id"], unique=False)


def downgrade() -> None:
    # Revert the index name
    op.drop_index(op.f("ix_adora_orders_id"), table_name="adora_orders")
    op.create_index("ix_orders_id", "adora_orders", ["id"], unique=False)

    # Rename the table back to orders
    op.rename_table("adora_orders", "orders")
