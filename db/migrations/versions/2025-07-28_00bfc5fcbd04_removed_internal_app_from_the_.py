"""Remove internal_app from Channel enum

Revision ID: 00bfc5fcbd04
Revises: 9a6f6f3ef3cf
Create Date: 2025-07-28 16:07:01.130296

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "00bfc5fcbd04"
down_revision: Union[str, None] = "9a6f6f3ef3cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove 'internal_app' from the channel enum
    # PostgreSQL doesn't allow direct removal of enum values, so we need to:
    # 1. Create a new enum with the desired values
    # 2. Update any existing columns that use this enum
    # 3. Replace the old enum with the new one

    # Create new channel enum without 'internal_app'
    op.execute(
        "CREATE TYPE channel_new AS ENUM ('api', 'instagram', 'sms', 'voice', 'whatsapp')"
    )

    # Update any existing columns that use the channel enum
    # Note: If there are tables using this enum, add the ALTER TABLE statements here
    # For example: op.execute("ALTER TABLE your_table ALTER COLUMN your_column TYPE channel_new USING your_column::text::channel_new")

    # Replace the old enum with the new one
    op.execute("DROP TYPE IF EXISTS channel")
    op.execute("ALTER TYPE channel_new RENAME TO channel")


def downgrade() -> None:
    # Restore 'internal_app' to the channel enum
    op.execute(
        "CREATE TYPE channel_new AS ENUM ('api', 'instagram', 'internal_app', 'sms', 'voice', 'whatsapp')"
    )

    # Update any existing columns back to the old enum
    # Note: Add corresponding ALTER TABLE statements here if needed

    # Replace with the old enum that includes 'internal_app'
    op.execute("DROP TYPE IF EXISTS channel")
    op.execute("ALTER TYPE channel_new RENAME TO channel")
