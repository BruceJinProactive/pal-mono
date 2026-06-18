from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.onboarding import (
    CreateClientOnboardingAccountRequest,
    CreateClientOnboardingAccountResponse,
)
from services import client_onboarding_service
from services.client_onboarding_service import DuplicateClientOnboardingError


def create_client_onboarding_account(
    request: CreateClientOnboardingAccountRequest,
    context: UserContext,
    session: Session,
) -> CreateClientOnboardingAccountResponse:
    try:
        result = client_onboarding_service.create_client_onboarding_account(
            session=session,
            context=context,
            params=request.to_service_params(),
        )
    except DuplicateClientOnboardingError as err:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err

    return CreateClientOnboardingAccountResponse(
        account_id=result.account_id,
        account_name=result.account_name,
        account_created=result.account_created,
        lifecycle_id=result.lifecycle_id,
        lifecycle_status=result.lifecycle_status,
        invitation_id=result.invitation_id,
        signer_email=result.signer_email,
        ae_owner_user_id=result.ae_owner_user_id,
        fde_owner_user_id=result.fde_owner_user_id,
    )
