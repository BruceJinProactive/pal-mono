"""add vision_rule table

Revision ID: daceb91f0ce4
Revises: 5ca029ff7265
Create Date: 2026-05-20 12:58:00.465626

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "daceb91f0ce4"
down_revision: Union[str, None] = "5ca029ff7265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE visionruletype AS ENUM ('table_cleanness')")
    op.execute(
        """
        CREATE TABLE vision_rule (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            type visionruletype NOT NULL,
            severity VARCHAR(20) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            rule_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """
    )
    op.create_index(
        op.f("ix_vision_rule_project_id"), "vision_rule", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vision_rule_project_id"), table_name="vision_rule")
    op.drop_table("vision_rule")
    op.execute("DROP TYPE IF EXISTS visionruletype")
