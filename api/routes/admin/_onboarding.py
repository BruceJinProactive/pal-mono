import asyncio
import uuid

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import AccountParams
from api.schemas.admin.onboarding import (
    BuildMenuRequest,
    BuildMenuResponse,
    GenerateAgentPromptsRequest,
    GenerateAgentPromptsResponse,
    MenuUploaderResponse,
    OnboardingRequest,
    OnboardingResponse,
    ScrapeBrandFromUrlRequest,
    ScrapeBrandFromUrlResponse,
    SelfOnboardingRequest,
    SelfOnboardingResponse,
)
from db.session import SyncSessionLocal
from db.tables.accounts import AccountStatus, OnboardingMethod
from services import account_service, admin_service, agent_service, project_service
from services.admin_service import ProjectSetup
from services.admin_service.schema import CognitoUser
from services.agent_service import AgentParams
from services.number_service import NumberService
from services.number_service._utils import NumberChannel
from services.project_service import ProjectParams
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate agent prompts: {str(err)}",
            headers={"Content-Type": "application/json"},
        )


async def build_menu_api(
    request: BuildMenuRequest,
    context: UserContext,
) -> BuildMenuResponse:
    """
    Build menu data from a restaurant URL using Firecrawl.

    This endpoint handles the building of restaurant menu data from URLs
    using the Firecrawl service with optional stealth proxy support.
    """
    authorize_admin(context)

    try:
        result = await admin_service.build_menu_from_url(
            url=request.url,
            use_stealth_proxy=request.use_stealth_proxy,
        )

        return BuildMenuResponse(menu=result)

    except ValueError as err:
        # Client errors: bad URL, no content, timeout, etc.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        # Server errors: API key missing, service unavailable, etc.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Menu building service is currently unavailable",
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        # Unexpected errors - log and return 500
        logger.exception(
            "Unexpected error in build menu API",
            extra={
                "url": str(request.url),
                "use_stealth_proxy": request.use_stealth_proxy,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
            headers={"Content-Type": "application/json"},
        )


async def process_menu_upload_background(
    upload_files,
    context: UserContext,
    project_id: uuid.UUID,
) -> None:
    """
    Background task to process menu upload and update project.
    Creates its own database session to avoid using the closed request-scoped session.
    """
    # Create a new session for this background task
    session = SyncSessionLocal()
    try:
        logger.info(
            f"[Background] Starting menu upload processing for project {project_id}"
        )

        # Process the menu files
        result = await admin_service.build_menu_from_upload(upload_files)

        # Update the project with the menu
        project_params = ProjectParams()
        project_params.product_info = result
        logger.info("Project result: %s", result)
        project_service.update_project(session, context, project_id, project_params)

        # Commit the transaction
        session.commit()

        logger.info(
            f"[Background] Successfully processed and updated menu for project {project_id}"
        )

    except ValueError as err:
        session.rollback()
        logger.error(
            f"[Background] Client error processing menu for project {project_id}: {err}"
        )
    except RuntimeError as err:
        session.rollback()
        logger.error(
            f"[Background] Service error processing menu for project {project_id}: {err}"
        )
    except Exception as err:
        session.rollback()
        logger.exception(
            f"[Background] Unexpected error processing menu for project {project_id}",
            extra={"error": str(err)},
        )
    finally:
        # Always close the session to avoid connection leaks
        session.close()


async def upload_menu_api(
    upload_files,
    context: UserContext,
    project_id: uuid.UUID,
) -> MenuUploaderResponse:
    """
    Start async menu upload processing and return immediately.

    Returns a response indicating that processing has started.
    The menu will be updated in the background.
    """
    try:
        # Validate files before starting background task
        files_list = upload_files if isinstance(upload_files, list) else [upload_files]

        # Basic validation - accept images and PDFs
        for file in files_list:
            if not file.content_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File type could not be determined",
                    headers={"Content-Type": "application/json"},
                )

            is_image = file.content_type.startswith("image/")
            is_pdf = file.content_type == "application/pdf"

            if not (is_image or is_pdf):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file type. Expected image or PDF, got: {file.content_type}",
                    headers={"Content-Type": "application/json"},
                )

        logger.info(
            f"Starting background menu upload for project {project_id} with {len(files_list)} file(s)"
        )

        # Start background task
        asyncio.create_task(
            process_menu_upload_background(upload_files, context, project_id)
        )

        return MenuUploaderResponse(
            status="accepted",
            message="The menu starts to update. Processing in background and will be available shortly.",
            project_id=str(project_id),
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception:
        logger.exception(
            "Error starting menu upload background task",
            extra={"project_id": str(project_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start menu processing",
            headers={"Content-Type": "application/json"},
        )


async def scrape_brand_from_url(
    request: ScrapeBrandFromUrlRequest,
) -> ScrapeBrandFromUrlResponse:
    try:
        res = await admin_service.scrape_brand_from_url(request.url)
        return ScrapeBrandFromUrlResponse(brand_info=res)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
            headers={"Content-Type": "application/json"},
        )


async def self_onboarding(
    request: SelfOnboardingRequest, response: Response, session: Session
) -> SelfOnboardingResponse:
    """
    Self onboard a new user and create an account, agent, and project.
    This function first creates an account with the given account_name, then creates a Cognito user. If Cognito user creation
    fails, the account is hard deleted to maintain consistency.
    This function then creates an agent with the given agent_name, then creates a project with the given project_name.
    This function then assigns a phone number to the project.
    This function then returns the success status and account response.

    Args:
        request: A SignUpRequest object containing different fields for account, agent, and project.
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

    # Create Cognito user

    # Create account, agent, and project
    account_name = self_onboard_account(request, guest_context, session)
    if not account_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create account",
            headers={"Content-Type": "application/json"},
        )

    agent_id = self_onboard_agent(request, guest_context, session, account_name)
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create agent",
            headers={"Content-Type": "application/json"},
        )

    self_onboard_project(request, guest_context, session, account_name, agent_id)
    # Create Cognito user. If this fails, the account and agent will be hard deleted.

    user = self_onboard_user(request, session)
    if not user or not user.session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create user",
            headers={"Content-Type": "application/json"},
        )

    logger.info(f"[SelfOnboarding] Completed self onboarding for user {request.email}")

    session.commit()
    _set_user_session(response, user.email, user.session)
    account_response = get_account_status(account_name, guest_context, session)
    return SelfOnboardingResponse(
        success=True,
        account_response=account_response,
    )
    # Function completes successfully - no return value needed


def self_onboard_account(
    request: SelfOnboardingRequest, context: UserContext, session: Session
) -> str | None:
    """
    Self onboard an account. This function creates an account with the given account_name and other parameters.

    Args:
        request: A SelfOnboardingRequest object containing the account name, display name, phone number, and onboarding method.
        context: A UserContext object containing the user context.
        session: A Session object containing the database session.

    Returns:
        A SelfOnboardingResponse object containing the account name.
    """
    # Account Parameters assigned
    account_name = request.account_name
    account_params = AccountParams()
    account_params.status = AccountStatus.initializing
    account_params.onboarding_method = OnboardingMethod.self_onboarding
    account_params.display_name = request.account_display_name
    account_params.phone_number = request.phone_number
    account_params.business_description = request.account_description
    try:
        new_account = account_service.create_account(
            session=session,
            context=context,
            account_name=account_name,
            params=account_params,
            lead_id=None,
            auto_commit=False,  # Don't commit yet, in case Cognito creation fails
        )
        logger.info(f"[SelfOnboarding] Created account {account_name} for user signup")
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create account {account_name}: {e}",
            headers={"Content-Type": "application/json"},
        )
    return new_account.name if new_account else None


def self_onboard_agent(
    request: SelfOnboardingRequest,
    context: UserContext,
    session: Session,
    account_name: str,
) -> uuid.UUID | None:
    """
    Self onboard an agent. This function creates an agent with the given agent_name

    Args:
        request: A SelfOnboardingRequest object containing the agent name, communication style, interaction guidelines, voice id, and background noise.
        context: A UserContext object containing the user context.
        session: A Session object containing the database session.
        account_name: A string containing the account name.

    Returns:
        The agent id.
    """
    agent_params = AgentParams()
    agent_params.name = request.agent_name
    agent_params.greeting_message = request.agent_greeting_message
    agent_params.communication_style = request.agent_communication_style
    agent_params.interaction_guidelines = request.agent_interaction_guidelines
    agent_params.raw_config = {
        "vapi_voice_config_enabled": True,
        "dynamic_prompt_enabled": True,
    }
    agent_params.voice_id = request.agent_voice_id
    agent_params.background_noise = True
    try:
        new_agent = agent_service.create_agent(
            session=session,
            context=context,
            account_name=account_name,
            params=agent_params,
            auto_commit=False,
        )
        logger.info(f"[SelfOnboarding] Created agent {new_agent.name} for user signup")
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create agent {request.agent_name}: {e}",
            headers={"Content-Type": "application/json"},
        )
    return new_agent.id if new_agent else None


def self_onboard_project(
    request: SelfOnboardingRequest,
    context: UserContext,
    session: Session,
    account_name: str,
    agent_id: uuid.UUID,
) -> uuid.UUID | None:
    """
    Self onboard a project. This function creates a project with the given project_name

    Args:
        request: A SelfOnboardingRequest object containing the project name, display name, store hours, address, and timezone.
        context: A UserContext object containing the user context.
        session: A Session object containing the database session.
        account_name: A string containing the account name.
        agent_id: A uuid.UUID object containing the agent id.

    Returns:
        The project id.
    """
    # Project Parameters assigned
    project_params = ProjectParams()
    project_params.name = request.project_name
    project_params.display_name = request.project_display_name
    project_params.agent_id = agent_id
    # project_params.timezone = request.project_timezone
    project_params.store_hours = request.project_store_hours
    project_params.address = request.project_address
    project_params.timezone = request.project_timezone
    try:
        new_project = project_service.create_project(
            session=session,
            context=context,
            project_name=request.project_name,
            account_name=account_name,
            params=project_params,
            auto_commit=False,
        )
        logger.info(
            f"[SelfOnboarding] Created project {new_project.name} for user signup"
        )
        self_onboard_phone_number(new_project.name, new_project.id, context, session)

        return new_project.id if new_project else None
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create project {request.project_name}: {e}",
            headers={"Content-Type": "application/json"},
        )


def self_onboard_phone_number(
    project_name: str,
    project_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> str | None:
    """
    Self onboard a phone number. This function purchases a phone number for the given project

    Args:
        project_name: A string containing the project name.
        project_id: A uuid.UUID object containing the project id.
        context: A UserContext object containing the user context.
        session: A Session object containing the database session.

    Returns:
        The phone number.
    """
    try:
        channels = [NumberChannel.VOICE]

        phone_number = NumberService().assign_phone_number_to_project(
            project_id=project_id,
            project_name=project_name,
            channels=channels,
            session=session,
            context=context,
            auto_commit=False,
        )
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign phone number to project {project_name}: {e}",
            headers={"Content-Type": "application/json"},
        )
    logger.info(
        f"[SelfOnboarding] Assigned phone number {phone_number} to project {project_name}"
    )
    return phone_number


def self_onboard_user(request: SelfOnboardingRequest, session: Session) -> CognitoUser:
    """
    Self onboard a user by creating a Cognito user account.

    Args:
        request: SelfOnboardingRequest containing user details
        session: Database session for rollback if needed

    Returns:
        CognitoUser: The created user with session details

    Raises:
        HTTPException: If user creation fails
    """
    try:
        user = admin_service.signup_self_onboarding_user(
            account_name=request.account_name,
            user_email=request.email,
            user_name=request.user_name,
            password=request.password,
        )
        logger.info(f"[SelfOnboarding] Created Cognito user for {request.email}")
    except ValueError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    if not user or not user.session:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fully create user session",
            headers={"Content-Type": "application/json"},
        )

    return user
