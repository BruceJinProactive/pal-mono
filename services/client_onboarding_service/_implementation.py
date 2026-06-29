from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, TypeVar
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from db.pal_repository.client_onboarding import (
    ClientOnboardingRepository,
    client_onboarding_transition_changed,
    client_onboarding_transition_previous_status,
)
from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
    ResourceType,
)
from db.tables import (
    Account,
    ClientOnboardingActivitySource,
    ClientOnboardingActorType,
    ClientOnboardingLifecycle,
    ClientOnboardingStatus,
    ClientOnboardingSyncJobStatus,
    ClientOnboardingSyncTarget,
    UserInvitation,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.types import AccountUserStatus, InvitationStatus
from services import account_service
from services.account_service import AccountParams
from services.auth_types import UserContext
from services.folk_notion_sync._mapping import (
    CompanyProjection,
    DealProjection,
    build_notion_properties,
    select_property,
)
from utils.log import logger
from utils.secret import (
    get_client_secret_with_fallback,
    get_server_secret_with_fallback,
)

from .schema import (
    ClientOnboardingFdeOwnerAssignmentResult,
    ClientOnboardingFolkSyncResult,
    ClientOnboardingHandoffCompletionResult,
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
    ClientOnboardingNotionSyncResult,
    ClientOnboardingSlackHandoffResult,
    CreateClientOnboardingAccountParams,
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
    ReconcileClientOnboardingDocusignCompletionParams,
    ReconcileClientOnboardingDocusignCompletionResult,
)

POST_SIGNATURE_STATUSES = {
    ClientOnboardingStatus.docusign_signed,
    ClientOnboardingStatus.password_set,
    ClientOnboardingStatus.handoff_created,
    ClientOnboardingStatus.activation_ready,
}
POST_PASSWORD_STATUSES = {
    ClientOnboardingStatus.password_set,
    ClientOnboardingStatus.handoff_created,
    ClientOnboardingStatus.activation_ready,
}
DATABASE_CONTRACT_ACCEPTANCE_JOB_TYPE = "record_contract_acceptance"
FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE = "update_contract_acceptance"
SLACK_HANDOFF_JOB_TYPE = "create_handoff_channel"
NOTION_CMD_ENTRY_JOB_TYPE = "upsert_cmd_entry"
MANAGE_APP_FDE_OWNER_JOB_TYPE = "add_fde_owner"
REQUIRED_HANDOFF_SYNC_JOBS = (
    (ClientOnboardingSyncTarget.database, DATABASE_CONTRACT_ACCEPTANCE_JOB_TYPE),
    (ClientOnboardingSyncTarget.folk, FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE),
    (ClientOnboardingSyncTarget.slack, SLACK_HANDOFF_JOB_TYPE),
    (ClientOnboardingSyncTarget.notion, NOTION_CMD_ENTRY_JOB_TYPE),
    (ClientOnboardingSyncTarget.manage_app, MANAGE_APP_FDE_OWNER_JOB_TYPE),
)
COGNITO_FDE_OWNER_CONNECT_TIMEOUT_SECONDS = 2
COGNITO_FDE_OWNER_READ_TIMEOUT_SECONDS = 3
COGNITO_FDE_OWNER_MAX_ATTEMPTS = 3
DOCUSIGN_EMBED_HTTP_TIMEOUT_SECONDS = 10
DOCUSIGN_EMBED_OAUTH_SCOPE = "signature impersonation"
DOCUSIGN_EMBED_RETURN_PATH = "/accept-invitation"
T = TypeVar("T")


class FolkContractAcceptanceClient(Protocol):
    async def create_company(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def list_companies(
        self,
        *,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]: ...

    async def update_company(
        self,
        company_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def update_contact(
        self,
        contact_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class SlackHandoffClient(Protocol):
    async def create_channel(
        self,
        *,
        name: str,
        is_private: bool,
    ) -> dict[str, Any]: ...

    async def invite_users(
        self,
        *,
        channel_id: str,
        user_ids: list[str],
    ) -> dict[str, Any]: ...

    async def post_message(
        self,
        *,
        channel_id: str,
        text: str,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def lookup_user_id_by_email(
        self,
        *,
        email: str,
    ) -> str | None: ...

    async def find_channel_id_by_name(
        self,
        *,
        name: str,
    ) -> str | None: ...


class NotionCmdEntryClient(Protocol):
    async def find_page(self, company: CompanyProjection) -> dict[str, Any] | None: ...

    async def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]: ...


class FdeOwnerIdentityProvider(Protocol):
    def get_identity(self, user_id: uuid.UUID) -> "_FdeOwnerIdentity": ...


class DocusignEmbeddedSigningClient(Protocol):
    def create_recipient_view(
        self,
        *,
        envelope_id: str,
        signer_email: str,
        signer_name: str,
        client_user_id: str,
        return_url: str,
    ) -> str: ...


@dataclass(frozen=True)
class _DocusignEmbeddedSigningConfig:
    account_id: str
    integration_key: str
    impersonated_user_id: str
    private_key: str
    auth_server: str
    rest_api_base_url: str


@dataclass(frozen=True)
class _OwnerContact:
    role: str
    user_id: uuid.UUID
    email: str | None
    name: str | None


@dataclass(frozen=True)
class _SlackHandoffMessage:
    text: str
    blocks: list[dict[str, Any]]


@dataclass(frozen=True)
class _SlackHandoffChannel:
    channel_id: str
    channel_name: str
    created: bool


@dataclass(frozen=True)
class _SlackHandoffOutcome:
    channel_id: str
    channel_name: str
    created_channel: bool
    invited_user_ids: list[str]
    unresolved_owner_user_ids: list[str]
    message_ts: str | None
    invite_error: str | None = None


@dataclass(frozen=True)
class _NotionCmdEntryOutcome:
    notion_page_id: str
    created_page: bool
    updated_page: bool


@dataclass(frozen=True)
class _FdeOwnerIdentity:
    email: str
    name: str | None


@dataclass(frozen=True)
class _FdeOwnerAssignmentOutcome:
    account_id: uuid.UUID
    fde_owner_user_id: uuid.UUID
    membership_created: bool
    membership_reactivated: bool
    owner_role_assigned: bool


def create_client_onboarding_account(
    session: Session,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> CreateClientOnboardingAccountResult:
    ae_user_id = _parse_user_id(context.username)
    signer_email = _normalize_email(params.signer_email)
    now = datetime.now(timezone.utc)

    onboarding_repo = ClientOnboardingRepository(session)
    _raise_for_duplicate_idempotency_key(onboarding_repo, params)
    _raise_for_duplicate_docusign_reference(onboarding_repo, params)

    account = account_service.get_account(session, params.account_name)
    account_created = False
    if account is None:
        account = account_service.create_account(
            session=session,
            context=context,
            account_name=params.account_name,
            params=AccountParams(
                display_name=params.account_display_name or params.client_company_name,
                status=AccountStatus.pending,
                owner=context.email,
                contract_signed=True,
                onboarding_method=OnboardingMethod.manage_onboarding,
            ),
            lead_id=None,
            auto_commit=False,
        )
        account_created = True

    duplicate = onboarding_repo.get_active_for_account_signer(account.id, signer_email)
    if duplicate:
        raise DuplicateClientOnboardingError(
            "Active client onboarding lifecycle already exists for this account and signer"
        )

    _attach_ae_as_owner(session, account, context, ae_user_id)

    lifecycle = onboarding_repo.create_lifecycle(
        idempotency_key=params.idempotency_key,
        account_id=account.id,
        manage_app_account_name=account.name,
        order_form_id=params.order_form_id,
        client_company_name=params.client_company_name,
        signer_name=params.signer_name,
        signer_email=signer_email,
        contract_type=params.contract_type,
        docusign_contract_id=params.docusign_contract_id,
        docusign_envelope_id=params.docusign_envelope_id,
        docusign_contract_url=params.docusign_contract_url,
        ae_owner_user_id=ae_user_id,
        fde_owner_user_id=params.fde_owner_user_id,
        folk_company_id=params.folk_company_id,
        folk_contact_id=params.folk_contact_id,
        scoping_doc_url=params.scoping_doc_url,
        occurred_at=now,
    )
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type=ClientOnboardingStatus.contract_prepared.value,
        actor_type=ClientOnboardingActorType.ae,
        actor_id=ae_user_id,
        actor_display_name=context.display_name or context.email,
        source=ClientOnboardingActivitySource.manage_app,
        next_status=ClientOnboardingStatus.contract_prepared,
        description="AE prepared DocuSign contract reference for onboarding",
        payload_diff=_contract_payload(params),
        occurred_at=now,
    )
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type=ClientOnboardingStatus.account_created.value,
        actor_type=ClientOnboardingActorType.ae,
        actor_id=ae_user_id,
        actor_display_name=context.display_name or context.email,
        source=ClientOnboardingActivitySource.manage_app,
        previous_status=ClientOnboardingStatus.contract_prepared,
        next_status=ClientOnboardingStatus.account_created,
        description="AE created or linked Manage App account",
        payload_diff={
            "account_id": str(account.id),
            "account_name": account.name,
            "account_created": account_created,
        },
        occurred_at=now,
    )
    session.commit()

    try:
        invitation = _create_signer_invitation(
            session=session,
            context=context,
            account_name=account.name,
            signer_email=signer_email,
        )
    except Exception as exc:
        session.rollback()
        onboarding_repo.mark_blocked(
            lifecycle.id,
            status_reason=f"Failed to create signer invite: {exc}",
            occurred_at=datetime.now(timezone.utc),
        )
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type=ClientOnboardingStatus.blocked.value,
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.manage_app,
            previous_status=ClientOnboardingStatus.account_created,
            next_status=ClientOnboardingStatus.blocked,
            description="Signer invite creation failed",
            payload_diff={"error": str(exc)},
        )
        session.commit()
        raise

    invite_sent_at = datetime.now(timezone.utc)
    lifecycle = onboarding_repo.mark_invite_sent(
        lifecycle.id,
        invite_id=invitation.id,
        occurred_at=invite_sent_at,
    )
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type=ClientOnboardingStatus.invite_sent.value,
        actor_type=ClientOnboardingActorType.ae,
        actor_id=ae_user_id,
        actor_display_name=context.display_name or context.email,
        source=ClientOnboardingActivitySource.manage_app,
        previous_status=ClientOnboardingStatus.account_created,
        next_status=ClientOnboardingStatus.invite_sent,
        description="AE sent client signer invite",
        payload_diff={
            "invite_id": str(invitation.id),
            "signer_email": signer_email,
        },
        occurred_at=invite_sent_at,
    )

    signed_at = invite_sent_at
    lifecycle = onboarding_repo.mark_docusign_signed(
        lifecycle.id,
        occurred_at=signed_at,
        backfill_client_timestamps=False,
    )
    if client_onboarding_transition_changed(lifecycle):
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type=ClientOnboardingStatus.docusign_signed.value,
            actor_type=ClientOnboardingActorType.ae,
            actor_id=ae_user_id,
            actor_display_name=context.display_name or context.email,
            source=ClientOnboardingActivitySource.manage_app,
            previous_status=client_onboarding_transition_previous_status(lifecycle)
            or ClientOnboardingStatus.invite_sent,
            next_status=ClientOnboardingStatus.docusign_signed,
            description="AE manually verified signed DocuSign contract before account creation",
            payload_diff=_manual_docusign_acceptance_payload(lifecycle),
            occurred_at=signed_at,
        )
        _enqueue_post_signature_sync_jobs(
            onboarding_repo,
            lifecycle,
            occurred_at=signed_at,
        )
    session.commit()
    _attempt_post_signature_folk_sync(session, lifecycle.id)
    _attempt_post_signature_slack_handoff(session, lifecycle.id)
    _attempt_post_signature_notion_cmd_entry(session, lifecycle.id)
    _attempt_post_signature_fde_owner_assignment(session, lifecycle.id)

    return CreateClientOnboardingAccountResult(
        account_id=account.id,
        account_name=account.name,
        account_created=account_created,
        lifecycle_id=lifecycle.id,
        lifecycle_status=lifecycle.status,
        invitation_id=invitation.id,
        signer_email=signer_email,
        ae_owner_user_id=ae_user_id,
        fde_owner_user_id=params.fde_owner_user_id,
    )


