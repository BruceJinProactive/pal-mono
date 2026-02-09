from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime

from .base import Base
from .types import OnboardingStatus


class OnboardingWebhookEvent(Base):
    __tablename__ = "onboarding_webhook_events"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Source and extracted webhook fields
    src: Mapped[str] = mapped_column(
        String(), nullable=False
    )  # "toast", "square", etc.
    restaurant_guid: Mapped[str] = mapped_column(String(), nullable=False, index=True)

    # Creator information (from webhook)
    created_by_first_name: Mapped[str | None] = mapped_column(String(), nullable=True)
    created_by_last_name: Mapped[str | None] = mapped_column(String(), nullable=True)
    created_by_email_address: Mapped[str | None] = mapped_column(
        String(), nullable=True
    )
    created_by_phone_number: Mapped[str | None] = mapped_column(String(), nullable=True)

    # Restaurant contact
    restaurant_phone_number: Mapped[str | None] = mapped_column(String(), nullable=True)

    # Full webhook payload
    extra: Mapped[dict] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )

    # Multi-tenant (nullable - backfilled after account/project created)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Processing state
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        Enum(OnboardingStatus),
        nullable=False,
        default=OnboardingStatus.pending,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
