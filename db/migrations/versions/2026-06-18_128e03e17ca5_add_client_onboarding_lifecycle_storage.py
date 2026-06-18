"""add client onboarding lifecycle storage

Revision ID: 128e03e17ca5
Revises: a4d9c8e7b6a5
Create Date: 2026-06-18 00:25:15.534459

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "128e03e17ca5"
down_revision: Union[str, None] = "a4d9c8e7b6a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


client_onboarding_status = postgresql.ENUM(
    "contract_prepared",
    "account_created",
    "invite_sent",
    "invite_opened",
    "docusign_viewed",
    "docusign_signed",
    "password_set",
    "handoff_created",
    "activation_ready",
    "blocked",
    "cancelled",
    name="clientonboardingstatus",
    create_type=False,
)
client_onboarding_contract_type = postgresql.ENUM(
    "order_form_tos",
    "order_form_msa",
    name="clientonboardingcontracttype",
    create_type=False,
)
client_onboarding_actor_type = postgresql.ENUM(
    "client",
    "ae",
    "fde",
    "system",
    "webhook",
    name="clientonboardingactortype",
    create_type=False,
)
client_onboarding_activity_source = postgresql.ENUM(
    "manage_app",
    "admin_console",
    "docusign",
    "folk",
    "slack",
    "notion",
    "system_job",
    "api",
    name="clientonboardingactivitysource",
    create_type=False,
)
client_onboarding_sync_target = postgresql.ENUM(
    "database",
    "docusign",
    "folk",
    "slack",
    "notion",
    "manage_app",
    "admin_console",
    name="clientonboardingsynctarget",
    create_type=False,
)
client_onboarding_sync_job_status = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    "cancelled",
    name="clientonboardingsyncjobstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    client_onboarding_status.create(bind, checkfirst=True)
    client_onboarding_contract_type.create(bind, checkfirst=True)
    client_onboarding_actor_type.create(bind, checkfirst=True)
    client_onboarding_activity_source.create(bind, checkfirst=True)
    client_onboarding_sync_target.create(bind, checkfirst=True)
    client_onboarding_sync_job_status.create(bind, checkfirst=True)

    op.create_table(
        "client_onboarding_lifecycles",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("manage_app_account_name", sa.String(length=255), nullable=True),
        sa.Column("order_form_id", sa.String(length=255), nullable=True),
        sa.Column("client_company_name", sa.String(length=255), nullable=False),
        sa.Column("signer_name", sa.String(length=255), nullable=True),
        sa.Column("signer_email", sa.String(length=255), nullable=False),
        sa.Column("contract_type", client_onboarding_contract_type, nullable=False),
        sa.Column("docusign_contract_id", sa.String(length=255), nullable=True),
        sa.Column("docusign_envelope_id", sa.String(length=255), nullable=True),
        sa.Column("docusign_contract_url", sa.Text(), nullable=True),
        sa.Column("invite_id", sa.UUID(), nullable=True),
        sa.Column("ae_owner_user_id", sa.UUID(), nullable=True),
        sa.Column("fde_owner_user_id", sa.UUID(), nullable=True),
        sa.Column("folk_company_id", sa.String(length=255), nullable=True),
        sa.Column("folk_contact_id", sa.String(length=255), nullable=True),
        sa.Column("slack_channel_id", sa.String(length=255), nullable=True),
        sa.Column("notion_page_id", sa.String(length=255), nullable=True),
        sa.Column("scoping_doc_url", sa.Text(), nullable=True),
        sa.Column(
            "signer_scope_type",
            sa.String(length=64),
            server_default=sa.text("'account'"),
            nullable=False,
        ),
        sa.Column(
            "signer_scope_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            client_onboarding_status,
            server_default="contract_prepared",
            nullable=False,
        ),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("contract_prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("docusign_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("docusign_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handoff_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activation_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_client_onboarding_lifecycles_idempotency_key",
        ),
    )
    op.create_index(
        "idx_client_onboarding_lifecycles_account_signer",
        "client_onboarding_lifecycles",
        ["account_id", "signer_email"],
        unique=False,
    )
    op.create_index(
        "idx_client_onboarding_lifecycles_docusign_envelope",
        "client_onboarding_lifecycles",
        ["docusign_envelope_id"],
        unique=False,
    )
    op.create_index(
        "idx_client_onboarding_lifecycles_order_form",
        "client_onboarding_lifecycles",
        ["order_form_id"],
        unique=False,
    )
    op.create_index(
        "idx_client_onboarding_lifecycles_status",
        "client_onboarding_lifecycles",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_account_id"),
        "client_onboarding_lifecycles",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_ae_owner_user_id"),
        "client_onboarding_lifecycles",
        ["ae_owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_docusign_contract_id"),
        "client_onboarding_lifecycles",
        ["docusign_contract_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_fde_owner_user_id"),
        "client_onboarding_lifecycles",
        ["fde_owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_folk_company_id"),
        "client_onboarding_lifecycles",
        ["folk_company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_folk_contact_id"),
        "client_onboarding_lifecycles",
        ["folk_contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_id"),
        "client_onboarding_lifecycles",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_idempotency_key"),
        "client_onboarding_lifecycles",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_invite_id"),
        "client_onboarding_lifecycles",
        ["invite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_notion_page_id"),
        "client_onboarding_lifecycles",
        ["notion_page_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_order_form_id"),
        "client_onboarding_lifecycles",
        ["order_form_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_signer_email"),
        "client_onboarding_lifecycles",
        ["signer_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_lifecycles_slack_channel_id"),
        "client_onboarding_lifecycles",
        ["slack_channel_id"],
        unique=False,
    )

    op.create_table(
        "client_onboarding_activity",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lifecycle_id", sa.UUID(), nullable=False),
        sa.Column("activity_type", sa.String(length=100), nullable=False),
        sa.Column("previous_status", client_onboarding_status, nullable=True),
        sa.Column("next_status", client_onboarding_status, nullable=True),
        sa.Column("actor_type", client_onboarding_actor_type, nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_display_name", sa.String(length=255), nullable=True),
        sa.Column("source", client_onboarding_activity_source, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "payload_diff",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_client_onboarding_activity_actor",
        "client_onboarding_activity",
        ["actor_type", "actor_id"],
        unique=False,
    )
    op.create_index(
        "idx_client_onboarding_activity_lifecycle_time",
        "client_onboarding_activity",
        ["lifecycle_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_activity_actor_id"),
        "client_onboarding_activity",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_activity_id"),
        "client_onboarding_activity",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_activity_lifecycle_id"),
        "client_onboarding_activity",
        ["lifecycle_id"],
        unique=False,
    )

    op.create_table(
        "client_onboarding_sync_jobs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lifecycle_id", sa.UUID(), nullable=False),
        sa.Column("target", client_onboarding_sync_target, nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            client_onboarding_sync_job_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_client_onboarding_sync_jobs_idempotency_key",
        ),
    )
    op.create_index(
        "idx_client_onboarding_sync_jobs_claim",
        "client_onboarding_sync_jobs",
        ["status", "target", "available_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_client_onboarding_sync_jobs_lifecycle_target",
        "client_onboarding_sync_jobs",
        ["lifecycle_id", "target"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_sync_jobs_id"),
        "client_onboarding_sync_jobs",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_sync_jobs_idempotency_key"),
        "client_onboarding_sync_jobs",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_client_onboarding_sync_jobs_lifecycle_id"),
        "client_onboarding_sync_jobs",
        ["lifecycle_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_client_onboarding_sync_jobs_lifecycle_id"),
        table_name="client_onboarding_sync_jobs",
    )
    op.drop_index(
        op.f("ix_client_onboarding_sync_jobs_idempotency_key"),
        table_name="client_onboarding_sync_jobs",
    )
    op.drop_index(
        op.f("ix_client_onboarding_sync_jobs_id"),
        table_name="client_onboarding_sync_jobs",
    )
    op.drop_index(
        "idx_client_onboarding_sync_jobs_lifecycle_target",
        table_name="client_onboarding_sync_jobs",
    )
    op.drop_index(
        "idx_client_onboarding_sync_jobs_claim",
        table_name="client_onboarding_sync_jobs",
    )
    op.drop_table("client_onboarding_sync_jobs")

    op.drop_index(
        op.f("ix_client_onboarding_activity_lifecycle_id"),
        table_name="client_onboarding_activity",
    )
    op.drop_index(
        op.f("ix_client_onboarding_activity_id"),
        table_name="client_onboarding_activity",
    )
    op.drop_index(
        op.f("ix_client_onboarding_activity_actor_id"),
        table_name="client_onboarding_activity",
    )
    op.drop_index(
        "idx_client_onboarding_activity_lifecycle_time",
        table_name="client_onboarding_activity",
    )
    op.drop_index(
        "idx_client_onboarding_activity_actor",
        table_name="client_onboarding_activity",
    )
    op.drop_table("client_onboarding_activity")

    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_slack_channel_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_signer_email"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_order_form_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_notion_page_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_invite_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_idempotency_key"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_folk_contact_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_folk_company_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_fde_owner_user_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_docusign_contract_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_ae_owner_user_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        op.f("ix_client_onboarding_lifecycles_account_id"),
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        "idx_client_onboarding_lifecycles_status",
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        "idx_client_onboarding_lifecycles_order_form",
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        "idx_client_onboarding_lifecycles_docusign_envelope",
        table_name="client_onboarding_lifecycles",
    )
    op.drop_index(
        "idx_client_onboarding_lifecycles_account_signer",
        table_name="client_onboarding_lifecycles",
    )
    op.drop_table("client_onboarding_lifecycles")

    bind = op.get_bind()
    client_onboarding_sync_job_status.drop(bind, checkfirst=True)
    client_onboarding_sync_target.drop(bind, checkfirst=True)
    client_onboarding_activity_source.drop(bind, checkfirst=True)
    client_onboarding_actor_type.drop(bind, checkfirst=True)
    client_onboarding_contract_type.drop(bind, checkfirst=True)
    client_onboarding_status.drop(bind, checkfirst=True)