def get_client_onboarding_invite_step(
    session: Session,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    resolved = _resolve_client_onboarding_invite(session, invitation_token)
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = resolved.lifecycle

    if lifecycle.status == ClientOnboardingStatus.invite_sent:
        opened_at = datetime.now(timezone.utc)
        lifecycle = onboarding_repo.mark_invite_opened(
            lifecycle.id,
            occurred_at=opened_at,
        )
        if client_onboarding_transition_changed(lifecycle):
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.invite_opened.value,
                actor_type=ClientOnboardingActorType.client,
                source=ClientOnboardingActivitySource.admin_console,
                previous_status=ClientOnboardingStatus.invite_sent,
                next_status=ClientOnboardingStatus.invite_opened,
                actor_display_name=lifecycle.signer_email,
                description="Client opened Admin Console invite",
                occurred_at=opened_at,
            )
            session.commit()

    return _build_invite_step_result(resolved, lifecycle, invitation_token)


def mark_client_onboarding_docusign_viewed(
    session: Session,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    resolved = _resolve_client_onboarding_invite(session, invitation_token)
    lifecycle = resolved.lifecycle

    if not (
        lifecycle.docusign_envelope_id or lifecycle.docusign_contract_url
    ) and lifecycle.status not in {
        ClientOnboardingStatus.docusign_viewed,
        *POST_SIGNATURE_STATUSES,
    }:
        raise ClientOnboardingInviteInvalidError("DocuSign embed URL is not available")

    if lifecycle.status in {
        ClientOnboardingStatus.invite_sent,
        ClientOnboardingStatus.invite_opened,
    }:
        viewed_at = datetime.now(timezone.utc)
        previous_status = lifecycle.status
        onboarding_repo = ClientOnboardingRepository(session)
        lifecycle = onboarding_repo.mark_docusign_viewed(
            lifecycle.id,
            occurred_at=viewed_at,
        )
        if client_onboarding_transition_changed(lifecycle):
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.docusign_viewed.value,
                actor_type=ClientOnboardingActorType.client,
                source=ClientOnboardingActivitySource.admin_console,
                previous_status=client_onboarding_transition_previous_status(lifecycle)
                or previous_status,
                next_status=ClientOnboardingStatus.docusign_viewed,
                actor_display_name=lifecycle.signer_email,
                description="Client-visible DocuSign embed loaded in Admin Console",
                payload_diff={
                    "docusign_contract_url": lifecycle.docusign_contract_url,
                    "docusign_envelope_id": lifecycle.docusign_envelope_id,
                },
                occurred_at=viewed_at,
            )
            session.commit()

    return _build_invite_step_result(resolved, lifecycle, invitation_token)


def mark_client_onboarding_password_set(
    session: Session,
    context: UserContext,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    resolved = _resolve_client_onboarding_invite_for_password_set(
        session=session,
        invitation_token=invitation_token,
        context=context,
    )
    lifecycle = resolved.lifecycle

    if lifecycle.status not in {
        ClientOnboardingStatus.docusign_signed,
        *POST_PASSWORD_STATUSES,
    }:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before password setup"
        )

    if lifecycle.status in {
        ClientOnboardingStatus.docusign_signed,
        ClientOnboardingStatus.handoff_created,
    }:
        password_set_at = datetime.now(timezone.utc)
        onboarding_repo = ClientOnboardingRepository(session)
        lifecycle = onboarding_repo.mark_password_set(
            lifecycle.id,
            occurred_at=password_set_at,
        )
        if client_onboarding_transition_changed(lifecycle):
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.password_set.value,
                actor_type=ClientOnboardingActorType.client,
                actor_id=_parse_optional_user_id(context.username),
                actor_display_name=context.email,
                source=ClientOnboardingActivitySource.admin_console,
                previous_status=client_onboarding_transition_previous_status(lifecycle)
                or ClientOnboardingStatus.docusign_signed,
                next_status=lifecycle.status,
                description="Client completed password setup after DocuSign signature",
                payload_diff={
                    "invite_id": (
                        str(lifecycle.invite_id) if lifecycle.invite_id else None
                    ),
                    "signer_email": lifecycle.signer_email,
                },
                occurred_at=password_set_at,
            )
            session.commit()
            completion = orchestrate_client_onboarding_handoff_completion(
                session,
                lifecycle.id,
            )
            lifecycle.status = completion.lifecycle_status

    return _build_invite_step_result(resolved, lifecycle, invitation_token)


def reconcile_client_onboarding_docusign_completion(
    session: Session,
    params: ReconcileClientOnboardingDocusignCompletionParams,
) -> ReconcileClientOnboardingDocusignCompletionResult:
    docusign_contract_id = _clean_optional_text(params.docusign_contract_id)
    docusign_envelope_id = _clean_optional_text(params.docusign_envelope_id)
    docusign_contract_url = _clean_optional_text(params.docusign_contract_url)
    if not (docusign_contract_id or docusign_envelope_id or docusign_contract_url):
        raise ClientOnboardingInviteInvalidError(
            "At least one DocuSign reference is required"
        )

    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_active_by_docusign_reference(
        docusign_contract_id=docusign_contract_id,
        docusign_envelope_id=docusign_envelope_id,
        docusign_contract_url=docusign_contract_url,
    )
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found for DocuSign reference"
        )
    _raise_for_docusign_reference_mismatch(
        lifecycle,
        docusign_contract_id=docusign_contract_id,
        docusign_envelope_id=docusign_envelope_id,
        docusign_contract_url=docusign_contract_url,
    )

    signer_email = _clean_optional_text(params.signer_email)
    if signer_email and _normalize_email(signer_email) != lifecycle.signer_email:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign signer email does not match lifecycle signer"
        )

    completed_at = _coerce_event_time(params.completed_at)
    transition_recorded = False
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        previous_status = lifecycle.status
        lifecycle = onboarding_repo.mark_docusign_signed(
            lifecycle.id,
            occurred_at=completed_at,
        )
        transition_recorded = client_onboarding_transition_changed(lifecycle)
        if transition_recorded:
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.docusign_signed.value,
                actor_type=ClientOnboardingActorType.webhook,
                source=ClientOnboardingActivitySource.docusign,
                previous_status=client_onboarding_transition_previous_status(lifecycle)
                or previous_status,
                next_status=ClientOnboardingStatus.docusign_signed,
                actor_display_name=lifecycle.signer_email,
                description="DocuSign confirmed client contract completion",
                payload_diff=_docusign_completion_payload(
                    params=params,
                    lifecycle=lifecycle,
                ),
                occurred_at=completed_at,
            )
            _enqueue_post_signature_sync_jobs(
                onboarding_repo,
                lifecycle,
                occurred_at=completed_at,
            )
            session.commit()
            _attempt_post_signature_slack_handoff(session, lifecycle.id)
            _attempt_post_signature_notion_cmd_entry(session, lifecycle.id)
            _attempt_post_signature_fde_owner_assignment(session, lifecycle.id)
        elif lifecycle.status not in POST_SIGNATURE_STATUSES:
            raise ClientOnboardingInviteInvalidError(
                f"DocuSign completion cannot advance lifecycle from {lifecycle.status.value}"
            )

    return ReconcileClientOnboardingDocusignCompletionResult(
        lifecycle_id=lifecycle.id,
        lifecycle_status=lifecycle.status,
        docusign_signed_at=lifecycle.docusign_signed_at,
        password_setup_available=lifecycle.status in POST_SIGNATURE_STATUSES,
        transition_recorded=transition_recorded,
    )


