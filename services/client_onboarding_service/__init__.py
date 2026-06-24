from uuid import UUID

from sqlalchemy.orm import Session

from services.auth_types import UserContext

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


def sync_client_onboarding_slack_handoff(
    session: Session,
    lifecycle_id: UUID,
) -> ClientOnboardingSlackHandoffResult:
    from ._implementation import sync_client_onboarding_slack_handoff as _sync

    return _sync(session=session, lifecycle_id=lifecycle_id)


def sync_client_onboarding_notion_cmd_entry(
    session: Session,
    lifecycle_id: UUID,
) -> ClientOnboardingNotionSyncResult:
    from ._implementation import sync_client_onboarding_notion_cmd_entry as _sync

    return _sync(session=session, lifecycle_id=lifecycle_id)


def sync_client_onboarding_fde_owner_assignment(
    session: Session,
    lifecycle_id: UUID,
) -> ClientOnboardingFdeOwnerAssignmentResult:
    from ._implementation import sync_client_onboarding_fde_owner_assignment as _sync

    return _sync(session=session, lifecycle_id=lifecycle_id)


def orchestrate_client_onboarding_handoff_completion(
    session: Session,
    lifecycle_id: UUID,
) -> ClientOnboardingHandoffCompletionResult:
    from ._implementation import (
        orchestrate_client_onboarding_handoff_completion as _orchestrate,
    )

    return _orchestrate(session=session, lifecycle_id=lifecycle_id)


__all__ = [
    "ClientOnboardingFdeOwnerAssignmentResult",
    "ClientOnboardingFolkSyncResult",
    "ClientOnboardingHandoffCompletionResult",
    "ClientOnboardingInviteInvalidError",
    "ClientOnboardingInviteNotFoundError",
    "ClientOnboardingInviteStepResult",
    "ClientOnboardingNotionSyncResult",
    "ClientOnboardingSlackHandoffResult",
    "CreateClientOnboardingAccountParams",
    "CreateClientOnboardingAccountResult",
    "DuplicateClientOnboardingError",
    "ReconcileClientOnboardingDocusignCompletionParams",
    "ReconcileClientOnboardingDocusignCompletionResult",
    "create_client_onboarding_account",
    "get_client_onboarding_invite_step",
    "mark_client_onboarding_docusign_viewed",
    "mark_client_onboarding_password_set",
    "orchestrate_client_onboarding_handoff_completion",
    "reconcile_client_onboarding_docusign_completion",
    "sync_client_onboarding_contract_acceptance_to_folk",
    "sync_client_onboarding_fde_owner_assignment",
    "sync_client_onboarding_notion_cmd_entry",
    "sync_client_onboarding_slack_handoff",
]
