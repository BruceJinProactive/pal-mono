import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import AgentConfig
from api.routes.admin._utils import SortOrder, UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.account import (
    Account,
    AccountStatisticsResponse,
    AccountStatusResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    UpdateAccountRequest,
)
from api.schemas.admin.agent import (
    Agent,
    AgentSummary,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from api.schemas.admin.analytics import GetAllReportsResponse
from api.schemas.admin.campaign import CreateCampaignResponse, ListCampaignsResponse
from api.schemas.admin.conversation import (
    DEFAULT_STATS_AGE,
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
    UpdateConversationRequest,
    UpdateSessionResponse,
)
from api.schemas.admin.email import (
    GetTemplateInfoRequest,
    ListTemplatesRequest,
    SendBatchEmailsRequest,
    SendEmailRequest,
)
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    Feedback,
    FeedbackDetail,
    ListFeedbacksResponse,
    UpdateFeedbackRequest,
)
from api.schemas.admin.history import ChangeLogDetails, ListChangeLogsResponse
from api.schemas.admin.integration import (
    CreateProjectIntegrationRequest,
    IntegrationRequest,
    IntegrationResponse,
    ListIntegrationsResponse,
    ListProjectIntegrationsResponse,
    ProjectIntegrationResponse,
    UpdateIntegrationRequest,
    UpdateProjectIntegrationRequest,
)
from api.schemas.admin.knowledge import ListKnowledgeFileResponse, ResourceType
from api.schemas.admin.lead import (
    CreateLeadRequest,
    Lead,
    ListLeadsResponse,
    UpdateLeadRequest,
)
from api.schemas.admin.onboarding import OnboardingRequest
from api.schemas.admin.phone_number import (
    ReleaseProjectNumberRequest,
    ReserveProjectNumberRequest,
)
from api.schemas.admin.project import (
    CreateProjectRequest,
    Project,
    ProjectSummary,
    UpdateProjectRequest,
)
from api.schemas.admin.prompt import (
    CreatePromptRequest,
    Prompt,
    PromptDetails,
    SystemPrompt,
    UpdatePromptRequest,
)
from api.schemas.admin.subscription import (
    CreateCheckoutSessionRequest,
    CreateProjectSubscriptionRequest,
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
    ListAccountSubscriptionsResponse,
    ListSubscriptionsResponse,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    UpdateAccountSubscriptionRequest,
    UpdateAccountSubscriptionStatusRequest,
    UpdateAccountSubscriptionStatusResponse,
    UpdateSubscriptionPlanRequest,
)
from api.schemas.admin.user import SignUpRequest
from api.schemas.admin.user_management import (
    CreateUserRequest,
    ListUsersResponse,
    UserInfo,
)
from db.tables.change_log import ChangeResourceType
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from db.tables.types import Channel
from services.campaign_service.schema import CampaignDetails, CreateCampaignRequest

from . import (
    _account,
    _agent,
    _analytics,
    _auth,
    _campaign,
    _conversation,
    _email,
    _feedback,
    _history,
    _integration,
    _knowledge,
    _lead,
    _phone_number,
    _projects,
    _prompt,
    _subscription,
    _users,
)
from ._auth import authenticate_user
from ._onboarding import create_onboarding

"""
######################################################
# Guide for the Admin APIs
######################################################

The API routes for the Admin Console are grouped by resource types for easier
maintenance and quick search.

The implementation is divided into separate modules based on the functionality.

Submodules are to organized in function name alphabetical order unless
otherwise specified.

You do not need to waste time writing docstring for the args in these endpoints
if they are self explanatory.
"""

admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])


@admin_router.get("/me")
def get_user(context: UserContext = Depends(authenticate_user)):
    """
    Retrieve information about the currently logged-in user.
    """
    return _auth.get_user_info(context)


@admin_router.post("/signup", status_code=status.HTTP_200_OK)
async def signup(
    request: SignUpRequest,
    response: Response,
    session: Session = Depends(db.get_db),
) -> AccountStatusResponse:
    """
    Sign up a new user and create an account. Creates the account first, then the Cognito user.
    If Cognito user creation fails, the account will be deleted.
    """
    return await _account.user_signup(request, response, session)


"""
---------- Accounts Endpoints ----------
----------------------------------------
"""


@admin_router.get("/accounts")
def list_accounts(
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
    keyword: str = Query(
        None, description="Optional keyword to filter the accounts by name"
    ),
) -> ListAccountsResponse:
    """
    Retrieve a list of accounts that are associated with the current user.
    """
    return _account.list_accounts(context, session, keyword)