def _attempt_post_signature_slack_handoff(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> None:
    try:
        sync_client_onboarding_slack_handoff(session, lifecycle_id)
    except Exception:
        logger.exception(
            "Client onboarding Slack handoff failed after DocuSign completion",
            extra={"lifecycle_id": str(lifecycle_id)},
        )
        return


def _attempt_post_signature_folk_sync(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> None:
    try:
        sync_client_onboarding_contract_acceptance_to_folk(session, lifecycle_id)
    except Exception:  # noqa: BLE001 - handoff sync attempts are best-effort here.
        logger.exception(
            "Client onboarding Folk sync failed after manual DocuSign verification",
            extra={"lifecycle_id": str(lifecycle_id)},
        )
        return


def _attempt_post_signature_notion_cmd_entry(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> None:
    try:
        sync_client_onboarding_notion_cmd_entry(session, lifecycle_id)
    except Exception:
        logger.exception(
            "Client onboarding Notion CMD sync failed after DocuSign completion",
            extra={"lifecycle_id": str(lifecycle_id)},
        )
        return


def _attempt_post_signature_fde_owner_assignment(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> None:
    try:
        sync_client_onboarding_fde_owner_assignment(session, lifecycle_id)
    except Exception:
        logger.exception(
            "Client onboarding FDE owner assignment failed after DocuSign completion",
            extra={"lifecycle_id": str(lifecycle_id)},
        )
        return


def sync_client_onboarding_contract_acceptance_to_folk(
    session: Session,
    lifecycle_id: uuid.UUID,
    *,
    folk_client: FolkContractAcceptanceClient | None = None,
) -> ClientOnboardingFolkSyncResult:
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_id(lifecycle_id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found"
        )
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before syncing contract acceptance to Folk"
        )
    if lifecycle.docusign_signed_at is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing DocuSign signed timestamp"
        )

    job = onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.folk,
        job_type=FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.folk,
            FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE,
        ),
        payload=_post_signature_sync_payload(lifecycle),
    )
    if job.status in {
        ClientOnboardingSyncJobStatus.completed,
        ClientOnboardingSyncJobStatus.cancelled,
    }:
        result_payload = job.result_payload or {}
        _attempt_handoff_completion(session, lifecycle.id)
        return ClientOnboardingFolkSyncResult(
            lifecycle_id=lifecycle.id,
            folk_company_id=lifecycle.folk_company_id,
            folk_contact_id=lifecycle.folk_contact_id,
            updated_company=result_payload.get("updated_company") is True,
            updated_contact=result_payload.get("updated_contact") is True,
            skipped_reason=(
                "Folk contract acceptance sync job is cancelled"
                if job.status == ClientOnboardingSyncJobStatus.cancelled
                else None
            ),
        )

    try:
        client = folk_client or _build_folk_contract_acceptance_client()
        created_company = False
        if not lifecycle.folk_company_id:
            company_id, created_company = _run_async(
                _resolve_or_create_folk_company(client, lifecycle)
            )
            lifecycle = onboarding_repo.update_folk_ids(
                lifecycle.id,
                folk_company_id=company_id,
                folk_contact_id=lifecycle.folk_contact_id,
            )
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=(
                    "folk_company_created" if created_company else "folk_company_linked"
                ),
                actor_type=ClientOnboardingActorType.system,
                source=ClientOnboardingActivitySource.folk,
                description=(
                    "Folk company created for client onboarding"
                    if created_company
                    else "Existing Folk company linked for client onboarding"
                ),
                payload_diff={
                    "sync_job_id": str(job.id),
                    "folk_company_id": company_id,
                    "client_company_name": lifecycle.client_company_name,
                },
            )
            session.commit()

        payload = _folk_contract_acceptance_payload(lifecycle)
        updated_company, updated_contact = _run_async(
            _update_folk_contract_acceptance(
                client,
                lifecycle,
                payload,
            )
        )
    except Exception as exc:
        onboarding_repo.mark_sync_job_failed(
            job.id,
            last_error=str(exc),
            result_payload={"error": str(exc)},
        )
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type="folk_contract_acceptance_sync_failed",
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.folk,
            description="Folk contract acceptance update failed",
            payload_diff={"sync_job_id": str(job.id), "error": str(exc)},
        )
        session.commit()
        raise

    onboarding_repo.mark_sync_job_completed(
        job.id,
        result_payload={
            "updated_company": updated_company,
            "updated_contact": updated_contact,
            "created_company": created_company,
        },
    )
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type="folk_contract_acceptance_synced",
        actor_type=ClientOnboardingActorType.system,
        source=ClientOnboardingActivitySource.folk,
        description="Folk contract acceptance fields updated",
        payload_diff={
            "sync_job_id": str(job.id),
            "folk_company_id": lifecycle.folk_company_id,
            "folk_contact_id": lifecycle.folk_contact_id,
        },
    )
    session.commit()
    _attempt_handoff_completion(session, lifecycle.id)
    return ClientOnboardingFolkSyncResult(
        lifecycle_id=lifecycle.id,
        folk_company_id=lifecycle.folk_company_id,
        folk_contact_id=lifecycle.folk_contact_id,
        updated_company=updated_company,
        updated_contact=updated_contact,
    )


def sync_client_onboarding_slack_handoff(
    session: Session,
    lifecycle_id: uuid.UUID,
    *,
    slack_client: SlackHandoffClient | None = None,
) -> ClientOnboardingSlackHandoffResult:
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_id(lifecycle_id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found"
        )
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before creating Slack handoff"
        )
    if lifecycle.docusign_signed_at is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing DocuSign signed timestamp"
        )

    job = onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.slack,
        job_type=SLACK_HANDOFF_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.slack,
            SLACK_HANDOFF_JOB_TYPE,
        ),
        payload=_post_signature_sync_payload(lifecycle),
    )
    if job.status in {
        ClientOnboardingSyncJobStatus.completed,
        ClientOnboardingSyncJobStatus.cancelled,
    }:
        result_payload = job.result_payload or {}
        _attempt_handoff_completion(session, lifecycle.id)
        return ClientOnboardingSlackHandoffResult(
            lifecycle_id=lifecycle.id,
            slack_channel_id=_payload_text(result_payload, "slack_channel_id")
            or lifecycle.slack_channel_id,
            slack_channel_name=_payload_text(result_payload, "slack_channel_name"),
            created_channel=result_payload.get("created_channel") is True,
            invited_user_ids=_payload_text_list(
                result_payload,
                "invited_user_ids",
            ),
            posted_message=result_payload.get("posted_message") is True,
            message_ts=_payload_text(result_payload, "message_ts"),
            skipped_reason=(
                "Slack handoff sync job is cancelled"
                if job.status == ClientOnboardingSyncJobStatus.cancelled
                else None
            ),
        )

    owner_contacts = _resolve_handoff_owner_contacts(session, lifecycle)
    try:
        client = slack_client or _build_slack_handoff_client()
        channel = _run_async(_ensure_slack_handoff_channel(client, lifecycle))
        if lifecycle.slack_channel_id != channel.channel_id:
            lifecycle = onboarding_repo.set_slack_channel_id(
                lifecycle.id,
                slack_channel_id=channel.channel_id,
            )
            session.commit()
        outcome = _run_async(
            _post_slack_handoff(
                client,
                lifecycle,
                owner_contacts,
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                created_channel=channel.created,
            )
        )
    except Exception as exc:
        onboarding_repo.mark_sync_job_failed(
            job.id,
            last_error=str(exc),
            result_payload={"error": str(exc)},
        )
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type="slack_handoff_sync_failed",
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.slack,
            description="Slack handoff creation failed",
            payload_diff={"sync_job_id": str(job.id), "error": str(exc)},
        )
        session.commit()
        raise

    result_payload = {
        "slack_channel_id": outcome.channel_id,
        "slack_channel_name": outcome.channel_name,
        "created_channel": outcome.created_channel,
        "invited_user_ids": outcome.invited_user_ids,
        "unresolved_owner_user_ids": outcome.unresolved_owner_user_ids,
        "posted_message": True,
        "message_ts": outcome.message_ts,
    }
    if outcome.invite_error:
        result_payload["invite_error"] = outcome.invite_error
    onboarding_repo.mark_sync_job_completed(job.id, result_payload=result_payload)
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type="slack_handoff_created",
        actor_type=ClientOnboardingActorType.system,
        source=ClientOnboardingActivitySource.slack,
        description="Slack handoff channel created and contract acceptance posted",
        payload_diff={
            "sync_job_id": str(job.id),
            "slack_channel_id": outcome.channel_id,
            "slack_channel_name": outcome.channel_name,
            "invited_user_ids": outcome.invited_user_ids,
            "unresolved_owner_user_ids": outcome.unresolved_owner_user_ids,
        },
    )
    session.commit()
    _attempt_handoff_completion(session, lifecycle.id)
    return ClientOnboardingSlackHandoffResult(
        lifecycle_id=lifecycle.id,
        slack_channel_id=outcome.channel_id,
        slack_channel_name=outcome.channel_name,
        created_channel=outcome.created_channel,
        invited_user_ids=outcome.invited_user_ids,
        posted_message=True,
        message_ts=outcome.message_ts,
    )


def sync_client_onboarding_notion_cmd_entry(
    session: Session,
    lifecycle_id: uuid.UUID,
    *,
    notion_client: NotionCmdEntryClient | None = None,
) -> ClientOnboardingNotionSyncResult:
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_id(lifecycle_id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found"
        )
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before creating the Notion CMD entry"
        )
    if lifecycle.docusign_signed_at is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing DocuSign signed timestamp"
        )

    job = onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.notion,
        job_type=NOTION_CMD_ENTRY_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.notion,
            NOTION_CMD_ENTRY_JOB_TYPE,
        ),
        payload=_post_signature_sync_payload(lifecycle),
    )
    if job.status in {
        ClientOnboardingSyncJobStatus.completed,
        ClientOnboardingSyncJobStatus.cancelled,
    }:
        result_payload = job.result_payload or {}
        _attempt_handoff_completion(session, lifecycle.id)
        return ClientOnboardingNotionSyncResult(
            lifecycle_id=lifecycle.id,
            notion_page_id=_payload_text(result_payload, "notion_page_id")
            or lifecycle.notion_page_id,
            created_page=result_payload.get("created_page") is True,
            updated_page=result_payload.get("updated_page") is True,
            skipped_reason=(
                "Notion CMD sync job is cancelled"
                if job.status == ClientOnboardingSyncJobStatus.cancelled
                else None
            ),
        )

    try:
        owner_contacts = _resolve_handoff_owner_contacts(session, lifecycle)
        client = notion_client or _build_notion_cmd_entry_client()
        outcome = _run_async(
            _upsert_notion_cmd_entry(
                client,
                lifecycle,
                owner_contacts,
            )
        )
        if lifecycle.notion_page_id != outcome.notion_page_id:
            lifecycle = onboarding_repo.set_notion_page_id(
                lifecycle.id,
                notion_page_id=outcome.notion_page_id,
            )
    except Exception as exc:
        onboarding_repo.mark_sync_job_failed(
            job.id,
            last_error=str(exc),
            result_payload={"error": str(exc)},
        )
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type="notion_cmd_entry_sync_failed",
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.notion,
            description="Notion CMD entry sync failed",
            payload_diff={"sync_job_id": str(job.id), "error": str(exc)},
        )
        session.commit()
        raise

    result_payload = {
        "notion_page_id": outcome.notion_page_id,
        "created_page": outcome.created_page,
        "updated_page": outcome.updated_page,
    }
    onboarding_repo.mark_sync_job_completed(job.id, result_payload=result_payload)
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type="notion_cmd_entry_synced",
        actor_type=ClientOnboardingActorType.system,
        source=ClientOnboardingActivitySource.notion,
        description="Notion Client Master Database entry synced",
        payload_diff={
            "sync_job_id": str(job.id),
            "notion_page_id": outcome.notion_page_id,
            "created_page": outcome.created_page,
            "updated_page": outcome.updated_page,
        },
    )
    session.commit()
    _attempt_handoff_completion(session, lifecycle.id)
    return ClientOnboardingNotionSyncResult(
        lifecycle_id=lifecycle.id,
        notion_page_id=outcome.notion_page_id,
        created_page=outcome.created_page,
        updated_page=outcome.updated_page,
    )


