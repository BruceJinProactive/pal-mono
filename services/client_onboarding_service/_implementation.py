from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.pal_repository.client_onboarding import ClientOnboardingRepository
from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
    ResourceType,
)
from db.tables import (
    Account,
    ClientOnboardingActivitySource,
    ClientOnboardingActorType,
    ClientOnboardingStatus,
    UserInvitation,
)
from db.tables.accounts import AccountStatus, OnboardingMethod
from db.tables.types import AccountUserStatus
from services import account_service
from services.account_service import AccountParams
from services.auth_types import UserContext

from .schema import (
    CreateClientOnboardingAccountParams,
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
)


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


def _parse_user_id(username: str) -> uuid.UUID:
    try:
        return uuid.UUID(username)
    except ValueError as exc:
        raise ValueError("Authenticated AE user id is not a valid UUID") from exc


def _normalize_email(email: str) -> str:
    return email.strip().lower()
