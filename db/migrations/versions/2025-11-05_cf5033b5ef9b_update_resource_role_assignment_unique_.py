"""update_resource_role_assignment_unique_constraint

Revision ID: cf5033b5ef9b
Revises: 312e97520412
Create Date: 2025-11-05 20:28:40.257074

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf5033b5ef9b"
down_revision: Union[str, None] = "312e97520412"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_user_resource_role", "resource_role_assignments", type_="unique"
    )
    op.create_unique_constraint(
        "uq_user_resource_role",
        "resource_role_assignments",
        ["user_id", "resource_type", "resource_id", "role"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_resource_role", "resource_role_assignments", type_="unique"
    )
    op.create_unique_constraint(
        "uq_user_resource_role",
        "resource_role_assignments",
        ["user_id", "resource_type", "resource_id"],
    )