def sync_client_onboarding_fde_owner_assignment(
    session: Session,
    lifecycle_id: uuid.UUID,
    *,
    identity_provider: FdeOwnerIdentityProvider | None = None,
) -> ClientOnboardingFdeOwnerAssignmentResult:
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_id(lifecycle_id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found"
        )
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before assigning the FDE owner"
        )
    if lifecycle.docusign_signed_at is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing DocuSign signed timestamp"
        )

    job = onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.manage_app,
        job_type=MANAGE_APP_FDE_OWNER_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.manage_app,
            MANAGE_APP_FDE_OWNER_JOB_TYPE,
        ),
        payload=_post_signature_sync_payload(lifecycle),
    )
    if job.status in {
        ClientOnboardingSyncJobStatus.completed,
        ClientOnboardingSyncJobStatus.cancelled,
    }:
        result_payload = job.result_payload or {}
        _attempt_handoff_completion(session, lifecycle.id)
        return ClientOnboardingFdeOwnerAssignmentResult(
            lifecycle_id=lifecycle.id,
            account_id=lifecycle.account_id,
            fde_owner_user_id=lifecycle.fde_owner_user_id,
            membership_created=result_payload.get("membership_created") is True,
            membership_reactivated=(
                result_payload.get("membership_reactivated") is True
            ),
            owner_role_assigned=result_payload.get("owner_role_assigned") is True,
            skipped_reason=(
                "FDE owner assignment sync job is cancelled"
                if job.status == ClientOnboardingSyncJobStatus.cancelled
                else _payload_text(result_payload, "skipped_reason")
            ),
        )

    if lifecycle.fde_owner_user_id is None:
        skipped_reason = "No FDE owner user ID is linked to this lifecycle"
        result_payload = {"skipped_reason": skipped_reason}
        onboarding_repo.mark_sync_job_completed(job.id, result_payload=result_payload)
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type="fde_owner_assignment_skipped",
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.manage_app,
            description=skipped_reason,
            payload_diff={"sync_job_id": str(job.id)},
        )
        session.commit()
        _attempt_handoff_completion(session, lifecycle.id)
        return ClientOnboardingFdeOwnerAssignmentResult(
            lifecycle_id=lifecycle.id,
            account_id=lifecycle.account_id,
            fde_owner_user_id=None,
            membership_created=False,
            membership_reactivated=False,
            owner_role_assigned=False,
            skipped_reason=skipped_reason,
        )

    try:
        outcome = _add_fde_owner_to_manage_app_account(
            session,
            lifecycle,
            identity_provider=identity_provider or _build_fde_owner_identity_provider(),
        )
    except Exception as exc:
        onboarding_repo.mark_sync_job_failed(
            job.id,
            last_error=str(exc),
            result_payload={"error": str(exc)},
        )
        onboarding_repo.append_activity(
            lifecycle_id=lifecycle.id,
            activity_type="fde_owner_assignment_failed",
            actor_type=ClientOnboardingActorType.system,
            source=ClientOnboardingActivitySource.manage_app,
            description="FDE account owner assignment failed",
            payload_diff={"sync_job_id": str(job.id), "error": str(exc)},
        )
        session.commit()
        raise

    result_payload = {
        "account_id": str(outcome.account_id),
        "fde_owner_user_id": str(outcome.fde_owner_user_id),
        "membership_created": outcome.membership_created,
        "membership_reactivated": outcome.membership_reactivated,
        "owner_role_assigned": outcome.owner_role_assigned,
    }
    onboarding_repo.mark_sync_job_completed(job.id, result_payload=result_payload)
    onboarding_repo.append_activity(
        lifecycle_id=lifecycle.id,
        activity_type="fde_owner_assigned",
        actor_type=ClientOnboardingActorType.system,
        source=ClientOnboardingActivitySource.manage_app,
        description="FDE added to account as owner",
        payload_diff={
            "sync_job_id": str(job.id),
            "account_id": str(outcome.account_id),
            "fde_owner_user_id": str(outcome.fde_owner_user_id),
            "membership_created": outcome.membership_created,
            "membership_reactivated": outcome.membership_reactivated,
            "owner_role_assigned": outcome.owner_role_assigned,
        },
    )
    session.commit()
    _attempt_handoff_completion(session, lifecycle.id)
    return ClientOnboardingFdeOwnerAssignmentResult(
        lifecycle_id=lifecycle.id,
        account_id=outcome.account_id,
        fde_owner_user_id=outcome.fde_owner_user_id,
        membership_created=outcome.membership_created,
        membership_reactivated=outcome.membership_reactivated,
        owner_role_assigned=outcome.owner_role_assigned,
    )


def orchestrate_client_onboarding_handoff_completion(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> ClientOnboardingHandoffCompletionResult:
    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_id(lifecycle_id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found"
        )
    if lifecycle.status not in POST_SIGNATURE_STATUSES:
        raise ClientOnboardingInviteInvalidError(
            "DocuSign completion is required before handoff completion"
        )
    if lifecycle.docusign_signed_at is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing DocuSign signed timestamp"
        )

    pending_sync_jobs = _pending_handoff_sync_jobs(
        onboarding_repo.get_sync_jobs_for_lifecycle(lifecycle.id)
    )
    if pending_sync_jobs:
        return ClientOnboardingHandoffCompletionResult(
            lifecycle_id=lifecycle.id,
            lifecycle_status=lifecycle.status,
            handoff_created=lifecycle.handoff_created_at is not None,
            activation_ready=lifecycle.status
            == ClientOnboardingStatus.activation_ready,
            pending_sync_jobs=pending_sync_jobs,
        )

    if lifecycle.status in {
        ClientOnboardingStatus.docusign_signed,
        ClientOnboardingStatus.password_set,
    }:
        occurred_at = datetime.now(timezone.utc)
        previous_status = lifecycle.status
        lifecycle = onboarding_repo.mark_handoff_created(
            lifecycle.id,
            occurred_at=occurred_at,
        )
        if client_onboarding_transition_changed(lifecycle):
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.handoff_created.value,
                actor_type=ClientOnboardingActorType.system,
                source=ClientOnboardingActivitySource.system_job,
                previous_status=client_onboarding_transition_previous_status(lifecycle)
                or previous_status,
                next_status=ClientOnboardingStatus.handoff_created,
                description="Post-signature handoff artifacts completed",
                payload_diff={
                    "completed_sync_jobs": [
                        _handoff_sync_job_key(target, job_type)
                        for target, job_type in REQUIRED_HANDOFF_SYNC_JOBS
                    ],
                },
                occurred_at=occurred_at,
            )
            session.commit()

    if (
        lifecycle.status == ClientOnboardingStatus.handoff_created
        and lifecycle.password_set_at is not None
    ):
        occurred_at = datetime.now(timezone.utc)
        lifecycle = onboarding_repo.mark_activation_ready(
            lifecycle.id,
            occurred_at=occurred_at,
        )
        if client_onboarding_transition_changed(lifecycle):
            onboarding_repo.append_activity(
                lifecycle_id=lifecycle.id,
                activity_type=ClientOnboardingStatus.activation_ready.value,
                actor_type=ClientOnboardingActorType.system,
                source=ClientOnboardingActivitySource.system_job,
                previous_status=client_onboarding_transition_previous_status(lifecycle)
                or ClientOnboardingStatus.handoff_created,
                next_status=ClientOnboardingStatus.activation_ready,
                description="Client onboarding is ready for activation",
                occurred_at=occurred_at,
            )
            session.commit()

    return ClientOnboardingHandoffCompletionResult(
        lifecycle_id=lifecycle.id,
        lifecycle_status=lifecycle.status,
        handoff_created=lifecycle.handoff_created_at is not None,
        activation_ready=lifecycle.status == ClientOnboardingStatus.activation_ready,
        pending_sync_jobs=[],
    )


def _attempt_handoff_completion(
    session: Session,
    lifecycle_id: uuid.UUID,
) -> None:
    try:
        orchestrate_client_onboarding_handoff_completion(session, lifecycle_id)
    # Best-effort lifecycle advancement must not fail artifact syncs.
    except Exception:  # noqa: BLE001
        logger.exception(
            "Client onboarding handoff completion orchestration failed",
            extra={"lifecycle_id": str(lifecycle_id)},
        )
        return


def _pending_handoff_sync_jobs(jobs: list[Any]) -> list[str]:
    jobs_by_key = {
        (job.target, job.job_type): job
        for job in jobs
        if isinstance(getattr(job, "target", None), ClientOnboardingSyncTarget)
        and isinstance(getattr(job, "job_type", None), str)
    }
    pending: list[str] = []
    for target, job_type in REQUIRED_HANDOFF_SYNC_JOBS:
        job = jobs_by_key.get((target, job_type))
        if not job or job.status != ClientOnboardingSyncJobStatus.completed:
            pending.append(_handoff_sync_job_key(target, job_type))
    return pending


def _handoff_sync_job_key(target: ClientOnboardingSyncTarget, job_type: str) -> str:
    return f"{target.value}:{job_type}"


def _attach_ae_as_owner(
    session: Session,
    account: Account,
    context: UserContext,
    ae_user_id: uuid.UUID,
) -> None:
    account_user_repo = AccountUserRepository(session, auto_commit=False)
    account_user_repo.create(
        account_id=account.id,
        user_id=ae_user_id,
        email=context.email,
        name=context.display_name or context.email,
        added_by=ae_user_id,
        status=AccountUserStatus.active,
    )

    role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)
    role_repo.add_role(
        user_id=ae_user_id,
        resource_type=ResourceType.ACCOUNT,
        resource_id=account.id,
        role="owner",
        assigned_by=ae_user_id,
        reason="AE account creation onboarding",
    )


def _create_signer_invitation(
    *,
    session: Session,
    context: UserContext,
    account_name: str,
    signer_email: str,
) -> UserInvitation:
    from services import team_service
    from services.team_service.schema import InvitationParams

    return team_service.create_invitation(
        session=session,
        context=context,
        account_name=account_name,
        params=InvitationParams(
            email=signer_email,
            account_role="owner",
            project_ids=None,
        ),
    )


