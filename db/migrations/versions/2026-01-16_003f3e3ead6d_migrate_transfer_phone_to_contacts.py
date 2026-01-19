"""Migrate transfer_phone_number to contacts table

Revision ID: 003f3e3ead6d
Revises: 58a96ada96f2
Create Date: 2026-01-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003f3e3ead6d"
down_revision: Union[str, None] = "58a96ada96f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Data migration: Copy transfer_phone_number from projects to contacts table
    # Creates a contact with role='general' for each project that has transfer_phone_number set
    # and doesn't already have a 'general' role contact linked

    # Step 1: Insert contacts for projects with transfer_phone_number
    op.execute(
        """
        INSERT INTO contacts (id, name, phone_number, role, email, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            p.name || ' - General Transfer',
            p.transfer_phone_number,
            'general',
            NULL,
            NOW(),
            NOW()
        FROM projects p
        WHERE p.transfer_phone_number IS NOT NULL
          AND p.transfer_phone_number != ''
          AND NOT EXISTS (
            SELECT 1
            FROM project_contacts pc
            JOIN contacts c ON c.id = pc.contact_id
            WHERE pc.project_id = p.id AND c.role = 'general'
          )
        """
    )

    # Step 2: Link the newly created contacts to their projects
    op.execute(
        """
        INSERT INTO project_contacts (id, project_id, contact_id, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            p.id,
            c.id,
            NOW(),
            NOW()
        FROM projects p
        JOIN contacts c ON c.phone_number = p.transfer_phone_number
                       AND c.role = 'general'
                       AND c.name = p.name || ' - General Transfer'
        WHERE p.transfer_phone_number IS NOT NULL
          AND p.transfer_phone_number != ''
          AND NOT EXISTS (
            SELECT 1
            FROM project_contacts pc
            WHERE pc.project_id = p.id AND pc.contact_id = c.id
          )
        """
    )


def downgrade() -> None:
    # Remove project_contacts links for migrated contacts
    op.execute(
        """
        DELETE FROM project_contacts
        WHERE contact_id IN (
            SELECT c.id
            FROM contacts c
            WHERE c.role = 'general'
              AND c.name LIKE '% - General Transfer'
        )
        """
    )

    # Remove the migrated contacts
    op.execute(
        """
        DELETE FROM contacts
        WHERE role = 'general'
          AND name LIKE '% - General Transfer'
        """
    )
