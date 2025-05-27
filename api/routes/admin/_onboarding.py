from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from api.schemas.admin.onboarding import OnboardingRequest
from services import admin_service
from services.account_service import AccountParams
from services.admin_service.schema import CognitoUser
from services.agent_service import AgentParams
from services.project_service import ProjectParams

from ._auth import authorize_user_account
from ._utils import UserContext


async def create_onboarding(
    request: OnboardingRequest,
    context: UserContext,
    session: Session,
):
    """
    Create a new account, agents, and projects in a single transaction.

    This endpoint handles the onboarding process by creating all necessary entities
    in a single transaction. If any part of the process fails, the entire transaction
    is rolled back.
    """
    authorize_user_account(context, request.account.name)

    account_params = AccountParams(
        display_name=request.account.display_name,
        icon_uri=request.account.icon_uri,
        industry=request.account.industry,
        business_description=request.account.business_description,
        business_faq=request.account.business_faq,
        business_promotions=request.account.business_promotions,
        business_catalog=request.account.business_catalog,
        business_others=request.account.business_others,
        lead_id=request.account.lead_id,
        status=request.account.status,
    )

    agent_projects_data = []
    for ap in request.agent_projects:
        agent_data = AgentParams(
            name=ap.agent.name,
            description=ap.agent.description,
            communication_style=ap.agent.communication_style,
            interaction_guidelines=ap.agent.interaction_guidelines,
            raw_config=None,
            voice_id=ap.agent.voice_id,
            greeting_message=ap.agent.greeting_message,
            speech_rate=ap.agent.speech_rate,
        )

        projects_data = []
        for p in ap.projects:
            project_data = ProjectParams(
                name=p.name,
                display_name=p.display_name,
                channel_identifiers=p.channel_identifiers,
                store_hours=p.store_hours,
                address=p.address,
                product_info=p.product_info,
                service_instruction=p.service_instruction,
            )
            projects_data.append(project_data)

        agent_projects_data.append((agent_data, projects_data))

    cognito_users = [
        CognitoUser(email=user.email, name=user.name) for user in request.users
    ]
    try:
        admin_service.onboard_new_account(
            session,
            context,
            request.account.name,
            account_params,
            agent_projects_data,
            users=cognito_users,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