def _raise_for_duplicate_docusign_reference(
    onboarding_repo: ClientOnboardingRepository,
    params: CreateClientOnboardingAccountParams,
) -> None:
    duplicate = onboarding_repo.get_active_by_docusign_reference(
        docusign_contract_id=params.docusign_contract_id,
        docusign_envelope_id=params.docusign_envelope_id,
        docusign_contract_url=params.docusign_contract_url,
    )
    if duplicate:
        raise DuplicateClientOnboardingError(
            "Active client onboarding lifecycle already exists for this DocuSign reference"
        )


def _raise_for_duplicate_idempotency_key(
    onboarding_repo: ClientOnboardingRepository,
    params: CreateClientOnboardingAccountParams,
) -> None:
    if not params.idempotency_key:
        return

    duplicate = onboarding_repo.get_by_idempotency_key(params.idempotency_key)
    if duplicate:
        raise DuplicateClientOnboardingError(
            "Client onboarding lifecycle already exists for this idempotency key"
        )


def _contract_payload(params: CreateClientOnboardingAccountParams) -> dict[str, str]:
    payload = {
        "contract_type": params.contract_type.value,
        "signer_email": _normalize_email(params.signer_email),
    }
    optional_values = {
        "order_form_id": params.order_form_id,
        "docusign_contract_id": params.docusign_contract_id,
        "docusign_envelope_id": params.docusign_envelope_id,
        "docusign_contract_url": params.docusign_contract_url,
        "scoping_doc_url": params.scoping_doc_url,
    }
    return payload | {key: value for key, value in optional_values.items() if value}


def _docusign_completion_payload(
    *,
    params: ReconcileClientOnboardingDocusignCompletionParams,
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, str]:
    payload = {
        "signer_email": lifecycle.signer_email,
    }
    optional_values = {
        "docusign_contract_id": lifecycle.docusign_contract_id
        or _clean_optional_text(params.docusign_contract_id),
        "docusign_envelope_id": lifecycle.docusign_envelope_id
        or _clean_optional_text(params.docusign_envelope_id),
        "docusign_contract_url": lifecycle.docusign_contract_url
        or _clean_optional_text(params.docusign_contract_url),
        "docusign_status": _clean_optional_text(params.docusign_status),
        "docusign_event_id": _clean_optional_text(params.docusign_event_id),
    }
    return payload | {key: value for key, value in optional_values.items() if value}


def _manual_docusign_acceptance_payload(
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, str]:
    payload = {
        "signer_email": lifecycle.signer_email,
        "source": "manual_ae_verification",
    }
    optional_values = {
        "docusign_contract_id": lifecycle.docusign_contract_id,
        "docusign_envelope_id": lifecycle.docusign_envelope_id,
        "docusign_contract_url": lifecycle.docusign_contract_url,
    }
    return payload | {key: value for key, value in optional_values.items() if value}


def _enqueue_post_signature_sync_jobs(
    onboarding_repo: ClientOnboardingRepository,
    lifecycle: ClientOnboardingLifecycle,
    *,
    occurred_at: datetime,
) -> None:
    payload = _post_signature_sync_payload(lifecycle)
    database_job = onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.database,
        job_type=DATABASE_CONTRACT_ACCEPTANCE_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.database,
            DATABASE_CONTRACT_ACCEPTANCE_JOB_TYPE,
        ),
        payload=payload,
        available_at=occurred_at,
    )
    onboarding_repo.mark_sync_job_completed(
        database_job.id,
        result_payload={"contract_acceptance_recorded": True},
        occurred_at=occurred_at,
    )
    onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.folk,
        job_type=FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.folk,
            FOLK_CONTRACT_ACCEPTANCE_JOB_TYPE,
        ),
        payload=payload,
        available_at=occurred_at,
    )
    onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.slack,
        job_type=SLACK_HANDOFF_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.slack,
            SLACK_HANDOFF_JOB_TYPE,
        ),
        payload=payload,
        available_at=occurred_at,
    )
    onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.notion,
        job_type=NOTION_CMD_ENTRY_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.notion,
            NOTION_CMD_ENTRY_JOB_TYPE,
        ),
        payload=payload,
        available_at=occurred_at,
    )
    onboarding_repo.upsert_sync_job(
        lifecycle_id=lifecycle.id,
        target=ClientOnboardingSyncTarget.manage_app,
        job_type=MANAGE_APP_FDE_OWNER_JOB_TYPE,
        idempotency_key=_post_signature_sync_idempotency_key(
            lifecycle,
            ClientOnboardingSyncTarget.manage_app,
            MANAGE_APP_FDE_OWNER_JOB_TYPE,
        ),
        payload=payload,
        available_at=occurred_at,
    )


def _post_signature_sync_idempotency_key(
    lifecycle: ClientOnboardingLifecycle,
    target: ClientOnboardingSyncTarget,
    job_type: str,
) -> str:
    return f"client-onboarding:{lifecycle.id}:{target.value}:{job_type}"


def _post_signature_sync_payload(
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, str]:
    payload = {
        "lifecycle_id": str(lifecycle.id),
        "client_company_name": lifecycle.client_company_name,
        "signer_email": lifecycle.signer_email,
        "contract_type": lifecycle.contract_type.value,
    }
    optional_values = {
        "account_id": _optional_uuid(lifecycle.account_id),
        "manage_app_account_name": lifecycle.manage_app_account_name,
        "signer_name": lifecycle.signer_name,
        "docusign_contract_id": lifecycle.docusign_contract_id,
        "docusign_envelope_id": lifecycle.docusign_envelope_id,
        "docusign_contract_url": lifecycle.docusign_contract_url,
        "docusign_signed_at": _optional_datetime(lifecycle.docusign_signed_at),
        "ae_owner_user_id": _optional_uuid(lifecycle.ae_owner_user_id),
        "fde_owner_user_id": _optional_uuid(lifecycle.fde_owner_user_id),
        "folk_company_id": lifecycle.folk_company_id,
        "folk_contact_id": lifecycle.folk_contact_id,
        "slack_channel_id": lifecycle.slack_channel_id,
        "notion_page_id": lifecycle.notion_page_id,
        "scoping_doc_url": lifecycle.scoping_doc_url,
    }
    return payload | {key: value for key, value in optional_values.items() if value}


def _folk_contract_acceptance_payload(
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, Any]:
    from services.folk_notion_sync._settings import get_folk_notion_sync_settings

    settings = get_folk_notion_sync_settings()
    field_values = {
        "Account Name": lifecycle.manage_app_account_name,
        "Contract Signed Date": _optional_date(lifecycle.docusign_signed_at),
        "Contract Accepted At": _optional_datetime(lifecycle.docusign_signed_at),
        "Contract Accepted By": lifecycle.signer_email,
        "DocuSign Contract ID": lifecycle.docusign_contract_id,
        "DocuSign Envelope ID": lifecycle.docusign_envelope_id,
        "DocuSign Contract URL": lifecycle.docusign_contract_url,
        "Manage App Account ID": _optional_uuid(lifecycle.account_id),
        "Manage App Account Name": lifecycle.manage_app_account_name,
        "Signer Name": lifecycle.signer_name,
        "Signer Email": lifecycle.signer_email,
        "AE Owner User ID": _optional_uuid(lifecycle.ae_owner_user_id),
        "FDE Owner User ID": _optional_uuid(lifecycle.fde_owner_user_id),
        "Contract Type": lifecycle.contract_type.value,
    }
    clean_field_values = {
        key: value for key, value in field_values.items() if value is not None
    }
    return {"customFieldValues": {settings.folk_group_id: clean_field_values}}


def _folk_onboarding_company_payload(
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, str]:
    return {"name": lifecycle.client_company_name}


async def _resolve_or_create_folk_company(
    client: FolkContractAcceptanceClient,
    lifecycle: ClientOnboardingLifecycle,
) -> tuple[str, bool]:
    existing_company_id = await _find_folk_company_id_by_name(
        client,
        lifecycle.client_company_name,
    )
    if existing_company_id:
        return existing_company_id, False

    company = await client.create_company(_folk_onboarding_company_payload(lifecycle))
    return _created_folk_resource_id(company, "company"), True


async def _find_folk_company_id_by_name(
    client: FolkContractAcceptanceClient,
    company_name: str,
) -> str | None:
    target_name = _normalize_folk_company_name(company_name)
    for company in await client.list_companies():
        if _normalize_folk_company_name(_folk_company_name(company)) != target_name:
            continue
        company_id = company.get("id")
        if isinstance(company_id, str) and company_id.strip():
            return company_id
    return None


def _folk_company_name(company: dict[str, Any]) -> str:
    for key in ("name", "displayName", "title"):
        value = company.get(key)
        if isinstance(value, str):
            return value
    return ""


def _normalize_folk_company_name(company_name: str) -> str:
    return " ".join(company_name.casefold().split())


def _created_folk_resource_id(resource: dict[str, Any], resource_name: str) -> str:
    resource_id = resource.get("id")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise RuntimeError(f"Folk {resource_name} creation response did not include id")
    return resource_id


def _build_folk_contract_acceptance_client() -> FolkContractAcceptanceClient:
    from services.folk_notion_sync._folk import FolkClient
    from services.folk_notion_sync._settings import get_folk_notion_sync_settings

    return FolkClient(get_folk_notion_sync_settings())


async def _update_folk_contract_acceptance(
    client: FolkContractAcceptanceClient,
    lifecycle: ClientOnboardingLifecycle,
    payload: dict[str, Any],
) -> tuple[bool, bool]:
    updated_company = False
    updated_contact = False
    if lifecycle.folk_company_id:
        await client.update_company(lifecycle.folk_company_id, payload)
        updated_company = True
    if lifecycle.folk_contact_id:
        await client.update_contact(lifecycle.folk_contact_id, payload)
        updated_contact = True
    return updated_company, updated_contact


