from sqlalchemy.orm import Session

from services.auth_types import UserContext

from .schema import (
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
    CreateClientOnboardingAccountParams,
    CreateClientOnboardingAccountResult,
    DuplicateClientOnboardingError,
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


__all__ = [
    "ClientOnboardingInviteInvalidError",
    "ClientOnboardingInviteNotFoundError",
    "ClientOnboardingInviteStepResult",
    "CreateClientOnboardingAccountParams",
    "CreateClientOnboardingAccountResult",
    "DuplicateClientOnboardingError",
    "create_client_onboarding_account",
    "get_client_onboarding_invite_step",
    "mark_client_onboarding_docusign_viewed",
]