@admin_router.put("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    account: CreateAccountRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """
    Create a new account based on the provided request data.
    """
    return await _account.create_account(account, context, session)


@admin_router.get("/accounts/{account_name}")
def get_account(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """
    Retrieve account details by account name.
    """
    return _account.get_account(account_name, context, session)


@admin_router.patch("/accounts/{account_name}")
async def update_account(
    account_name: str,
    account: UpdateAccountRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """
    Update the account based on the provided request data.
    """
    return await _account.update_account(account_name, account, context, session)


@admin_router.delete("/accounts/{account_name}")
async def delete_account(
    account_name: str,
    hard_delete: bool = Query(
        False, description="Whether to hard delete the account from the database"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete the account identified by name.
    """
    await _account.delete_account(account_name, hard_delete, context, session)


@admin_router.post("/accounts/{account_name}/close")
async def close_account(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Close the account by canceling the Stripe subscription and updating status to disabled.
    """
    return await _account.close_account(account_name, context, session)


@admin_router.get("/accounts/{account_name}/agents")
async def list_account_agents(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> list[AgentSummary]:
    """
    Retrieve a list of agents associated with the given account name.
    """
    return await _account.list_account_agents(account_name, context, session)


@admin_router.get("/accounts/{account_name}/projects")
async def list_account_projects(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> list[Project]:
    """
    Retrieve a list of projects associated with the given account name.
    """
    return await _projects.list_account_projects(account_name, context, session)


@admin_router.get("/accounts/{account_name}/reports", status_code=status.HTTP_200_OK)
async def get_account_reports(
    account_name: str,
    start_date: datetime | None = Query(
        default=None,
        description="Start date for the report data. If not provided, defaults to 7 days ago.",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End date for the report data. If not provided, defaults to today.",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> GetAllReportsResponse:
    """
    Retrieve unified analytics reports for this account.
    Data is filtered by the specified date range (default: today + 7 days).
    """

    # Set default dates if not provided (today + 7 days)

    if end_date is None:
        # Set end_date to today at 23:59:59
        now = datetime.now(UTC)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if start_date is None:
        # Subtract 6 full days to get exactly 7 calendar days
        start_date = end_date - timedelta(days=6)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get unified reports using async session
    return await _analytics.get_reports(
        account_name, context, session, start_date, end_date
    )


@admin_router.get("/accounts/{account_name}/stat")
async def get_account_statistics(
    account_name: str,
    start_date: datetime | None = Query(
        default=None,
        description="Start date for statistics (inclusive). If not provided, defaults to 7 days ago.",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End date for statistics (inclusive). If not provided, defaults to now.",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AccountStatisticsResponse:
    """
    Return basic account statistics such as total unique users and active sessions.
    Statistics are calculated based on the specified date range. If no dates are provided,
    defaults to the last 7 days.
    """
    end_date = end_date or datetime.now(UTC)
    start_date = start_date or (end_date - timedelta(seconds=DEFAULT_STATS_AGE))

    return await _account.get_account_statistics(
        account_name, start_date, end_date, context, session
    )


@admin_router.get("/accounts/{account_name}/status")
def get_account_status(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AccountStatusResponse:
    """
    Retrieve account status by account name.
    """
    return _account.get_account_status(account_name, context, session)


"""
---------- Integrations Endpoints ----------
--------------------------------------------
"""


@admin_router.get("/accounts/{account_name}/integrations")
def list_integrations(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListIntegrationsResponse:
    """
    Retrieve a list of integrations for the specified account.
    """
    return _integration.list_integrations(account_name, context, session)


@admin_router.get("/accounts/{account_name}/integrations/{integration_id}")
def get_integration(
    account_name: str,
    integration_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> IntegrationResponse:
    """
    Retrieve integration details by integration ID.
    """
    return _integration.get_integration(account_name, integration_id, context, session)


@admin_router.put(
    "/accounts/{account_name}/integrations", status_code=status.HTTP_201_CREATED
)
async def create_integration(
    account_name: str,
    integration: IntegrationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> IntegrationResponse:
    """
    Create a new integration for the specified account.
    """
    return await _integration.create_integration(
        account_name, integration, context, session
    )


@admin_router.patch("/accounts/{account_name}/integrations/{integration_id}")
async def update_integration(
    account_name: str,
    integration_id: uuid.UUID,
    integration: UpdateIntegrationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> IntegrationResponse:
    """
    Update an existing integration.
    """
    return await _integration.update_integration(
        account_name, integration_id, integration, context, session
    )


@admin_router.delete("/accounts/{account_name}/integrations/{integration_id}")
async def delete_integration(
    account_name: str,
    integration_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete an integration.
    """
    return await _integration.delete_integration(
        account_name, integration_id, context, session
    )


@admin_router.get("/projects/{project_id}/integrations")
def list_project_integrations(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListProjectIntegrationsResponse:
    """
    Retrieve a list of integrations for the specified project.
    """
    return _integration.list_project_integrations(project_id, context, session)


@admin_router.get("/projects/{project_id}/integrations/{project_integration_id}")
def get_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ProjectIntegrationResponse:
    """
    Retrieve project integration details by project integration ID.
    """
    return _integration.get_project_integration(
        project_id, project_integration_id, context, session
    )


@admin_router.put(
    "/projects/{project_id}/integrations", status_code=status.HTTP_201_CREATED
)
async def create_project_integration(
    project_id: uuid.UUID,
    project_integration: CreateProjectIntegrationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ProjectIntegrationResponse:
    """
    Create a new project integration.
    """
    return await _integration.create_project_integration(
        project_id, project_integration, context, session
    )


@admin_router.patch("/projects/{project_id}/integrations/{project_integration_id}")
async def update_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    project_integration: UpdateProjectIntegrationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ProjectIntegrationResponse:
    """
    Update an existing project integration.
    """
    return await _integration.update_project_integration(
        project_id, project_integration_id, project_integration, context, session
    )


@admin_router.delete("/projects/{project_id}/integrations/{project_integration_id}")
async def delete_project_integration(
    project_id: uuid.UUID,
    project_integration_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete a project integration.
    """
    return await _integration.delete_project_integration(
        project_id, project_integration_id, context, session
    )


"""
---------- Agents Endpoints ----------
--------------------------------------
"""


@admin_router.put("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent: CreateAgentRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Create a new agent based on the provided request data. An agent must
    have a name and a valid account associated with it.
    """
    return await _agent.create_agent(agent, context, session)


@admin_router.get("/agents/{agent_id}")
def get_agent(
    agent_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Retrieve the agent configuration for the agent_id.
    """
    return _agent.get_agent(agent_id, context, session)


@admin_router.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    agent: UpdateAgentRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Update the agent config for the given agent_id. Note that the account
    associated with the agent cannot be modified once created.
    """
    return await _agent.update_agent(agent_id, agent, context, session)


@admin_router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete the specified agent by id.
    """
    await _agent.delete_agent(agent_id, context, session)


@admin_router.get("/agents/{agent_id}/projects")
async def list_agent_projects(
    agent_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> list[ProjectSummary]:
    """
    Retrieve a list of projects associated with the given agent ID.
    """
    return await _agent.list_agent_projects(agent_id, context, session)


@admin_router.get("/agents/{agent_id}/agent_config")
async def get_agent_config(
    agent_id: uuid.UUID,
    project_id: uuid.UUID = Query(
        ..., description="Project ID to build the agent config for"
    ),
    channel: Channel = Query(
        Channel.VOICE, description="The channel to build the agent config for"
    ),
    context: UserContext = Depends(authenticate_user),
    sync_session: Session = Depends(db.get_db),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> AgentConfig:
    """
    Retrieve the agent configuration as generated by the construct_agent_config function.
    This endpoint returns the complete AgentConfig object that would be used to initialize the agent.

    Args:
        agent_id (uuid.UUID): The ID of the agent.
        project_id (uuid.UUID): The ID of the project to build the agent config for.
        channel (Channel): The channel to build config for

    Returns:
        AgentConfig: The complete agent configuration.
    """
    return await _agent.get_agent_config(
        agent_id, project_id, channel, context, sync_session, async_session
    )


"""
---------- Campaign Endpoints ----------
----------------------------------------
"""


@admin_router.put("/accounts/{account_name}/campaigns")
async def create_campaign(
    account_name: str,
    campaign_request: CreateCampaignRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> CreateCampaignResponse:
    """
    Creates a new marketing campaign where it can be used to send promotional
    contents to a select list of users.
    """
    return await _campaign.create_campaign(
        account_name, campaign_request, context, session
    )


@admin_router.get("/campaigns/{campaign_id}")
async def get_campaign_detail(
    campaign_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> CampaignDetails:
    """
    Uses the campaign id to retrieve the campaign metadata and execution results.
    """
    return await _campaign.get_campaign_detail(campaign_id, context, session)


@admin_router.get("/accounts/{account_name}/campaigns")
async def list_account_campaigns(
    account_name: str,
    status: str | None = Query(
        None, description="Optional status to filter campaigns by"
    ),
    page: int = Query(1, gt=0, description="Page number"),
    page_size: int = Query(20, gt=0, le=100, description="Number of items per page"),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListCampaignsResponse:
    """
    Retrieves a list of campaign summaries for the given account.
    Optionally filter by campaign status.
    """
    return await _campaign.list_account_campaigns(
        account_name, status, context, session, page, page_size
    )


"""
---------- Conversation Endpoints ----------
--------------------------------------------
"""
DEFAULT_SESSION_AGE = 3600 * 24 * 365  # 365 days of history


@admin_router.get("/accounts/{account_name}/sessions", include_in_schema=False)
@admin_router.get("/accounts/{account_name}/conversations")
async def list_account_conversations(
    account_name: str,
    keyword: str = Query("", description="Optional keyword to filter the results by"),
    channel: Channel | None = Query(
        None, description="Optional channel to filter the results by"
    ),
    lookback: int = Query(
        DEFAULT_SESSION_AGE,
        description="Only retrieve sessions created within the specified lookback period in seconds.",
        gt=0,
    ),
    page: int = Query(..., description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        ..., description="Size of each page, cannot be less than 1", gt=0
    ),
    escalated: bool = Query(
        False, description="Returns only the escalated sessions if set to true"
    ),
    hide_testing_sessions: bool = Query(
        True, description="Set to false to include test sessions in the result"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListUserSessionsResponse:
    """
    Retrieve the list of convo sessions for a given account. Returned conversations
    are sorted by the timestamp of the last message in reverse chronological order.
    """
    return await _conversation.list_account_user_sessions(
        account_name,
        keyword,
        channel,
        lookback,
        page,
        page_size,
        escalated,
        hide_testing_sessions,
        context,
        session,
    )


@admin_router.get("/sessions/{session_id}/messages", include_in_schema=False)
async def list_session_messages(
    session_id: uuid.UUID,
    page: int = Query(..., description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        ..., description="Size of each page, cannot be less than 1", gt=0
    ),
    sort_order: SortOrder = Query(
        SortOrder.desc,
        description="The order in which messages are sorted by on the timestamp field",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListConversationMessagesResponse:
    """
    Returns the detailed convo session messages for the given id. Messages are sorted
    in chronological order.
    """
    return await _conversation.list_conversation_messages(
        None, session_id, page, page_size, sort_order, context, session
    )


@admin_router.get("/accounts/{account_name}/conversations/{conversation_id}/messages")
async def list_conversation_messages(
    account_name: str,
    conversation_id: uuid.UUID,
    page: int = Query(..., description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        ..., description="Size of each page, cannot be less than 1", gt=0
    ),
    sort_order: SortOrder = Query(
        SortOrder.desc,
        description="The order in which messages are sorted by on the timestamp field",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListConversationMessagesResponse:
    """
    Returns the detailed convo session messages for the given id. Messages are sorted
    in chronological order.
    """
    return await _conversation.list_conversation_messages(
        account_name, conversation_id, page, page_size, sort_order, context, session
    )


@admin_router.patch("/sessions/{session_id}", include_in_schema=False)
async def update_session(
    session_id: uuid.UUID,
    session_request: UpdateConversationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UpdateSessionResponse:
    """
    Update the session with the given id.
    """
    return await _conversation.update_session(
        session_id, session_request, context, session
    )


@admin_router.patch("/accounts/{account_name}/conversations/{conversation_id}")
async def update_conversation(
    account_name: str,
    conversation_id: uuid.UUID,
    update_request: UpdateConversationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UpdateSessionResponse:
    """
    Update the session with the given id.
    """
    return await _conversation.update_conversation(
        context,
        session,
        account_name,
        conversation_id,
        update_request,
    )


"""
---------- Feedback Endpoints ----------
----------------------------------------
"""


@admin_router.get("/accounts/{account_name}/feedbacks")
async def list_account_feedbacks(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListFeedbacksResponse:
    """
    Retrieve the list of feedbacks for a given account. Returned feedbacks are
    sorted by the timestamp of the associated message in reverse chronological
    order.
    """
    return await _feedback.list_account_feedbacks(account_name, context, session)


@admin_router.put("/feedbacks", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback: CreateFeedbackRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Feedback:
    """
    Create a feedback for a message.
    """
    return await _feedback.create_feedback(feedback, context, session)


@admin_router.get("/feedbacks/{feedback_id}")
async def get_feedback(
    feedback_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> FeedbackDetail:
    """
    Get feedback by feedback id.
    """
    return await _feedback.retrieve_feedback_by_id(feedback_id, context, session)


@admin_router.patch("/feedbacks/{feedback_id}")
async def update_feedback(
    feedback_id: uuid.UUID,
    feedback: UpdateFeedbackRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Feedback:
    """
    Update the referenced feedback, only fields populated in the request
    will be updated.
    """
    return await _feedback.update_feedback(feedback_id, feedback, context, session)


@admin_router.delete("/feedbacks/{feedback_id}")
async def delete_feedback(
    feedback_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete the referenced feedback, return 200 OK if the feedback is successfully
    deleted or if it doesn't exist. No response content is returned.
    """
    await _feedback.delete_feedback(feedback_id, context, session)


"""
---------- Projects Endpoints ----------
----------------------------------------
"""


@admin_router.put("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    project: CreateProjectRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Create a new project based on the provided request data. A project must
    have a name and a valid account associated with it.
    """
    return await _projects.create_project(project, context, session)


@admin_router.get("/projects/{project_id}")
def get_project(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Fetch detailed information about a specific project by its uuid.
    """
    return _projects.get_project(project_id, context, session)


@admin_router.patch("/projects/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    project: UpdateProjectRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Update a project based on the provided request data. Project's account can
    not be updated once created.
    """
    return await _projects.update_project(project_id, project, context, session)


@admin_router.delete("/projects/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete the specified project by id.
    """
    await _projects.delete_project(project_id, context, session)


@admin_router.post(
    "/projects/{project_id}/reserve_number", status_code=status.HTTP_200_OK
)
async def reserve_number_for_project(
    project_id: uuid.UUID,
    request: ReserveProjectNumberRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Create a new phone number, optionally bind to assistant and project.
    """
    await _phone_number.reserve_phone_number(project_id, request, context, session)


@admin_router.post(
    "/projects/{project_id}/release_number", status_code=status.HTTP_200_OK
)
async def release_phone_number(
    project_id: uuid.UUID,
    request: ReleaseProjectNumberRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Release the specified phone number.
    """
    await _phone_number.release_phone_number(project_id, request, context, session)


"""
---------- Email Endpoints ----------
-------------------------------------
"""


@admin_router.post("/email/send", status_code=status.HTTP_200_OK)
async def send_email(
    request: SendEmailRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Send a single email using a Postmark template.
    """
    return await _email.send_email(request, context, session)


@admin_router.post("/email/send_batch", status_code=status.HTTP_200_OK)
async def send_batch_emails(
    request: SendBatchEmailsRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Send multiple emails using Postmark templates in a single API call.
    """
    return await _email.send_batch_emails(request, context, session)


@admin_router.post("/email/template/info", status_code=status.HTTP_200_OK)
async def get_template_info(
    request: GetTemplateInfoRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Get information about a Postmark template.
    """
    return await _email.get_template_info(request, context, session)


@admin_router.post("/email/templates/list", status_code=status.HTTP_200_OK)
async def list_templates(
    request: ListTemplatesRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    List available Postmark templates.
    """
    return await _email.list_templates(request, context, session)


@admin_router.delete(
    "/instagram/deauthorize/{ig_user_id}", status_code=status.HTTP_200_OK
)
async def handle_instagram_deauthorization(
    ig_user_id: str,
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Handle Instagram deauthorization request.

    Returns:
        dict: A message indicating the Instagram account is deauthorized.
    """
    return await _projects.handle_instagram_deauthorization(
        ig_user_id, request, session
    )


@admin_router.post(
    "/projects/{project_id}/instagram/connect", status_code=status.HTTP_200_OK
)
async def connect_instagram(
    project_id: str,
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Connect an Instagram account to a project.

    Returns:
        dict: A message indicating the Instagram account is connected.
    """
    return await _projects.connect_instagram(project_id, request, session)


@admin_router.delete(
    "/projects/{project_id}/instagram/connect", status_code=status.HTTP_200_OK
)
async def disconnect_instagram(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Disconnect an Instagram account from a project.

    Returns:
        dict: A message indicating the Instagram account is disconnected.
    """
    return await _projects.disconnect_instagram(project_id, session)


@admin_router.get(
    "/projects/{project_id}/instagram/status", status_code=status.HTTP_200_OK
)
async def get_project_instagram_connected(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Check if an Instagram account is connected to a project.
    """
    return await _projects.get_project_instagram_connected(project_id, session)


@admin_router.get(
    "/projects/{project_id}/instagram/username", status_code=status.HTTP_200_OK
)
async def get_project_instagram_username(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Get the username of the Instagram account connected to a project.

    """
    return _projects.get_project_instagram_username(project_id, session)


"""
---------- User Management Endpoints ----------
----------------------------------------------
"""


@admin_router.get("/accounts/{account_name}/users")
async def list_account_users(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
) -> ListUsersResponse:
    """
    Retrieve a list of admin users for a specific account.
    Filters users by the custom:account_name attribute in Cognito.
    """
    return await _users.list_account_users(account_name, context)


@admin_router.put("/accounts/{account_name}/users")
async def create_account_user(
    account_name: str,
    user: CreateUserRequest,
    context: UserContext = Depends(authenticate_user),
) -> UserInfo:
    """
    Create a new admin user for a specific account.
    Uses AdminCreateUser flow to create the user in Cognito.
    """
    return await _users.create_account_user(account_name, user, context)


@admin_router.delete("/accounts/{account_name}/users")
async def delete_account_user(
    account_name: str,
    email: str = Query(..., description="Email address for the user to be deleted"),
    context: UserContext = Depends(authenticate_user),
):
    """
    Delete an admin user for a specific account by user email
    """
    await _users.delete_account_user(account_name, email, context)


"""
---------- Knowledge Endpoints ----------
-----------------------------------------
"""


@admin_router.get("/knowledge/{resource}/{resource_id}/files")
async def get_knowledge_files(
    resource: ResourceType,
    resource_id: uuid.UUID,
    page: int = Query(1, description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        10, description="Size of each page, cannot be less than 1", gt=0
    ),
    filename: str | None = Query(
        None, description="Optional filename to filter results by"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListKnowledgeFileResponse:
    """
    Retrieve a list of knowledge file names for a specific target resource (e.g. project).
    Returns a list of file names from the knowledge base (Pinecone index).
    Optionally filter the results by filename (case-insensitive partial match).
    """
    return await _knowledge.get_project_knowledge_files(
        resource,
        resource_id,
        filename,
        page=page,
        page_size=page_size,
        context=context,
        session=session,
    )


@admin_router.post("/knowledge/{resource}/{resource_id}/files")
async def upload_knowledge_files(
    resource: ResourceType,
    resource_id: uuid.UUID,
    file: UploadFile = File(...),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Upload a text file to the target resource's knowledge base.
    This endpoint gets the knowledge settings from the target's raw_config,
    generates embeddings for the text content, and stores them in Pinecone.

    The file should be uploaded as a form-data file field.
    """
    content = await file.read()

    filename = file.filename or f"uploaded_file_{str(uuid.uuid4())[-12:]}.txt"

    return await _knowledge.upload_knowledge_file(
        resource, resource_id, filename, content, context, session
    )


@admin_router.delete("/knowledge/{resource}/{resource_id}/files")
async def delete_project_knowledge(
    resource: ResourceType,
    resource_id: uuid.UUID,
    filename: str = Query(...),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> str:
    """
    Delete a text file from the target resource's knowledge base.
    This endpoint deletes the vector data associated with the file name
    from the pinecone index.

    The endpoint returns 200 OK if file is deleted, or if file doesn't
    exist in the index.
    """
    return await _knowledge.delete_knowledge_file(
        resource, resource_id, filename, context, session
    )


@admin_router.delete("/vectors")
async def delete_vector_database_namespace(
    context: UserContext = Depends(authenticate_user),
    pinecone_index_name: str = Query(..., description="Pinecone index name"),
    pinecone_namespace: str = Query(..., description="Pinecone namespace to delete"),
) -> dict:
    """
    Delete all vector data from a specific namespace in the Pinecone index.
    This is a direct delete operation that removes all vectors in the specified namespace.

    WARNING: This operation cannot be undone. All vector data in the namespace will be permanently deleted.
    """
    return await _knowledge.delete_vector_database_namespace(
        context,
        pinecone_index_name,
        pinecone_namespace,
    )


@admin_router.get("/vectors")
async def query_vector_database_namespace(
    context: UserContext = Depends(authenticate_user),
    pinecone_index_name: str = Query(..., description="Pinecone index name"),
    pinecone_namespace: str = Query(..., description="Pinecone namespace to query"),
    query: str = Query(..., description="Query text for semantic search"),
    top_k: int = Query(10, gt=0, le=100, description="Number of top results to return"),
) -> list:
    """
    Query vectors in a specific namespace of the Pinecone index using semantic search.
    This operation performs a semantic search and returns the most relevant results.
    """
    return await _knowledge.query_vector_database_namespace(
        context,
        pinecone_index_name,
        pinecone_namespace,
        query,
        top_k,
    )


@admin_router.post("/accounts/{account_name}/projects/{project_id}/update_menu")
async def update_agent_kb(
    account_name: str,
    project_id: uuid.UUID,
    pinecone_index_name: str = Query(..., description="Pinecone index name"),
    debug: bool = Query(False, description="Enable debug mode"),
    include_category_in_doc_name: bool = Query(
        False, description="Whether to include category name in document names"
    ),
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
) -> dict:
    # TODO: Ask user to review the parsed menu document and system prompt menu, then user can confirm or reject the menu document. Once confirmed, update the agent's config in db, and upsert the menu document to pinecone.
    # TODO: Once menu is parsed and upserted, let user review the menu document and system prompt menu, then user can confirm or reject the menu document. Once confirmed, update the agent's config in db, and upsert the menu document to pinecone; if rejected, delete the menu document from pinecone.
    # TODO: namespace example: {project_name}_{pos_provider}_{store}_{store_id}_{timestamp YYYY-MM-DD_HH:MM}
    """
    Update the knowledge base for an agent.

    The endpoint returns a dictionary of the following:
    - system_prompt_menu: Menu information added to project config
    - pinecone_namespace: Pinecone namespace name
    - pinecone_index_name: Pinecone index name

    When debug is enabled, the endpoint will return the following:
    - debug:
        - pos_provider: POS provider name
        - store_id: Store ID
        - client_id: Client ID
        - client_secret: Client secret
        - token_api_endpoint: Token API endpoint
        - general_api_endpoint: General API endpoint


    If the knowledge base is not updated successfully, the endpoint returns 400 Bad Request.

    Args:
        timestamp: Optional timestamp in YYYY-MM-DD_HH:MM format to append to namespace.
                  If not provided, will search in database or use current time.
        include_category_in_doc_name: Whether to include category name in document names. Defaults to False.
    """
    # Integration details and API endpoints are now retrieved from the project's integrations and raw config
    return await _knowledge.update_agent_kb(
        context,
        db_session,
        account_name,
        project_id,
        pinecone_index_name,
        debug,
        include_category_in_doc_name,
    )


"""
---------- Change Log Endpoints ----------
------------------------------------------
"""


@admin_router.get("/accounts/{account_name}/changes")
async def list_account_changes(
    account_name: str,
    page: int = Query(1, gt=0),
    page_size: int = Query(25, gt=0, le=1000),
    resource_types: list[ChangeResourceType] | None = Query(None),
    resource_id: str | None = Query(None),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListChangeLogsResponse:
    """
    Retrieve a list of change logs for a given account with optional filtering.
    """
    return await _history.list_account_change_logs(
        context=context,
        session=session,
        account_name=account_name,
        page=page,
        page_size=page_size,
        resource_types=resource_types,
        resource_id=resource_id,
    )


@admin_router.get("/changes/{change_log_id}")
async def get_change_log(
    change_log_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ChangeLogDetails:
    """
    Retrieve the details of a specific change log including the changed fields.
    """
    return await _history.get_change_log_details(
        change_log_id=change_log_id,
        context=context,
        session=session,
    )


"""
----------- Lead Management -----------
---------------------------------------
"""


@admin_router.put("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead: CreateLeadRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Lead:
    """
    Create a new lead. Business name is required.
    """
    return await _lead.create_lead(
        lead_request=lead,
        context=context,
        session=session,
    )


@admin_router.get("/leads")
async def get_leads(
    page: int = Query(1, gt=0, description="Page number"),
    page_size: int = Query(20, gt=0, le=100, description="Number of items per page"),
    status: list[LeadStatus] | None = Query(
        None, description="Optional list of statuses to filter leads by"
    ),
    segment: list[BusinessSegment] | None = Query(
        None, description="Optional list of segments to filter leads by"
    ),
    tier: list[TargetTier] | None = Query(
        None, description="Optional list of tiers to filter leads by"
    ),
    keyword: str | None = Query(
        None, description="Optional keyword to search in business_name and owner fields"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListLeadsResponse:
    """
    Retrieve a paginated list of leads with optional filters.
    Supports filtering by multiple statuses, segments, tiers, and keyword search.

    Example usage:
    - Filter by multiple statuses: ?status=pending&status=converted
    - Filter by multiple segments: ?segment=smb&segment=mm
    - Combine filters: ?status=pending&segment=smb&tier=standard&keyword=restaurant
    """
    return await _lead.list_leads(
        context=context,
        session=session,
        page=page,
        page_size=page_size,
        status=status,
        segment=segment,
        tier=tier,
        keyword=keyword,
    )


@admin_router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Lead:
    """
    Get a lead by ID.
    """
    return await _lead.get_lead(
        lead_id=lead_id,
        context=context,
        session=session,
    )


@admin_router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID,
    lead: UpdateLeadRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Lead:
    """
    Update an existing lead by ID.
    """
    return await _lead.update_lead(
        lead_id=lead_id,
        lead_request=lead,
        context=context,
        session=session,
    )


@admin_router.delete("/leads/{lead_id}")
async def delete_lead(
    lead_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete a lead by ID.
    """
    await _lead.delete_lead(
        lead_id=lead_id,
        context=context,
        session=session,
    )


"""
---------- Onboarding Endpoint ----------
---------------------------------------
"""


@admin_router.post("/onboarding", status_code=status.HTTP_201_CREATED)
async def onboard(
    request: OnboardingRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Onboard a new account with agents and projects in a single transaction.
    """
    return await create_onboarding(request, context, session)


"""
---------- Subscription Plan Endpoints ----------
-----------------------------------------------
"""


@admin_router.put("/plans")
async def create_subscription_plan(
    request: CreateSubscriptionPlanRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> SubscriptionPlan:
    """
    Creates a new subscription plan.
    """
    return _subscription.create_subscription_plan(context, session, request)


@admin_router.get("/plans")
async def list_subscription_plans(
    hidden: Optional[bool] = Query(
        None,
        description="Filter by hidden status (true = hidden only, false = not hidden only, null = all)",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Retrieves all subscription plans, optionally filtered by hidden status.

    Args:
        hidden: Optional filter for hidden status:
            - true: return only hidden plans
            - false: return only non-hidden plans
            - null/omitted: return all plans
    """
    return _subscription.list_subscription_plans(context, session, hidden=hidden)


@admin_router.get("/plans/{plan_id}")
async def get_subscription_plan(
    plan_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Retrieves a subscription plan by ID.
    """
    return _subscription.get_subscription_plan(context, session, plan_id)


@admin_router.patch("/plans/{plan_id}")
async def update_subscription_plan(
    plan_id: uuid.UUID,
    request: UpdateSubscriptionPlanRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> SubscriptionPlan:
    """
    Updates a subscription plan with business logic for field restrictions.

    Business Rules:
    - If there are no linked account subscriptions (deleted ones are fine), all fields can be updated
    - If there are any linked account subscriptions that are not deleted, only these fields can be updated:
      - sort_id
      - free_trial_days
      - active
      - hidden
    """
    return _subscription.update_subscription_plan(context, session, plan_id, request)


@admin_router.delete("/plans/{plan_id}")
async def delete_subscription_plan(
    plan_id: uuid.UUID,
    hard_delete: bool = Query(
        False, description="Physically delete from database if true"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Hard delete a subscription plan when it has 0 subscriptions attached.
    """
    return _subscription.delete_subscription_plan(
        plan_id, hard_delete, context, session
    )


"""
---------- Subscription Endpoints ----------
------------------------------------------
"""


@admin_router.put("/accounts/{account_name}/subscriptions")
async def create_account_subscription(
    account_name: str,
    request: CreateSubscriptionRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Creates a new subscription for an account.
    """
    return _subscription.create_account_subscription(
        context, session, account_name, request
    )


@admin_router.get("/accounts/{account_name}/subscriptions")
def list_account_subscriptions(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListAccountSubscriptionsResponse:
    """
    Retrieves all active subscriptions for the given account.
    Scheduled subscriptions are sorted by start_date if there are multiple.
    """
    return _subscription.list_account_subscriptions(context, session, account_name)


@admin_router.patch("/accounts/{account_name}/subscriptions/{external_id}")
def update_account_subscription(
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionRequest,
    force_update: bool = Query(
        False, description="Whether to allow updates on non-active subscriptions"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Subscription:
    """
    Modifies the account_subscription configuration referenced by the external id.
    If the status of the latest version is not valid, no edit can be made unless force_update is true.
    This creates a new version with incremented version number.
    """
    return _subscription.update_account_subscription(
        context, session, account_name, external_id, request, force_update
    )


@admin_router.patch("/accounts/{account_name}/subscriptions/{external_id}/status")
def update_account_subscription_status(
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionStatusRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UpdateAccountSubscriptionStatusResponse:
    """
    Updates the status of the referenced account_subscription.
    Only active subscriptions can be updated to active or pending status.
    This API can be used to cancel a subscription.
    """
    return _subscription.update_account_subscription_status(
        context, session, account_name, external_id, request
    )


@admin_router.post("/accounts/{account_name}/subscriptions/{external_id}/cancel")
def cancel_account_subscription(
    account_name: str,
    external_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Cancels a subscription for the given account.

    This operation cannot be reverted unless they sign up again.
    """
    return _subscription.cancel_account_subscription(
        context, session, account_name, external_id
    )


@admin_router.post("/accounts/{account_name}/subscriptions/{external_id}/checkout")
def create_subscription_checkout_session(
    account_name: str,
    external_id: uuid.UUID,
    request: CreateCheckoutSessionRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> str:
    """
    Creates a Stripe checkout session for a subscription.
    The subscription must be active and not have a stripe_subscription_id.
    """
    return _subscription.create_checkout_session(
        context, session, account_name, external_id, request
    )


@admin_router.get("/subscriptions/checkout/callback", status_code=status.HTTP_200_OK)
def handle_subscription_checkout_callback(
    session_id: str = Query(..., description="stripe checkout session id"),
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
):
    """
    Handles the callback from stripe payment success event.
    """
    _subscription.handle_subscription_checkout_callback(context, db_session, session_id)


@admin_router.get("/subscriptions/{external_id}/projects")
def list_project_subscriptions_by_subscription_external_id(
    external_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
):
    """List all project subscriptions for a given subscription external ID."""
    return _subscription.list_project_subscriptions_by_subscription_external_id(
        context, db_session, external_id
    )


@admin_router.put("/accounts/{account_name}/subscriptions/{external_id}/projects")
def create_project_subscription(
    account_name: str,
    external_id: uuid.UUID,
    request: CreateProjectSubscriptionRequest,
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
):
    """Create a new project subscription."""
    return _subscription.create_project_subscription(
        context, db_session, account_name, external_id, request
    )


@admin_router.delete(
    "/accounts/{account_name}/subscriptions/{external_id}/projects/{project_id}"
)
def remove_project_subscription(
    account_name: str,
    external_id: uuid.UUID,
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
):
    """Remove a project subscription."""
    return _subscription.remove_project_subscription(
        context, db_session, account_name, external_id, project_id
    )


"""
---------- Prompt Endpoints ----------
------------------------------------
"""


@admin_router.put("/accounts/{account_name}/prompts")
async def create_prompt(
    account_name: str,
    request: CreatePromptRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Create a new prompt.
    """
    return _prompt.create_prompt(context, session, account_name, request)


@admin_router.get("/accounts/{account_name}/prompts")
def get_prompts(
    account_name: str,
    resource_type: str | None = Query(
        None, description="Optional filter by resource type"
    ),
    resource_id: uuid.UUID | None = Query(
        None, description="Optional filter by resource ID"
    ),
    search: str | None = Query(
        None, description="Optional search term to match against prompt name"
    ),
    channels: list[str] | None = Query(
        None, description="Optional list of channels to filter by"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Get prompts with optional filtering, search, and channel filtering.
    """
    return _prompt.get_prompts(
        context, session, account_name, resource_type, resource_id, search, channels
    )


@admin_router.patch("/accounts/{account_name}/prompts/{prompt_id}")
def update_prompt(
    account_name: str,
    prompt_id: uuid.UUID,
    request: UpdatePromptRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Prompt:
    """
    Update an existing prompt.
    """
    return _prompt.update_prompt(context, session, account_name, prompt_id, request)


@admin_router.get("/accounts/{account_name}/prompts/{prompt_id}/versions")
def get_prompt_versions(
    account_name: str,
    prompt_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> list[PromptDetails]:
    """
    Get all versions of prompt details for a specific prompt.
    """
    return _prompt.get_prompt_versions(context, session, account_name, prompt_id)


@admin_router.delete("/accounts/{account_name}/prompts/{prompt_id}")
def delete_prompt(
    account_name: str,
    prompt_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete an existing prompt (soft delete).
    """
    _prompt.delete_prompt(context, session, account_name, prompt_id)


@admin_router.get("/accounts/{account_name}/prompts/system")
def get_system_prompts(
    account_name: str,
    resource_type: str = Query(..., description="Resource type"),
    resource_id: uuid.UUID = Query(..., description="Resource ID"),
    search: str | None = Query(
        None, description="Search term to filter prompts by title or instructions"
    ),
    channels: str | None = Query(
        None,
        description="Comma-separated list of channels to filter by (e.g. 'sms,voice,api')",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> list[SystemPrompt]:
    """
    Get filtered system prompts based on resource type, agent type, plan tier, search, and channels.
    """
    return _prompt.get_system_prompts(
        context, session, account_name, resource_type, resource_id, search, channels
    )