def _add_fde_owner_to_manage_app_account(
    session: Session,
    lifecycle: ClientOnboardingLifecycle,
    *,
    identity_provider: FdeOwnerIdentityProvider,
) -> _FdeOwnerAssignmentOutcome:
    if lifecycle.account_id is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing account id"
        )
    if lifecycle.fde_owner_user_id is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing FDE owner user id"
        )

    account_user_repo = AccountUserRepository(session, auto_commit=False)
    role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)
    existing_membership = account_user_repo.get_by_user_and_account(
        lifecycle.fde_owner_user_id,
        lifecycle.account_id,
    )
    membership_created = False
    membership_reactivated = False

    if existing_membership is not None:
        if existing_membership.status != AccountUserStatus.active:
            account_user_repo.update_status(
                lifecycle.fde_owner_user_id,
                lifecycle.account_id,
                AccountUserStatus.active,
            )
            membership_reactivated = True
    else:
        identity = _resolve_fde_owner_identity(
            account_user_repo,
            lifecycle.fde_owner_user_id,
            identity_provider=identity_provider,
        )
        account_user_repo.create(
            account_id=lifecycle.account_id,
            user_id=lifecycle.fde_owner_user_id,
            email=identity.email,
            name=identity.name or identity.email,
            added_by=lifecycle.ae_owner_user_id,
            status=AccountUserStatus.active,
        )
        membership_created = True

    owner_role_assigned = not role_repo.has_role(
        lifecycle.fde_owner_user_id,
        ResourceType.ACCOUNT,
        lifecycle.account_id,
        "owner",
    )
    if owner_role_assigned:
        role_repo.add_role(
            user_id=lifecycle.fde_owner_user_id,
            resource_type=ResourceType.ACCOUNT,
            resource_id=lifecycle.account_id,
            role="owner",
            assigned_by=lifecycle.ae_owner_user_id,
            reason="Client onboarding post-signature FDE ownership",
        )

    return _FdeOwnerAssignmentOutcome(
        account_id=lifecycle.account_id,
        fde_owner_user_id=lifecycle.fde_owner_user_id,
        membership_created=membership_created,
        membership_reactivated=membership_reactivated,
        owner_role_assigned=owner_role_assigned,
    )


def _resolve_fde_owner_identity(
    account_user_repo: AccountUserRepository,
    user_id: uuid.UUID,
    *,
    identity_provider: FdeOwnerIdentityProvider,
) -> _FdeOwnerIdentity:
    existing_membership = account_user_repo.get_by_user_id(user_id)
    existing_email = _account_user_text(existing_membership, "email")
    if existing_email:
        return _FdeOwnerIdentity(
            email=existing_email,
            name=_account_user_text(existing_membership, "name"),
        )

    identity = identity_provider.get_identity(user_id)
    email = _clean_optional_text(identity.email)
    if not email:
        raise ValueError(f"FDE owner {user_id} does not have an email")
    return _FdeOwnerIdentity(
        email=email,
        name=_clean_optional_text(identity.name),
    )


def _build_fde_owner_identity_provider() -> FdeOwnerIdentityProvider:
    return _CognitoFdeOwnerIdentityProvider()


class _CognitoFdeOwnerIdentityProvider:
    def get_identity(self, user_id: uuid.UUID) -> _FdeOwnerIdentity:
        import importlib
        import os

        try:
            user_pool_id = get_client_secret_with_fallback(
                "AWS_ADMIN_CONSOLE_USER_POOL_ID"
            )
        except ValueError as exc:
            raise RuntimeError(
                "AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured"
            ) from exc
        if not user_pool_id:
            raise RuntimeError("AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured")

        boto3 = importlib.import_module("boto3")
        response = boto3.client(
            "cognito-idp",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=_build_cognito_fde_owner_client_config(),
        ).list_users(
            UserPoolId=user_pool_id,
            Filter=f'sub="{user_id}"',
        )
        users = response.get("Users", [])
        if not users:
            raise ValueError(f"FDE owner {user_id} was not found in Cognito")
        attributes = users[0].get("Attributes", [])
        email = _cognito_attribute(attributes, "email")
        if not email:
            raise ValueError(f"FDE owner {user_id} does not have an email in Cognito")
        return _FdeOwnerIdentity(
            email=email,
            name=_cognito_attribute(attributes, "name"),
        )


def _build_cognito_fde_owner_client_config() -> Any:
    import importlib

    config_module = importlib.import_module("botocore.config")
    config_class = getattr(config_module, "Config")
    return config_class(
        connect_timeout=COGNITO_FDE_OWNER_CONNECT_TIMEOUT_SECONDS,
        read_timeout=COGNITO_FDE_OWNER_READ_TIMEOUT_SECONDS,
        retries={
            "max_attempts": COGNITO_FDE_OWNER_MAX_ATTEMPTS,
            "mode": "standard",
        },
    )


def _cognito_attribute(attributes: Any, key: str) -> str | None:
    if not isinstance(attributes, list):
        return None
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("Name") != key:
            continue
        value = attribute.get("Value")
        return value if isinstance(value, str) and value else None
    return None


def _build_notion_cmd_entry_client() -> NotionCmdEntryClient:
    from services.folk_notion_sync._notion import NotionDataSourceClient
    from services.folk_notion_sync._settings import get_folk_notion_sync_settings

    return NotionDataSourceClient(get_folk_notion_sync_settings())


async def _upsert_notion_cmd_entry(
    client: NotionCmdEntryClient,
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
) -> _NotionCmdEntryOutcome:
    company = _notion_company_projection(lifecycle, owner_contacts)
    if lifecycle.notion_page_id:
        await _update_existing_notion_cmd_entry(
            client, lifecycle.notion_page_id, lifecycle
        )
        return _NotionCmdEntryOutcome(
            notion_page_id=lifecycle.notion_page_id,
            created_page=False,
            updated_page=True,
        )

    page = await client.find_page(company)
    if page is not None:
        page_id = _notion_page_id_from_response(page)
        await _update_existing_notion_cmd_entry(client, page_id, lifecycle)
        return _NotionCmdEntryOutcome(
            notion_page_id=page_id,
            created_page=False,
            updated_page=True,
        )

    created_page = await client.create_page(
        _notion_cmd_entry_create_properties(lifecycle, company),
        children=_notion_cmd_entry_children(lifecycle, owner_contacts),
    )
    return _NotionCmdEntryOutcome(
        notion_page_id=_notion_page_id_from_response(created_page),
        created_page=True,
        updated_page=False,
    )


async def _update_existing_notion_cmd_entry(
    client: NotionCmdEntryClient,
    page_id: str,
    lifecycle: ClientOnboardingLifecycle,
) -> None:
    properties = _notion_cmd_entry_update_properties(lifecycle)
    if properties:
        await client.update_page(page_id, properties)


def _notion_cmd_entry_create_properties(
    lifecycle: ClientOnboardingLifecycle,
    company: CompanyProjection,
) -> dict[str, Any]:
    properties = build_notion_properties(
        company,
        source="client_onboarding",
        include_title=True,
    )
    if lifecycle.manage_app_account_name:
        properties["account_name"] = select_property(lifecycle.manage_app_account_name)
    return properties


def _notion_cmd_entry_update_properties(
    lifecycle: ClientOnboardingLifecycle,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    if lifecycle.manage_app_account_name:
        properties["account_name"] = select_property(lifecycle.manage_app_account_name)
    return properties


def _notion_company_projection(
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
) -> CompanyProjection:
    deal = DealProjection(
        id="",
        name=lifecycle.client_company_name,
        company_id=lifecycle.folk_company_id or "",
        company_name=lifecycle.client_company_name,
        stage="6. Onboarding",
        ae=_owner_contact_name(owner_contacts, "AE"),
        fde=_owner_contact_name(owner_contacts, "FDE"),
        product="",
        vendors="",
        total_locations="",
        deal_locations="",
        live_locations="",
        contract_signed_date=_optional_date(lifecycle.docusign_signed_at) or "",
        go_live_date="",
        lead_source="",
        billing_details="",
        billing_method="",
        billing_status="",
        brand_structure="",
        key_account="",
        carr="",
        price_per_month_per_location="",
    )
    return CompanyProjection(
        key=lifecycle.folk_company_id or str(lifecycle.id),
        name=lifecycle.client_company_name,
        company_id=lifecycle.folk_company_id or "",
        deals=[deal],
        industry="",
        cuisine_type="",
        description="",
        addresses="",
        emails=lifecycle.signer_email,
        phones="",
        urls="",
        primary_contacts=_signer_label(lifecycle),
    )


def _notion_cmd_entry_children(
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
) -> list[dict[str, Any]]:
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "Client onboarding handoff"},
                    }
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": _notion_cmd_entry_summary(
                                lifecycle,
                                owner_contacts,
                            )
                        },
                    }
                ]
            },
        },
    ]


def _notion_cmd_entry_summary(
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
) -> str:
    values = {
        "Manage App account": _manage_app_account_label(lifecycle),
        "Signer": _signer_label(lifecycle),
        "Signed at": _optional_datetime(lifecycle.docusign_signed_at),
        "Contract type": lifecycle.contract_type.value,
        "DocuSign envelope": lifecycle.docusign_envelope_id,
        "DocuSign contract": lifecycle.docusign_contract_id,
        "DocuSign URL": lifecycle.docusign_contract_url,
        "Scoping doc": lifecycle.scoping_doc_url,
        "Slack channel ID": lifecycle.slack_channel_id,
        "Folk company ID": lifecycle.folk_company_id,
        "Folk contact ID": lifecycle.folk_contact_id,
        "Owners": _notion_owner_summary(owner_contacts),
    }
    lines = [f"{key}: {value}" for key, value in values.items() if value]
    return "\n".join(lines)[:2000]


def _notion_page_id_from_response(response: dict[str, Any]) -> str:
    page_id = response.get("id")
    if not isinstance(page_id, str) or not page_id.strip():
        raise RuntimeError("Notion page response did not include page id")
    return page_id


def _notion_owner_summary(owner_contacts: list[_OwnerContact]) -> str | None:
    values: list[str] = []
    for owner in owner_contacts:
        if owner.name:
            values.append(f"{owner.role}: {owner.name}")
        elif owner.email:
            values.append(f"{owner.role}: {owner.email}")
        else:
            values.append(f"{owner.role}: {owner.user_id}")
    return " | ".join(values) if values else None


def _owner_contact_name(owner_contacts: list[_OwnerContact], role: str) -> str:
    for owner in owner_contacts:
        if owner.role == role:
            return owner.name or owner.email or ""
    return ""


def _build_slack_handoff_client() -> SlackHandoffClient:
    from services.slack_service._client import get_slack_client

    return _SlackHandoffClientAdapter(get_slack_client())


