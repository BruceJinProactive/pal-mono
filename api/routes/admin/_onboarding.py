from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import AccountParams, AccountStatus
from api.schemas.admin.onboarding import (
    GenerateAgentPromptsRequest,
    GenerateAgentPromptsResponse,
    OnboardingRequest,
    OnboardingResponse,
    SelfOnboardingRequest,
    SelfOnboardingResponse,
)
from services import account_service, admin_service
from services.admin_service import ProjectSetup
from services.admin_service.schema import CognitoUser
from utils.log import logger

from ._account import _set_user_session, get_account_status
from ._auth import authorize_admin
from ._builder import build_onboarding_project_info
from ._utils import UserContext, create_guest_context


async def create_onboarding(
    request: OnboardingRequest,
    context: UserContext,
    session: Session,
) -> OnboardingResponse:
    """
    Create a new account, agents, and projects in a single transaction.

    This endpoint handles the onboarding process by creating all necessary entities
    in a single transaction. If any part of the process fails, the entire transaction
    is rolled back.
    """
    authorize_admin(context)

    account_params = request.account.to_account_params()

    agent_projects_data = []
    for ap in request.agent_projects:
        agent_data = ap.agent.to_agent_params()

        projects_data = []
        for proj in ap.projects:
            params = proj.to_project_params()
            projects_data.append(
                ProjectSetup(
                    params=params,
                    enable_web_widget=proj.enable_web_widget,
                )
            )
        agent_projects_data.append((agent_data, projects_data))

    cognito_users = [
        CognitoUser(email=user.email, name=user.name) for user in request.users
    ]
    try:
        project_data = admin_service.onboard_new_account(
            session,
            context,
            request.account.name,
            account_params,
            request.account.lead_id,
            agent_projects_data,
            users=cognito_users,
        )

        # Convert project data to response objects using reusable builder
        projects = [
            build_onboarding_project_info(project_info) for project_info in project_data
        ]

        return OnboardingResponse(account_name=request.account.name, projects=projects)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )


async def generate_agent_prompts_api(
    request: GenerateAgentPromptsRequest,
    context: UserContext,
) -> GenerateAgentPromptsResponse:
    """
    Generate agent prompts using the AI prompt generation service.

    This endpoint handles the generation of customized agent prompts based on
    restaurant information, agent configuration, and additional context.
    """
    authorize_admin(context)

    try:
        prompt_sections = await admin_service.generate_agent_prompts(
            restaurant_name=request.restaurant_name,
            agent_name=request.agent_name,
            agent_type=request.agent_type,
            keywords=request.keywords,
            specific_instructions=request.specific_instructions or "",
            menu_content=request.menu_content or "",
            additional_urls=request.additional_urls or [],
        )

        return GenerateAgentPromptsResponse(
            persona=prompt_sections["persona"],
            interaction_guidelines=prompt_sections["interaction_guidelines"],
        )

    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate agent prompts: {str(err)}",
            headers={"Content-Type": "application/json"},
        )


async def self_onboarding(
    request: SelfOnboardingRequest, response: Response, session: Session
) -> SelfOnboardingResponse:
    """
    Sign up a new user and create an account. This function first creates an account
    with the given account_name, then creates a Cognito user. If Cognito user creation
    fails, the account is hard deleted to maintain consistency.

    Args:
        request: A SignUpRequest object containing the user's email, password, and account name.
        response: FastAPI response object for setting cookies.
        session: Database session for account operations.

    Returns:
        SelfOnboardingResponse object containing the success status and account response.
    Raises:
        HTTPException: If there is an error signing up the user or creating the account.
    """
    # Create a guest context for account creation (no authenticated user yet)

    account_name = request.account_name
    guest_context = create_guest_context(account_name, request.email)
    params = AccountParams()
    params.status = AccountStatus.initializing
    params.display_name = request.account_display_name
    params.phone_number = request.phone_number
    try:
        account_service.create_account(
            session=session,
            context=guest_context,
            account_name=account_name,
            params=params,
            lead_id=None,
            auto_commit=False,  # Don't commit yet, in case Cognito creation fails
        )
        logger.info(f"Created account {account_name} for user signup")
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create account {account_name}: {e}",
            headers={"Content-Type": "application/json"},
        )

    try:
        user = admin_service.signup_account_user(
            account_name=request.account_name,
            user_email=request.email,
            user_name=request.name,
            password=request.password,
        )
    except ValueError as e:
        # undo the account creation
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    if not user.session:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fully create user session",
            headers={"Content-Type": "application/json"},
        )
    session.commit()
    _set_user_session(response, user.email, user.session)
    account_response = get_account_status(account_name, guest_context, session)
    return SelfOnboardingResponse(
        success=True,
        account_response=account_response,
    )
    # Function completes successfully - no return value needed
