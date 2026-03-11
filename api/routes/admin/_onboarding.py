import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from api.schemas.admin.account import AccountParams
from api.schemas.admin.onboarding import (
    BuildMenuRequest,
    BuildMenuResponse,
    GenerateAgentPromptsRequest,
    GenerateAgentPromptsResponse,
    MenuProcessingStatusResponse,
    MenuUploaderResponse,
    OnboardingRequest,
    OnboardingResponse,
    ScrapeBrandFromUrlRequest,
    ScrapeBrandFromUrlResponse,
    SelfOnboardingRequest,
    SelfOnboardingResponse,
    SigninGoogleUserRequest,
    SigninGoogleUserResponse,
)
from api.schemas.admin.voice_config import CreateVoiceConfigRequest
from db import TosAcceptanceRepository
from db.session import AsyncSessionLocal, SyncSessionLocal
from db.tables.accounts import AccountStatus, OnboardingMethod
from services import (
    account_service,
    admin_service,
    agent_service,
    project_service,
    slack_service,
)
from services.admin_service import ProjectSetup
from services.admin_service.schema import CognitoUser
from services.agent_service import AgentParams
from services.menu_service.menu_processing_service import (
    JobStatus,
    MenuProcessingService,
)
from services.number_service import NumberService
from services.number_service._utils import NumberChannel
from services.project_service import ProjectParams
from services.voice_service import VoiceService
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
    materialized_files: list[dict[str, Any]],
    context: UserContext,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    """
    Background task to process menu upload and update project.
    Creates its own database session to avoid using the closed request-scoped session.
    Tracks progress through MenuProcessingService.

    Args:
        materialized_files: List of dicts with keys: content_bytes, filename, content_type
        context: User context
        project_id: Project UUID
        job_id: Job UUID for tracking
    """
    from io import BytesIO

    from fastapi import UploadFile

    # Create a new session for this background task
    session = SyncSessionLocal()
    try:
        logger.info(
            f"[Background] Starting menu upload processing for project {project_id}, job {job_id}"
        )

        # Update job status to processing (10% progress)
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress_percent=10,
        )

        # Reconstruct UploadFile objects from materialized data
        upload_files = []
        for mat_file in materialized_files:
            file_obj = BytesIO(mat_file["content_bytes"])
            # Create UploadFile and manually set content_type via headers
            # Note: We're using type ignore because UploadFile accepts Headers but works with dict
            upload_file = UploadFile(
                filename=mat_file["filename"],
                file=file_obj,
                headers={"content-type": mat_file["content_type"]},  # type: ignore
            )
            upload_files.append(upload_file)

        # Update progress after file preparation (20%)
        MenuProcessingService.update_job(
            job_id=job_id,
            progress_percent=20,
        )

        # Handle single vs multiple files
        files_to_process = upload_files[0] if len(upload_files) == 1 else upload_files

        # Process the menu files (this is the heavy lifting - 20-70%)
        logger.info(
            f"[Background] Extracting menu from uploaded files for job {job_id}"
        )

        # Update progress before starting extraction (30%)
        MenuProcessingService.update_job(
            job_id=job_id,
            progress_percent=30,
        )

        # Start a heartbeat task to show progress during OpenAI processing
        heartbeat_active = True

        async def progress_heartbeat():
            """Slowly increment progress from 30% to 65% during OpenAI processing"""
            current_progress = 30
            while heartbeat_active and current_progress < 65:
                await asyncio.sleep(3)  # Update every 3 seconds
                if heartbeat_active:
                    current_progress += 5
                    MenuProcessingService.update_job(
                        job_id=job_id,
                        progress_percent=min(current_progress, 65),
                    )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(progress_heartbeat())

        try:
            result = await admin_service.build_menu_from_upload(files_to_process)
        finally:
            # Stop heartbeat
            heartbeat_active = False
            await heartbeat_task

        # Update progress after extraction (70%)
        MenuProcessingService.update_job(
            job_id=job_id,
            progress_percent=70,
        )

        # Update the project with the menu (70-100%)
        logger.info(
            f"[Background] Saving menu to project {project_id} for job {job_id}"
        )
        project_params = ProjectParams()
        project_params.product_info = result
        logger.debug("Project result: %s", result)
        project_service.update_project(session, context, project_id, project_params)

        # Update progress after project update (90%)
        MenuProcessingService.update_job(
            job_id=job_id,
            progress_percent=90,
        )

        # Commit the transaction
        session.commit()

        # Mark job as completed
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress_percent=100,
            completed=True,
            data={"menu": result},
        )

        logger.info(
            f"[Background] Successfully processed and updated menu for project {project_id}, job {job_id}"
        )

    except ValueError as err:
        session.rollback()
        error_message = f"Failed to extract menu: {str(err)}"
        logger.error(
            f"[Background] Client error processing menu for project {project_id}, job {job_id}: {err}"
        )
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            completed=True,
            error=error_message,
        )
    except RuntimeError as err:
        session.rollback()
        error_message = f"Menu processing service error: {str(err)}"
        logger.error(
            f"[Background] Service error processing menu for project {project_id}, job {job_id}: {err}"
        )
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            completed=True,
            error=error_message,
        )
    except Exception as err:
        session.rollback()
        error_message = "An unexpected error occurred during menu processing"
        logger.exception(
            f"[Background] Unexpected error processing menu for project {project_id}, job {job_id}",
            extra={"error": str(err)},
        )
        MenuProcessingService.update_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            completed=True,
            error=error_message,
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

    Returns a response indicating that processing has started, including a job_id
    for tracking progress via the status endpoint.
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

        # Materialize files before passing to background task
        # (UploadFile objects are request-scoped and close after response)
        materialized_files = []
        for file in files_list:
            content_bytes = await file.read()
            materialized_files.append(
                {
                    "content_bytes": content_bytes,
                    "filename": file.filename,
                    "content_type": file.content_type,
                }
            )

        # Create job to track processing
        job = MenuProcessingService.create_job(project_id=project_id)

        logger.info(
            f"Starting background menu upload for project {project_id} with {len(files_list)} file(s), job {job.job_id}"
        )

        # Start background task with materialized files
        asyncio.create_task(
            process_menu_upload_background(
                materialized_files, context, project_id, job.job_id
            )
        )

        return MenuUploaderResponse(
            status="accepted",
            message="The menu starts to update. Processing in background...",
            project_id=str(project_id),
            job_id=str(job.job_id),
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
    guest_context = create_guest_context(request.email)

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

    project_id = self_onboard_project(
        request, guest_context, session, account_name, agent_id
    )
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create project",
            headers={"Content-Type": "application/json"},
        )

    # Create voice config for the project
    await self_onboard_voice_config(project_id, request, guest_context, session)

    # Create Cognito user. If this fails, the account and agent will be hard deleted.
    user = self_onboard_user(request, session)

    if not user or not user.session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create user",
            headers={"Content-Type": "application/json"},
        )

    # Create TOS acceptance record if terms were accepted in onboarding
    if request.terms_accepted:
        try:
            # Get the newly created account to extract account_id
            account = account_service.get_account(session, account_name)
            if not account:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Account was created but cannot be retrieved",
                    headers={"Content-Type": "application/json"},
                )

            # Get user_id from Cognito session
            user_id = uuid.UUID(user.session.user_sub)

            # Create TOS acceptance in tos_acceptances table (idempotent)
            tos_repo = TosAcceptanceRepository(session)

            # Check if TOS acceptance already exists for this account/version
            existing_acceptance = tos_repo.get_tos_acceptance_by_version(
                account_id=account.id,
                tos_version=account_service.CURRENT_TOS_VERSION,
            )

            if existing_acceptance:
                logger.debug(
                    f"[SelfOnboarding] TOS acceptance already exists for account {account_name} version {account_service.CURRENT_TOS_VERSION}"
                )
            else:
                tos_repo.create_tos_acceptance(
                    account_id=account.id,
                    display_name=account.display_name or account.name,
                    tos_version=account_service.CURRENT_TOS_VERSION,
                    user_id=user_id,
                    user_email=request.email,
                    accepted_at=datetime.now(UTC),
                )
                logger.debug(
                    f"[SelfOnboarding] Created TOS acceptance record for account {account_name}"
                )
        except HTTPException:
            # Re-raise HTTPException as-is (already has proper status/detail)
            raise
        except Exception as e:
            session.rollback()
            logger.error(
                f"[SelfOnboarding] Failed to create TOS acceptance: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to record TOS acceptance: {str(e)}",
                headers={"Content-Type": "application/json"},
            ) from e

    logger.debug(f"[SelfOnboarding] Completed self onboarding for user {request.email}")

    session.commit()

    # Send notification to #test-channel Slack channel
    try:
        await slack_service.send_self_onboarding_notification(
            account_name=account_name,
            account_display_name=request.account_display_name,
            user_email=request.email,
            user_name=request.user_name,
            project_name=request.project_name,
            project_address=request.project_address,
            phone_number=request.phone_number,
        )
    except Exception as e:
        # Log error but don't fail the onboarding process
        logger.error(
            f"[SelfOnboarding] Failed to send Slack notification: {e}",
            extra={"account_name": account_name, "user_email": request.email},
        )

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
    # No longer write to terms_accepted field
    # account_params.terms_accepted = request.terms_accepted
    account_params.segment = request.segment
    # Default notification email to owner's email
    account_params.notification_email = request.email
    try:
        new_account = account_service.create_account(
            session=session,
            context=context,
            account_name=account_name,
            params=account_params,
            lead_id=None,
            auto_commit=False,  # Don't commit yet, in case Cognito creation fails
        )
        logger.debug(f"[SelfOnboarding] Created account {account_name} for user signup")
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
    agent_params.raw_config = {}
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
        logger.debug(f"[SelfOnboarding] Created agent {new_agent.name} for user signup")
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
        request: A SelfOnboardingRequest object containing the project name, display name, store hours, address, timezone, google_place_id, and product_info.
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
    project_params.store_hours = request.project_store_hours
    project_params.address = request.project_address
    project_params.timezone = request.project_timezone
    project_params.google_place_id = request.google_place_id
    project_params.product_info = request.product_info
    try:
        new_project = project_service.create_project(
            session=session,
            context=context,
            project_name=request.project_name,
            account_name=account_name,
            params=project_params,
            auto_commit=False,
        )
        logger.debug(
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
    logger.debug(
        f"[SelfOnboarding] Assigned phone number {phone_number} to project {project_name}"
    )
    return phone_number


def _get_language_config(language: str, custom_greeting: str | None = None) -> dict:
    """
    Get localized voice configuration for a given language.

    Args:
        language: The language code (English, Spanish, Chinese, Triage)
        custom_greeting: Optional custom greeting message to override default

    Returns:
        Dictionary with language, first_message, and transfer_message
    """
    language_defaults = {
        "English": {
            "first_message": "Let me know how I can help.",
            "transfer_message": "One second.",
        },
        "Spanish": {
            "first_message": "Hola, ¿cómo puedo ayudarle?",
            "transfer_message": "Un momento.",
        },
        "Chinese": {
            "first_message": "您好，我能帮您什么？",
            "transfer_message": "请稍等。",
        },
        "Triage": {
            "first_message": "Hi, this is an AI assistant. How can I help you?",
            "transfer_message": "One moment please.",
        },
    }

    # Get config for the language, fallback to English if not found
    config = language_defaults.get(language, language_defaults["English"])

    # Override first_message if custom greeting provided (used for Triage)
    if custom_greeting:
        config = {**config, "first_message": custom_greeting}

    return {
        "language": language,
        "first_message": config["first_message"],
        "transfer_message": config["transfer_message"],
    }


async def self_onboard_voice_config(
    project_id: uuid.UUID,
    request: SelfOnboardingRequest,
    context: UserContext,
    session: Session,
) -> None:
    """
    Self onboard a voice config. This function creates a voice config for the given project

    Args:
        project_id: UUID of the project
        request: SelfOnboardingRequest containing voice configuration
        context: UserContext for authorization
        session: Database session (not used, but kept for consistency)

    Returns:
        UUID of the created voice config, or None if creation fails
    """
    # Create async session for voice service
    async_session = AsyncSessionLocal()
    language = request.agent_language
    voice_service = VoiceService()

    try:
        if language != "Multilingual":
            # Get localized messages for the selected language
            lang_config = _get_language_config(language, request.agent_greeting_message)

            # Create voice config request with localized data
            voice_config_request = CreateVoiceConfigRequest(
                project_id=project_id,
                language=lang_config["language"],
                voice_id=request.agent_voice_id,
                first_message=lang_config["first_message"],
                transfer_message=lang_config["transfer_message"],
            )

            # Create voice config using voice service
            voice_config = await voice_service.create_voice_config(
                create_request=voice_config_request,
                async_session=async_session,
            )

            logger.debug(
                f"[SelfOnboarding] Created voice config {voice_config.id} for project {project_id}"
            )
            return
        else:
            # Create multilingual squad with all language configs
            language_configs = [
                _get_language_config("English"),
                _get_language_config("Spanish"),
                _get_language_config("Chinese"),
                _get_language_config("Triage", request.agent_greeting_message),
            ]

            for language_config in language_configs:
                voice_config_request = CreateVoiceConfigRequest(
                    project_id=project_id,
                    language=language_config["language"],
                    voice_id=request.agent_voice_id,
                    first_message=language_config["first_message"],
                    transfer_message=language_config["transfer_message"],
                )
                voice_config = await voice_service.create_voice_config(
                    create_request=voice_config_request,
                    async_session=async_session,
                )
                logger.debug(
                    f"[SelfOnboarding] Created voice config {voice_config.id} for project {project_id}"
                )
            return

    except Exception as e:
        await async_session.rollback()
        logger.error(
            f"[SelfOnboarding] Failed to create voice config for project {project_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create voice config: {e}",
            headers={"Content-Type": "application/json"},
        )
    finally:
        await async_session.close()


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
            session=session,
        )
        logger.debug(f"[SelfOnboarding] Created Cognito user for {request.email}")
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


