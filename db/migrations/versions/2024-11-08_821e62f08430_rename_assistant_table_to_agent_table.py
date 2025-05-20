"""rename assistant table to agent table

Revision ID: 821e62f08430
Revises: aeb9be41b437
Create Date: 2024-11-08 21:27:00.224855

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "821e62f08430"
down_revision: Union[str, None] = "aeb9be41b437"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Rename the table from assistants to agents
    op.rename_table("assistants", "agents", schema="public")

    # Rename indexes related to the assistants table
    op.execute("ALTER INDEX ix_public_assistants_id RENAME TO ix_public_agents_id")
    op.execute(
        "ALTER INDEX ix_public_assistants_account_id RENAME TO ix_public_agents_account_id"
    )

    # Rename the assistant_id column to agent_id in the projects table
    op.alter_column(
        "projects", "assistant_id", new_column_name="agent_id", schema="public"
    )

    # Rename index for the projects table
    op.execute(
        "ALTER INDEX ix_public_projects_assistant_id RENAME TO ix_public_projects_agent_id"
    )


def downgrade():
    # Revert column renaming in projects table
    op.alter_column(
        "projects", "agent_id", new_column_name="assistant_id", schema="public"
    )

    # Revert index renaming
    op.execute(
        "ALTER INDEX ix_public_projects_agent_id RENAME TO ix_public_projects_assistant_id"
    )
    op.execute(
        "ALTER INDEX ix_public_agents_account_id RENAME TO ix_public_assistants_account_id"
    )
    op.execute("ALTER INDEX ix_public_agents_id RENAME TO ix_public_assistants_id")

    # Rename the table back to assistants
    op.rename_table("agents", "assistants", schema="public")