class _SlackHandoffClientAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def create_channel(
        self,
        *,
        name: str,
        is_private: bool,
    ) -> dict[str, Any]:
        response = await self.client.conversations_create(
            name=name,
            is_private=is_private,
        )
        return _slack_response_to_dict(response)

    async def invite_users(
        self,
        *,
        channel_id: str,
        user_ids: list[str],
    ) -> dict[str, Any]:
        response = await self.client.conversations_invite(
            channel=channel_id,
            users=user_ids,
        )
        return _slack_response_to_dict(response)

    async def post_message(
        self,
        *,
        channel_id: str,
        text: str,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response = await self.client.chat_postMessage(
            channel=channel_id,
            text=text,
            blocks=blocks,
            mrkdwn=True,
        )
        return _slack_response_to_dict(response)

    async def lookup_user_id_by_email(
        self,
        *,
        email: str,
    ) -> str | None:
        try:
            response = await self.client.users_lookupByEmail(email=email)
        except Exception:
            return None
        data = _slack_response_to_dict(response)
        if data.get("ok") is False:
            return None
        user = data.get("user")
        if not isinstance(user, dict):
            return None
        slack_user_id = user.get("id")
        return slack_user_id if isinstance(slack_user_id, str) else None

    async def find_channel_id_by_name(
        self,
        *,
        name: str,
    ) -> str | None:
        cursor = None
        while True:
            response = await self.client.conversations_list(
                exclude_archived=True,
                limit=200,
                types="public_channel,private_channel",
                cursor=cursor,
            )
            data = _slack_response_to_dict(response)
            if data.get("ok") is False:
                return None
            channels = data.get("channels")
            if isinstance(channels, list):
                for channel in channels:
                    if not isinstance(channel, dict):
                        continue
                    if channel.get("name") != name:
                        continue
                    channel_id = channel.get("id")
                    return channel_id if isinstance(channel_id, str) else None
            metadata = data.get("response_metadata")
            next_cursor = (
                metadata.get("next_cursor") if isinstance(metadata, dict) else None
            )
            if not isinstance(next_cursor, str) or not next_cursor:
                return None
            cursor = next_cursor


async def _ensure_slack_handoff_channel(
    client: SlackHandoffClient,
    lifecycle: ClientOnboardingLifecycle,
) -> _SlackHandoffChannel:
    channel_name = _slack_channel_name(lifecycle)
    if lifecycle.slack_channel_id:
        return _SlackHandoffChannel(
            channel_id=lifecycle.slack_channel_id,
            channel_name=channel_name,
            created=False,
        )

    response = await client.create_channel(name=channel_name, is_private=False)
    if response.get("ok") is False and response.get("error") == "name_taken":
        existing_channel_id = await client.find_channel_id_by_name(name=channel_name)
        if existing_channel_id:
            return _SlackHandoffChannel(
                channel_id=existing_channel_id,
                channel_name=channel_name,
                created=False,
            )
    _raise_for_slack_error(response, "create handoff channel")
    channel = response.get("channel")
    if not isinstance(channel, dict):
        raise RuntimeError("Slack channel creation response did not include channel")
    channel_id = channel.get("id")
    if not isinstance(channel_id, str) or not channel_id.strip():
        raise RuntimeError("Slack channel creation response did not include channel id")
    response_channel_name = channel.get("name")
    return _SlackHandoffChannel(
        channel_id=channel_id,
        channel_name=(
            response_channel_name
            if isinstance(response_channel_name, str) and response_channel_name
            else channel_name
        ),
        created=True,
    )


async def _post_slack_handoff(
    client: SlackHandoffClient,
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
    *,
    channel_id: str,
    channel_name: str,
    created_channel: bool,
) -> _SlackHandoffOutcome:
    slack_user_ids_by_owner = await _resolve_slack_user_ids_by_owner(
        client,
        owner_contacts,
    )
    invited_user_ids = list(dict.fromkeys(slack_user_ids_by_owner.values()))
    invite_error = None
    if invited_user_ids:
        try:
            invite_response = await client.invite_users(
                channel_id=channel_id,
                user_ids=invited_user_ids,
            )
            _raise_for_slack_error(invite_response, "invite handoff owners")
        except Exception as exc:
            invite_error = str(exc)

    message = _slack_handoff_message(
        lifecycle,
        owner_contacts,
        slack_user_ids_by_owner,
        channel_name=channel_name,
    )
    message_response = await client.post_message(
        channel_id=channel_id,
        text=message.text,
        blocks=message.blocks,
    )
    _raise_for_slack_error(message_response, "post handoff message")
    return _SlackHandoffOutcome(
        channel_id=channel_id,
        channel_name=channel_name,
        created_channel=created_channel,
        invited_user_ids=invited_user_ids,
        unresolved_owner_user_ids=[
            str(owner.user_id)
            for owner in owner_contacts
            if str(owner.user_id) not in slack_user_ids_by_owner
        ],
        message_ts=_payload_text(message_response, "ts"),
        invite_error=invite_error,
    )


async def _resolve_slack_user_ids_by_owner(
    client: SlackHandoffClient,
    owner_contacts: list[_OwnerContact],
) -> dict[str, str]:
    slack_user_ids: dict[str, str] = {}
    for owner in owner_contacts:
        if not owner.email:
            continue
        slack_user_id = await client.lookup_user_id_by_email(email=owner.email)
        if slack_user_id:
            slack_user_ids[str(owner.user_id)] = slack_user_id
    return slack_user_ids


def _slack_handoff_message(
    lifecycle: ClientOnboardingLifecycle,
    owner_contacts: list[_OwnerContact],
    slack_user_ids_by_owner: dict[str, str],
    *,
    channel_name: str,
) -> _SlackHandoffMessage:
    company_name = lifecycle.client_company_name
    owner_line = _slack_owner_mentions(owner_contacts, slack_user_ids_by_owner)
    fields = _slack_handoff_fields(lifecycle, channel_name=channel_name)
    text = f"Contract signed for {company_name}. {owner_line}"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": _truncate_slack_text(f"{company_name} contract signed", 150),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{owner_line}\n"
                    "The client contract is signed. Continue the internal handoff "
                    "from the records below."
                ),
            },
        },
    ]
    if fields:
        blocks.append({"type": "section", "fields": fields})
    return _SlackHandoffMessage(text=text, blocks=blocks)


def _slack_owner_mentions(
    owner_contacts: list[_OwnerContact],
    slack_user_ids_by_owner: dict[str, str],
) -> str:
    labels: list[str] = []
    for owner in owner_contacts:
        slack_user_id = slack_user_ids_by_owner.get(str(owner.user_id))
        if slack_user_id:
            labels.append(f"{owner.role}: <@{slack_user_id}>")
        elif owner.name:
            labels.append(f"{owner.role}: {owner.name}")
        elif owner.email:
            labels.append(f"{owner.role}: {owner.email}")
        else:
            labels.append(f"{owner.role}: {owner.user_id}")
    return " | ".join(labels) if labels else "No AE/FDE owner was linked."


def _slack_handoff_fields(
    lifecycle: ClientOnboardingLifecycle,
    *,
    channel_name: str,
) -> list[dict[str, Any]]:
    values = {
        "Slack channel": f"#{channel_name}",
        "Signer": _signer_label(lifecycle),
        "Signed at": _optional_datetime(lifecycle.docusign_signed_at),
        "Contract type": lifecycle.contract_type.value,
        "Manage App account": _manage_app_account_label(lifecycle),
        "DocuSign": _slack_link(
            lifecycle.docusign_contract_url,
            lifecycle.docusign_envelope_id or lifecycle.docusign_contract_id,
        ),
        "Folk company": _slack_link(
            _folk_company_url(lifecycle.folk_company_id),
            lifecycle.folk_company_id,
        ),
        "Folk contact": lifecycle.folk_contact_id,
        "Notion": _slack_link(
            _notion_page_url(lifecycle.notion_page_id),
            lifecycle.notion_page_id,
        ),
        "Scoping doc": _slack_link(lifecycle.scoping_doc_url, "Open scoping doc"),
    }
    return [
        {"type": "mrkdwn", "text": f"*{key}:*\n{value}"}
        for key, value in values.items()
        if value
    ]


def _resolve_handoff_owner_contacts(
    session: Session,
    lifecycle: ClientOnboardingLifecycle,
) -> list[_OwnerContact]:
    account_user_repo = AccountUserRepository(session, auto_commit=False)
    contacts: list[_OwnerContact] = []
    for role, user_id in (
        ("AE", lifecycle.ae_owner_user_id),
        ("FDE", lifecycle.fde_owner_user_id),
    ):
        if user_id is None:
            continue
        account_user = None
        if lifecycle.account_id is not None:
            account_user = account_user_repo.get_by_user_and_account(
                user_id,
                lifecycle.account_id,
            )
        if account_user is None:
            account_user = account_user_repo.get_by_user_id(user_id)
        contacts.append(
            _OwnerContact(
                role=role,
                user_id=user_id,
                email=_account_user_text(account_user, "email"),
                name=_account_user_text(account_user, "name"),
            )
        )
    return contacts


def _slack_channel_name(lifecycle: ClientOnboardingLifecycle) -> str:
    base_name = lifecycle.manage_app_account_name or lifecycle.client_company_name
    normalized = base_name.casefold().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9_-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    if not normalized:
        normalized = "client"
    channel_name = f"client-{normalized}"
    return channel_name[:80].rstrip("-_") or "client-onboarding"


def _raise_for_slack_error(response: dict[str, Any], action: str) -> None:
    if response.get("ok") is False:
        error = response.get("error")
        raise RuntimeError(
            f"Slack failed to {action}: {error if isinstance(error, str) else 'unknown error'}"
        )


def _slack_response_to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    try:
        return dict(response)
    except (TypeError, ValueError):
        return {}


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _payload_text_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _account_user_text(account_user: Any, field_name: str) -> str | None:
    value = getattr(account_user, field_name, None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _signer_label(lifecycle: ClientOnboardingLifecycle) -> str:
    if lifecycle.signer_name:
        return f"{lifecycle.signer_name} <{lifecycle.signer_email}>"
    return lifecycle.signer_email


def _manage_app_account_label(lifecycle: ClientOnboardingLifecycle) -> str | None:
    if lifecycle.manage_app_account_name and lifecycle.account_id:
        return f"{lifecycle.manage_app_account_name} ({lifecycle.account_id})"
    return lifecycle.manage_app_account_name or _optional_uuid(lifecycle.account_id)


def _slack_link(url: str | None, label: str | None) -> str | None:
    if not url or not label:
        return label
    return f"<{url}|{label}>"


def _folk_company_url(folk_company_id: str | None) -> str | None:
    if not folk_company_id:
        return None
    return f"https://app.folk.app/apps/contacts/companies/{folk_company_id}"


def _notion_page_url(notion_page_id: str | None) -> str | None:
    if not notion_page_id:
        return None
    return f"https://www.notion.so/{notion_page_id}"


def _truncate_slack_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return value[: max_length - 3].rstrip() + "..."


def _run_async(
    coro: Coroutine[Any, Any, T],
) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "Cannot run client onboarding sync while an event loop is already running"
    )


