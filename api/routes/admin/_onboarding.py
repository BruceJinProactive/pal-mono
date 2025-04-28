from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.onboarding import OnboardingRequest, OnboardingResponse
from db.tables.accounts import BusinessIndustry
from services import admin_service
from services.account_service import AccountParams
from services.agent_service import AgentParams
from services.project_service import ProjectParams

from ._auth import authorize_user_account
from ._builder import build_account, build_agent, build_project
from ._utils import UserContext


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
    authorize_user_account(context, request.account.name)

    industry = None
    if request.account.industry:
        try:
            industry = BusinessIndustry(request.account.industry)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid account industry: {request.account.industry}",
                headers={"Content-Type": "application/json"},
            )
    account_params = AccountParams(
        display_name=request.account.display_name,
        icon_uri=request.account.icon_uri,
        industry=industry,
        business_description=request.account.business_description,
        business_faq=request.account.business_faq,
        business_promotions=request.account.business_promotions,
        business_catalog=request.account.business_catalog,
        business_others=request.account.business_others,
    )

    agent_projects_data = []
    for ap in request.agent_projects:
        agent_data = AgentParams(
            name=ap.agent.name,
            description=ap.agent.description,
            communication_style=ap.agent.communication_style,
            interaction_guidelines=ap.agent.interaction_guidelines,
            raw_config=None,
        )

        projects_data = []
        for p in ap.projects:
            project_data = ProjectParams(
                name=p.name,
                display_name=p.display_name,
                channel_identifiers=p.channel_identifiers,
            )
            projects_data.append(project_data)

        agent_projects_data.append((agent_data, projects_data))

    try:
        result = admin_service.onboard_new_account(
            session, request.account.name, account_params, agent_projects_data
        )
        return OnboardingResponse(
            account=build_account(result["account"]),
            agents=[build_agent(agent) for agent in result["agents"]],
            projects=[build_project(project) for project in result["projects"]],
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
