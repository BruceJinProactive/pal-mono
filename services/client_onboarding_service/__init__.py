from uuid import UUID

from sqlalchemy.orm import Session

from services.auth_types import UserContext

from .schema import (
    ClientOnboardingFolkSyncResult,
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
    CreateClientOnboardingAccountParams,
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
    ReconcileClientOnboardingDocusignCompletionParams,
    ReconcileClientOnboardingDocusignCompletionResult,
)


def create_client_onboarding_account(
    session: Session,
    context: UserContext,
    params: CreateClientOnboardingAccountParams,
) -> CreateClientOnboardingAccountResult:
    from ._implementation import create_client_onboarding_account as _create

    return _create(session=session, context=context, params=params)


def get_client_onboarding_invite_step(
    session: Session,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    from ._implementation import get_client_onboarding_invite_step as _get

    return _get(session=session, invitation_token=invitation_token)


def mark_client_onboarding_docusign_viewed(
    session: Session,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    from ._implementation import mark_client_onboarding_docusign_viewed as _mark

    return _mark(session=session, invitation_token=invitation_token)


def mark_client_onboarding_password_set(
    session: Session,
    context: UserContext,
    invitation_token: str,
) -> ClientOnboardingInviteStepResult:
    from ._implementation import mark_client_onboarding_password_set as _mark

    return _mark(session=session, context=context, invitation_token=invitation_token)


def reconcile_client_onboarding_docusign_completion(
    session: Session,
    params: ReconcileClientOnboardingDocusignCompletionParams,
) -> ReconcileClientOnboardingDocusignCompletionResult:
    from ._implementation import (
        reconcile_client_onboarding_docusign_completion as _reconcile,
    )

    return _reconcile(session=session, params=params)


def sync_client_onboarding_contract_acceptance_to_folk(
    session: Session,
    lifecycle_id: UUID,
) -> ClientOnboardingFolkSyncResult:
    from ._implementation import (
        sync_client_onboarding_contract_acceptance_to_folk as _sync,
    )

    return _sync(session=session, lifecycle_id=lifecycle_id)


__all__ = [
    "ClientOnboardingFolkSyncResult",
    "ClientOnboardingInviteInvalidError",
    "ClientOnboardingInviteNotFoundError",
    "ClientOnboardingInviteStepResult",
    "CreateClientOnboardingAccountParams",
    "CreateClientOnboardingAccountResult",
    "DuplicateClientOnboardingError",
    "ReconcileClientOnboardingDocusignCompletionParams",
    "ReconcileClientOnboardingDocusignCompletionResult",
    "create_client_onboarding_account",
    "get_client_onboarding_invite_step",
    "mark_client_onboarding_docusign_viewed",
    "mark_client_onboarding_password_set",
    "reconcile_client_onboarding_docusign_completion",
    "sync_client_onboarding_contract_acceptance_to_folk",
]