def _raise_for_docusign_reference_mismatch(
    lifecycle: ClientOnboardingLifecycle,
    *,
    docusign_contract_id: str | None,
    docusign_envelope_id: str | None,
    docusign_contract_url: str | None,
) -> None:
    mismatched_fields = [
        field_name
        for field_name, supplied_value, lifecycle_value in (
            (
                "docusign_contract_id",
                docusign_contract_id,
                lifecycle.docusign_contract_id,
            ),
            (
                "docusign_envelope_id",
                docusign_envelope_id,
                lifecycle.docusign_envelope_id,
            ),
            (
                "docusign_contract_url",
                docusign_contract_url,
                lifecycle.docusign_contract_url,
            ),
        )
        if supplied_value and _clean_optional_text(lifecycle_value) != supplied_value
    ]
    if mismatched_fields:
        raise ClientOnboardingInviteInvalidError(
            "Supplied DocuSign references do not all match the same lifecycle: "
            + ", ".join(mismatched_fields)
        )


@dataclass(frozen=True)
class _ResolvedClientOnboardingInvite:
    invitation: UserInvitation
    lifecycle: ClientOnboardingLifecycle
    account_name: str
    account_display_name: str | None
    docusign_sender_name: str


def _resolve_client_onboarding_invite(
    session: Session,
    invitation_token: str,
    allowed_invitation_statuses: set[InvitationStatus] | None = None,
) -> _ResolvedClientOnboardingInvite:
    from services import team_service

    allowed_statuses = allowed_invitation_statuses or {InvitationStatus.pending}
    invitation_details = team_service.get_invitation_details(session, invitation_token)
    if not invitation_details:
        raise ClientOnboardingInviteNotFoundError("Invitation not found")

    invitation, account_name, account_display_name, inviter_name = invitation_details
    if invitation.status not in allowed_statuses:
        raise ClientOnboardingInviteInvalidError(
            f"Invitation is {invitation.status.value}"
        )

    onboarding_repo = ClientOnboardingRepository(session)
    lifecycle = onboarding_repo.get_by_invite_id(invitation.id)
    if not lifecycle:
        raise ClientOnboardingInviteNotFoundError(
            "Client onboarding lifecycle not found for invitation"
        )

    if lifecycle.status in {
        ClientOnboardingStatus.blocked,
        ClientOnboardingStatus.cancelled,
    }:
        raise ClientOnboardingInviteInvalidError(
            f"Client onboarding lifecycle is {lifecycle.status.value}"
        )

    return _ResolvedClientOnboardingInvite(
        invitation=invitation,
        lifecycle=lifecycle,
        account_name=account_name,
        account_display_name=account_display_name,
        docusign_sender_name=inviter_name,
    )


def _resolve_client_onboarding_invite_for_password_set(
    *,
    session: Session,
    invitation_token: str,
    context: UserContext,
) -> _ResolvedClientOnboardingInvite:
    resolved = _resolve_client_onboarding_invite(
        session,
        invitation_token,
        allowed_invitation_statuses={
            InvitationStatus.pending,
            InvitationStatus.accepted,
        },
    )
    context_email = _normalize_email(context.email)
    invitation_email = _normalize_email(resolved.invitation.email)
    signer_email = _normalize_email(resolved.lifecycle.signer_email)
    if context_email != invitation_email or context_email != signer_email:
        raise ClientOnboardingInviteInvalidError(
            "Authenticated user does not match client onboarding signer"
        )
    return resolved


def _create_docusign_embed_url(
    lifecycle: ClientOnboardingLifecycle,
    invitation_token: str,
) -> str | None:
    envelope_id = _clean_optional_text(lifecycle.docusign_envelope_id)
    if not envelope_id:
        return None

    client = _build_docusign_embedded_signing_client()
    if client is None:
        return None
    admin_console_base_url = _docusign_admin_console_base_url()
    if admin_console_base_url is None:
        return None

    try:
        return client.create_recipient_view(
            envelope_id=envelope_id,
            signer_email=lifecycle.signer_email,
            signer_name=lifecycle.signer_name or lifecycle.signer_email,
            client_user_id=str(lifecycle.invite_id or lifecycle.id),
            return_url=_build_docusign_return_url(
                admin_console_base_url,
                invitation_token,
            ),
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 - invite page must fall back to emailed DocuSign.
        logger.warning(
            "Unable to create DocuSign embedded signing URL",
            extra={
                "lifecycle_id": str(lifecycle.id),
                "envelope_id": envelope_id,
                "signer_email": lifecycle.signer_email,
                "error": str(exc),
            },
        )
        return None


def _build_docusign_embedded_signing_client() -> DocusignEmbeddedSigningClient | None:
    config = _load_docusign_embedded_signing_config()
    if config is None:
        return None
    return _DocusignEmbeddedSigningHttpClient(config)


def _load_docusign_embedded_signing_config() -> _DocusignEmbeddedSigningConfig | None:
    account_id = _docusign_secret_value("DOCUSIGN_ACCOUNT_ID")
    integration_key = _docusign_secret_value("DOCUSIGN_INTEGRATION_KEY")
    impersonated_user_id = _docusign_secret_value("DOCUSIGN_IMPERSONATED_USER_ID")
    private_key = _docusign_secret_value("DOCUSIGN_PRIVATE_KEY")
    auth_server = _docusign_secret_value("DOCUSIGN_AUTH_SERVER")
    rest_api_base_url = _docusign_secret_value("DOCUSIGN_REST_API_BASE_URL")
    admin_console_base_url = _docusign_admin_console_base_url()

    if (
        account_id is None
        or integration_key is None
        or impersonated_user_id is None
        or private_key is None
        or auth_server is None
        or rest_api_base_url is None
        or admin_console_base_url is None
    ):
        return None

    return _DocusignEmbeddedSigningConfig(
        account_id=account_id,
        integration_key=integration_key,
        impersonated_user_id=impersonated_user_id,
        private_key=private_key.replace("\\n", "\n"),
        auth_server=auth_server,
        rest_api_base_url=rest_api_base_url.rstrip("/"),
    )


def _docusign_secret_value(secret_key: str) -> str | None:
    try:
        value = get_server_secret_with_fallback(secret_key)
    except ValueError:
        return None
    return _clean_optional_text(value)


def _docusign_admin_console_base_url() -> str | None:
    return _docusign_secret_value(
        "PAL_ADMIN_CONSOLE_BASE_URL"
    ) or _docusign_secret_value("PAL_CONSOLE_BASE_URL")


def _build_docusign_return_url(
    admin_console_base_url: str, invitation_token: str
) -> str:
    base_url = admin_console_base_url.rstrip("/")
    query = urlencode(
        {
            "invitation_token": invitation_token,
            "docusign_return": "1",
        }
    )
    return f"{base_url}{DOCUSIGN_EMBED_RETURN_PATH}?{query}"


class _DocusignEmbeddedSigningHttpClient:
    def __init__(self, config: _DocusignEmbeddedSigningConfig) -> None:
        self.config = config

    def create_recipient_view(
        self,
        *,
        envelope_id: str,
        signer_email: str,
        signer_name: str,
        client_user_id: str,
        return_url: str,
    ) -> str:
        import jwt
        import requests

        access_token = self._create_access_token(jwt, requests)
        response = requests.post(
            (
                f"{self.config.rest_api_base_url}/v2.1/accounts/"
                f"{self.config.account_id}/envelopes/{envelope_id}/views/recipient"
            ),
            json={
                "returnUrl": return_url,
                "authenticationMethod": "none",
                "email": signer_email,
                "userName": signer_name,
                "clientUserId": client_user_id,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=DOCUSIGN_EMBED_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            raise RuntimeError("DocuSign recipient view response did not include url")
        return url

    def _create_access_token(self, jwt_module: Any, requests_module: Any) -> str:
        now = int(datetime.now(timezone.utc).timestamp())
        assertion = jwt_module.encode(
            {
                "iss": self.config.integration_key,
                "sub": self.config.impersonated_user_id,
                "aud": self.config.auth_server,
                "iat": now,
                "exp": now + 300,
                "scope": DOCUSIGN_EMBED_OAUTH_SCOPE,
            },
            self.config.private_key,
            algorithm="RS256",
        )
        response = requests_module.post(
            f"https://{self.config.auth_server}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=DOCUSIGN_EMBED_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise RuntimeError("DocuSign OAuth response did not include access_token")
        return access_token


def _build_invite_step_result(
    resolved: _ResolvedClientOnboardingInvite,
    lifecycle: ClientOnboardingLifecycle,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    if lifecycle.account_id is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing account id"
        )

    status = lifecycle.status
    docusign_required = status not in POST_SIGNATURE_STATUSES
    docusign_embed_url = (
        _create_docusign_embed_url(lifecycle, invitation_token)
        if docusign_required
        else None
    )
    sender_name = resolved.docusign_sender_name or "your Palona AE"

    return ClientOnboardingInviteStepResult(
        lifecycle_id=lifecycle.id,
        lifecycle_status=status,
        account_id=lifecycle.account_id,
        account_name=resolved.account_name,
        account_display_name=resolved.account_display_name,
        client_company_name=lifecycle.client_company_name,
        signer_name=lifecycle.signer_name,
        signer_email=lifecycle.signer_email,
        docusign_required=docusign_required,
        docusign_embed_url=docusign_embed_url,
        docusign_contract_url=lifecycle.docusign_contract_url,
        docusign_contract_id=lifecycle.docusign_contract_id,
        docusign_envelope_id=lifecycle.docusign_envelope_id,
        docusign_sender_name=sender_name,
        fallback_message=f"Please check your email for a contract from {sender_name} via DocuSign.",
        password_setup_available=status in POST_SIGNATURE_STATUSES,
    )


def _parse_user_id(username: str) -> uuid.UUID:
    try:
        return uuid.UUID(username)
    except ValueError as exc:
        raise ValueError("Authenticated AE user id is not a valid UUID") from exc


def _parse_optional_user_id(username: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(username)
    except ValueError:
        return None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _coerce_event_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _optional_uuid(value: uuid.UUID | None) -> str | None:
    return str(value) if value else None


def _optional_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _optional_date(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None
