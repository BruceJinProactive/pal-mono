from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.onboarding import (
    GenerateAgentPromptsRequest,
    GenerateAgentPromptsResponse,
    OnboardingRequest,
)
from services import admin_service
from services.admin_service import ProjectSetup
from services.admin_service.schema import CognitoUser

from ._auth import authorize_admin
from ._utils import UserContext


async def create_onboarding(
    request: OnboardingRequest,
    context: UserContext,
    session: Session,
) -> str:
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
                    enable_voice=proj.enable_voice,
                    enable_sms=proj.enable_sms,
                )
            )
        agent_projects_data.append((agent_data, projects_data))

    cognito_users = [
        CognitoUser(email=user.email, name=user.name) for user in request.users
    ]
    try:
        return admin_service.onboard_new_account(
            session,
            context,
            request.account.name,
            account_params,
            request.account.lead_id,
            agent_projects_data,
            users=cognito_users,
        )
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
