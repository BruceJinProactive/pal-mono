from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

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
    UserInvitation,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.types import AccountUserStatus, InvitationStatus
from services import account_service
from services.account_service import AccountParams
from services.auth_types import UserContext

from .schema import (
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
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
                contract_signed=False,
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
    session.commit()

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

    return _build_invite_step_result(resolved, lifecycle)


def mark_client_onboarding_docusign_viewed(
    session: Session,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    resolved = _resolve_client_onboarding_invite(session, invitation_token)
    lifecycle = resolved.lifecycle

    if not lifecycle.docusign_contract_url and lifecycle.status not in {
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

    return _build_invite_step_result(resolved, lifecycle)


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

    if lifecycle.status == ClientOnboardingStatus.docusign_signed:
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
                next_status=ClientOnboardingStatus.password_set,
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

    return _build_invite_step_result(resolved, lifecycle)


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
            session.commit()
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


def _build_invite_step_result(
    resolved: _ResolvedClientOnboardingInvite,
    lifecycle: ClientOnboardingLifecycle,
) -> ClientOnboardingInviteStepResult:
    if lifecycle.account_id is None:
        raise ClientOnboardingInviteInvalidError(
            "Client onboarding lifecycle is missing account id"
        )

    status = lifecycle.status
    docusign_required = status not in POST_SIGNATURE_STATUSES
    docusign_embed_url = lifecycle.docusign_contract_url if docusign_required else None
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
