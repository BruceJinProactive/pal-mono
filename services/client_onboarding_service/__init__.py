from sqlalchemy.orm import Session

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
    from ._implementation import create_client_onboarding_account as _create

    return _create(session=session, context=context, params=params)


__all__ = [
    "CreateClientOnboardingAccountParams",
    "CreateClientOnboardingAccountResult",
    "DuplicateClientOnboardingError",
    "create_client_onboarding_account",
]
