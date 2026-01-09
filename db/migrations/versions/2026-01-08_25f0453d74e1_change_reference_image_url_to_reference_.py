"""change_reference_image_url_to_reference_images_list

Revision ID: 25f0453d74e1
Revises: 13262616703e
Create Date: 2026-01-08 17:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "25f0453d74e1"
down_revision: Union[str, None] = "13262616703e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change reference_image_url (String) to reference_images (JSONB list of dicts).

    Migration strategy:
    1. Add new reference_images column as JSONB list
    2. Migrate data: Convert reference_image_url to reference_images list format
    3. Drop old reference_image_url column
    """
    # Add new reference_images column as a JSONB list
    op.add_column(
        "routine_items",
        sa.Column(
            "reference_images",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="List of dicts with 'image_url' and 'description' fields",
        ),
    )

    # Migrate existing data: if reference_image_url exists, convert to list format
    # Wrap the old string URL in a dict, then wrap that dict in a list
    op.execute(
        """
        UPDATE routine_items
        SET reference_images = jsonb_build_array(
            jsonb_build_object(
                'image_url', reference_image_url,
                'description', ''
            )
        )
        WHERE reference_image_url IS NOT NULL AND reference_image_url != ''
        """
    )

    # Drop old column
    op.drop_column("routine_items", "reference_image_url")


def downgrade() -> None:
    """
    Revert reference_images (JSONB list) back to reference_image_url (String).

    Note: This will lose the description field and all but the first image.
    """
    # Add back reference_image_url column
    op.add_column(
        "routine_items",
        sa.Column("reference_image_url", sa.String(length=500), nullable=True),
    )

    # Migrate data back: extract first image_url from reference_images list
    op.execute(
        """
        UPDATE routine_items
        SET reference_image_url = reference_images->0->>'image_url'
        WHERE reference_images IS NOT NULL
        AND jsonb_typeof(reference_images) = 'array'
        AND jsonb_array_length(reference_images) > 0
        AND reference_images->0->>'image_url' IS NOT NULL
        """
    )

    # Drop new column
    op.drop_column("routine_items", "reference_images")
