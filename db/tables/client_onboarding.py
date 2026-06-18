from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Integer, String, Text

from .base import Base


class ClientOnboardingStatus(str, enum.Enum):
    contract_prepared = "contract_prepared"
    account_created = "account_created"
    invite_sent = "invite_sent"
    invite_opened = "invite_opened"
    docusign_viewed = "docusign_viewed"
    docusign_signed = "docusign_signed"
    password_set = "password_set"
    handoff_created = "handoff_created"
    activation_ready = "activation_ready"
    blocked = "blocked"
    cancelled = "cancelled"


class ClientOnboardingContractType(str, enum.Enum):
    order_form_tos = "order_form_tos"
    order_form_msa = "order_form_msa"


class ClientOnboardingActorType(str, enum.Enum):
    client = "client"
    ae = "ae"
    fde = "fde"
    system = "system"
    webhook = "webhook"


class ClientOnboardingActivitySource(str, enum.Enum):
    manage_app = "manage_app"
    admin_console = "admin_console"
    docusign = "docusign"
    folk = "folk"
    slack = "slack"
    notion = "notion"
    system_job = "system_job"
    api = "api"


class ClientOnboardingSyncTarget(str, enum.Enum):
    database = "database"
    docusign = "docusign"
    folk = "folk"
    slack = "slack"
    notion = "notion"
    manage_app = "manage_app"
    admin_console = "admin_console"


class ClientOnboardingSyncJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ClientOnboardingLifecycle(Base):
    __tablename__ = "client_onboarding_lifecycles"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_client_onboarding_lifecycles_idempotency_key",
        ),
        Index(
            "idx_client_onboarding_lifecycles_account_signer",
            "account_id",
            "signer_email",
        ),
        Index(
            "idx_client_onboarding_lifecycles_order_form",
            "order_form_id",
        ),
        Index(
            "idx_client_onboarding_lifecycles_docusign_envelope",
            "docusign_envelope_id",
        ),
        Index("idx_client_onboarding_lifecycles_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    manage_app_account_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    order_form_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    client_company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contract_type: Mapped[ClientOnboardingContractType] = mapped_column(
        Enum(ClientOnboardingContractType), nullable=False
    )
    docusign_contract_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    docusign_envelope_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    docusign_contract_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    invite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    ae_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    fde_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    folk_company_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    folk_contact_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    slack_channel_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    notion_page_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    scoping_doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    signer_scope_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'account'")
    )
    signer_scope_metadata: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[ClientOnboardingStatus] = mapped_column(
        Enum(ClientOnboardingStatus),
        nullable=False,
        server_default=ClientOnboardingStatus.contract_prepared.value,
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_prepared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    account_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invite_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invite_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    docusign_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    docusign_signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    handoff_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activation_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=func.now(),
    )


class ClientOnboardingActivity(Base):
    __tablename__ = "client_onboarding_activity"
    __table_args__ = (
        Index(
            "idx_client_onboarding_activity_lifecycle_time",
            "lifecycle_id",
            "occurred_at",
        ),
        Index(
            "idx_client_onboarding_activity_actor",
            "actor_type",
            "actor_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
        index=True,
    )
    lifecycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_status: Mapped[ClientOnboardingStatus | None] = mapped_column(
        Enum(ClientOnboardingStatus), nullable=True
    )
    next_status: Mapped[ClientOnboardingStatus | None] = mapped_column(
        Enum(ClientOnboardingStatus), nullable=True
    )
    actor_type: Mapped[ClientOnboardingActorType] = mapped_column(
        Enum(ClientOnboardingActorType), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[ClientOnboardingActivitySource] = mapped_column(
        Enum(ClientOnboardingActivitySource), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_diff: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    activity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ClientOnboardingSyncJob(Base):
    __tablename__ = "client_onboarding_sync_jobs"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_client_onboarding_sync_jobs_idempotency_key",
        ),
        Index(
            "idx_client_onboarding_sync_jobs_claim",
            "status",
            "target",
            "available_at",
            "created_at",
        ),
        Index(
            "idx_client_onboarding_sync_jobs_lifecycle_target",
            "lifecycle_id",
            "target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
        index=True,
    )
    lifecycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    target: Mapped[ClientOnboardingSyncTarget] = mapped_column(
        Enum(ClientOnboardingSyncTarget), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    status: Mapped[ClientOnboardingSyncJobStatus] = mapped_column(
        Enum(ClientOnboardingSyncJobStatus),
        nullable=False,
        server_default=ClientOnboardingSyncJobStatus.pending.value,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    result_payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=func.now(),
    )