def signin_google_user(request: SigninGoogleUserRequest) -> SigninGoogleUserResponse:
    """
    Sign in a user using Google OAuth and retrieve a Cognito user session.

    Args:
        request: SigninGoogleUserRequest containing Google credential
        session: Database session for rollback if needed
    """
    try:
        response = admin_service.signin_google_user(google_credential=request.token)

        logger.debug("Google signin response received")

        if response:
            return SigninGoogleUserResponse(
                is_signed_in=response["is_signed_in"],
                next_step=response["next_step"],
                tokens=response.get("tokens"),
                session=response.get("session"),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to sign in user",
                headers={"Content-Type": "application/json"},
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )


def _verify_project_access(
    context: UserContext,
    session: Session,
    project,
    project_id: uuid.UUID,
) -> None:
    """
    Verify user has access to a project.

    Args:
        context: User context
        session: Database session
        project: Project object
        project_id: Project UUID

    Raises:
        HTTPException: 403 if access denied
    """
    from db.repositories.resource_role_assignment_repository import (
        ResourceRoleAssignmentRepository,
        ResourceType,
    )

    # Admin users have access to all projects
    if context.role and context.role.value == "Admin":
        return

    try:
        user_id = uuid.UUID(context.username)
    except ValueError:
        # Invalid username format and not admin
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
            headers={"Content-Type": "application/json"},
        )

    role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)

    # Check account-level access
    account_roles = role_repo.get_roles_for_resource(
        user_id=user_id,
        resource_type=ResourceType.ACCOUNT,
        resource_id=project.account_id,
    )

    # Check project-level access
    project_roles = role_repo.get_roles_for_resource(
        user_id=user_id,
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )

    # Deny if no access
    if not (account_roles or project_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
            headers={"Content-Type": "application/json"},
        )


def is_google_user(request: str) -> bool:
    """
    Test if the user is a Google user.
    Args:
        request: Email address to check
    Returns:
        bool: True if the user is a Google user, False otherwise
    """
    return admin_service.is_google_user(request)


async def get_menu_processing_status(
    job_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> MenuProcessingStatusResponse:
    """
    Get the status of a menu processing job.

    Args:
        job_id: UUID of the job to check
        context: User context for authorization
        session: Database session for project access check

    Returns:
        Job status with progress information

    Raises:
        HTTPException: 404 if job not found or expired, 403 if unauthorized
    """
    job = MenuProcessingService.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
            headers={"Content-Type": "application/json"},
        )

    # Verify user has access to the project
    project = project_service.get_project(session, job.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )

    # Verify user has access to the project
    _verify_project_access(context, session, project, job.project_id)

    return MenuProcessingStatusResponse(**job.to_dict())
