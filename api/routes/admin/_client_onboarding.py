from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext
from api.schemas.admin.onboarding import (
    ClientOnboardingInviteStepResponse,
    CreateClientOnboardingAccountRequest,
    CreateClientOnboardingAccountResponse,
    ReconcileClientOnboardingDocusignCompletionRequest,
    ReconcileClientOnboardingDocusignCompletionResponse,
)
from services import client_onboarding_service
from services.client_onboarding_service import (
    ClientOnboardingInviteInvalidError,
    ClientOnboardingInviteNotFoundError,
    ClientOnboardingInviteStepResult,
    DuplicateClientOnboardingError,
    ReconcileClientOnboardingDocusignCompletionResult,
)


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


def get_client_onboarding_invite_step(
    invitation_token: str,
    session: Session,
) -> ClientOnboardingInviteStepResponse:
    try:
        result = client_onboarding_service.get_client_onboarding_invite_step(
            session=session,
            invitation_token=invitation_token,
        )
    except ClientOnboardingInviteNotFoundError as err:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err
    except ClientOnboardingInviteInvalidError as err:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err

    return _to_invite_step_response(result)


def mark_client_onboarding_docusign_viewed(
    invitation_token: str,
    session: Session,
) -> ClientOnboardingInviteStepResponse:
    try:
        result = client_onboarding_service.mark_client_onboarding_docusign_viewed(
            session=session,
            invitation_token=invitation_token,
        )
    except ClientOnboardingInviteNotFoundError as err:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err
    except ClientOnboardingInviteInvalidError as err:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err

    return _to_invite_step_response(result)


def reconcile_client_onboarding_docusign_completion(
    request: ReconcileClientOnboardingDocusignCompletionRequest,
    session: Session,
) -> ReconcileClientOnboardingDocusignCompletionResponse:
    try:
        result = (
            client_onboarding_service.reconcile_client_onboarding_docusign_completion(
                session=session,
                params=request.to_service_params(),
            )
        )
    except ClientOnboardingInviteNotFoundError as err:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err
    except ClientOnboardingInviteInvalidError as err:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        ) from err

    return _to_docusign_completion_response(result)


def _to_invite_step_response(
    result: ClientOnboardingInviteStepResult,
) -> ClientOnboardingInviteStepResponse:
    return ClientOnboardingInviteStepResponse(
        lifecycle_id=result.lifecycle_id,
        lifecycle_status=result.lifecycle_status,
        account_id=result.account_id,
        account_name=result.account_name,
        account_display_name=result.account_display_name,
        client_company_name=result.client_company_name,
        signer_name=result.signer_name,
        signer_email=result.signer_email,
        docusign_required=result.docusign_required,
        docusign_embed_url=result.docusign_embed_url,
        docusign_contract_url=result.docusign_contract_url,
        docusign_contract_id=result.docusign_contract_id,
        docusign_envelope_id=result.docusign_envelope_id,
        docusign_sender_name=result.docusign_sender_name,
        fallback_message=result.fallback_message,
        password_setup_available=result.password_setup_available,
    )


def _to_docusign_completion_response(
    result: ReconcileClientOnboardingDocusignCompletionResult,
) -> ReconcileClientOnboardingDocusignCompletionResponse:
    return ReconcileClientOnboardingDocusignCompletionResponse(
        lifecycle_id=result.lifecycle_id,
        lifecycle_status=result.lifecycle_status,
        docusign_signed_at=result.docusign_signed_at,
        password_setup_available=result.password_setup_available,
        transition_recorded=result.transition_recorded,
    )
