"""Add Stripe subscription statuses to SubscriptionStatus enum

Revision ID: ab66d7ed80fe
Revises: ac7b97cb0df5
Create Date: 2025-12-24 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab66d7ed80fe"
down_revision: Union[str, None] = "ac7b97cb0df5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add trialing, past_due, unpaid to SubscriptionStatus enum
    # Using IF NOT EXISTS to make migration idempotent (safe to re-run)
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'trialing'")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'past_due'")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'unpaid'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # This migration is non-reversible by design.
    pass
