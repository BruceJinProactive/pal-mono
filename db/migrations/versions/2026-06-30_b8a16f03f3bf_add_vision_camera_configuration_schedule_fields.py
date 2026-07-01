"""add vision camera configuration check schedule fields

Revision ID: b8a16f03f3bf
Revises: 8b7c6d5e4f3a
Create Date: 2026-06-30 14:45:16.156810

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8a16f03f3bf"
down_revision: Union[str, None] = "8b7c6d5e4f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_WEEKLY_OBSERVATION_DAYS_SQL = (
    "weekly_observation_days <@ ARRAY["
    "'monday', 'tuesday', 'wednesday', 'thursday', "
    "'friday', 'saturday', 'sunday'"
    "]::varchar[]"
)

DEFAULT_WEEKLY_OBSERVATION_DAYS_SQL = (
    "ARRAY["
    "'monday', 'tuesday', 'wednesday', 'thursday', "
    "'friday', 'saturday', 'sunday'"
    "]::varchar[]"
)

CHECK_MODE_CHECK_NAME = "ck_vision_camera_configuration_check_mode_valid"
CHECK_WINDOW_REQUIRED_CHECK_NAME = (
    "ck_vision_camera_configuration_check_window_required"
)
CHECK_FREQUENCY_MINUTES_POSITIVE_CHECK_NAME = (
    "ck_vision_camera_configuration_check_frequency_minutes_positive"
)
WEEKLY_OBSERVATION_DAYS_CHECK_NAME = (
    "ck_vision_camera_configuration_weekly_observation_days_valid"
)
WEEKLY_OBSERVATION_DAYS_NONEMPTY_CHECK_NAME = (
    "ck_vision_camera_configuration_weekly_observation_days_nonempty"
)


def upgrade() -> None:
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "check_mode",
            sa.String(length=10),
            server_default=sa.text("'daily'"),
            nullable=False,
        ),
    )
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "check_start_time",
            sa.Time(),
            server_default=sa.text("'00:00:00'"),
            nullable=True,
        ),
    )
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "check_end_time",
            sa.Time(),
            server_default=sa.text("'23:59:59.999999'"),
            nullable=True,
        ),
    )
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "check_frequency_minutes",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "vision_camera_configuration",
        sa.Column(
            "weekly_observation_days",
            postgresql.ARRAY(sa.String(length=9)),
            server_default=sa.text(DEFAULT_WEEKLY_OBSERVATION_DAYS_SQL),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        CHECK_MODE_CHECK_NAME,
        "vision_camera_configuration",
        "check_mode IN ('none', 'daily', 'weekly')",
    )
    op.create_check_constraint(
        CHECK_WINDOW_REQUIRED_CHECK_NAME,
        "vision_camera_configuration",
        "check_mode = 'none' OR "
        "(check_start_time IS NOT NULL AND check_end_time IS NOT NULL)",
    )
    op.create_check_constraint(
        CHECK_FREQUENCY_MINUTES_POSITIVE_CHECK_NAME,
        "vision_camera_configuration",
        "check_frequency_minutes > 0",
    )
    op.create_check_constraint(
        WEEKLY_OBSERVATION_DAYS_CHECK_NAME,
        "vision_camera_configuration",
        VALID_WEEKLY_OBSERVATION_DAYS_SQL,
    )
    op.create_check_constraint(
        WEEKLY_OBSERVATION_DAYS_NONEMPTY_CHECK_NAME,
        "vision_camera_configuration",
        "cardinality(weekly_observation_days) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        WEEKLY_OBSERVATION_DAYS_NONEMPTY_CHECK_NAME,
        "vision_camera_configuration",
        type_="check",
    )
    op.drop_constraint(
        WEEKLY_OBSERVATION_DAYS_CHECK_NAME,
        "vision_camera_configuration",
        type_="check",
    )
    op.drop_constraint(
        CHECK_FREQUENCY_MINUTES_POSITIVE_CHECK_NAME,
        "vision_camera_configuration",
        type_="check",
    )
    op.drop_constraint(
        CHECK_WINDOW_REQUIRED_CHECK_NAME,
        "vision_camera_configuration",
        type_="check",
    )
    op.drop_constraint(
        CHECK_MODE_CHECK_NAME,
        "vision_camera_configuration",
        type_="check",
    )
    op.drop_column("vision_camera_configuration", "weekly_observation_days")
    op.drop_column("vision_camera_configuration", "check_frequency_minutes")
    op.drop_column("vision_camera_configuration", "check_end_time")
    op.drop_column("vision_camera_configuration", "check_start_time")
    op.drop_column("vision_camera_configuration", "check_mode")
