import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
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
from api.routes.admin._utils import SortOrder
from api.routes.endpoints import endpoints
from api.routes.integrations.square import _implementation
from api.schemas.admin.account import (
    AcceptTermsResponse,
    Account,
    AccountStatisticsResponse,
    AccountStatusResponse,
    CreateAccountRequest,
    ListAccountsResponse,
    NotificationPreferencesResponse,
    TermsStatusResponse,
    UpdateAccountRequest,
    UpdateNotificationPreferencesRequest,
)
from api.schemas.admin.affiliate import (
    AffiliateResponse,
    CreateAffiliateRequest,
    UpdateAffiliateRequest,
)
from api.schemas.admin.agent import (
    Agent,
    AgentSummary,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from api.schemas.admin.analytics import GetAllReportsResponse
from api.schemas.admin.billing import (
    GenerateInvoiceRequest,
    GenerateInvoiceResponse,
    InvoiceActionRequest,
    InvoiceActionResponse,
    ListInvoicesResponse,
    UpdatePaymentMethodRequest,
    UpdatePaymentMethodResponse,
)
from api.schemas.admin.campaign import CreateCampaignResponse, ListCampaignsResponse
from api.schemas.admin.conversation import (
    DEFAULT_STATS_AGE,
    ConversationDetail,
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
    UpdateConversationRequest,
)
from api.schemas.admin.email import (
    GetTemplateInfoRequest,
    ListTemplatesRequest,
    SendBatchEmailsRequest,
    SendEmailRequest,
)
from api.schemas.admin.faq import (
    FAQ,
    CreateFAQRequest,
    ListFAQsResponse,
    UpdateFAQRequest,
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
    SigninGoogleUserRequest,
    SigninGoogleUserResponse,
)
from api.schemas.admin.phone_number import (
    EnhancedReleaseProjectNumberRequest,
    EnhancedReleaseProjectNumberResponse,
    ListPhoneNumbersResponse,
    PurchaseNumberRequest,
    PurchaseNumberResponse,
    ReleaseNumberRequest,
    ReleaseNumberResponse,
    ReleaseProjectNumberRequest,
    ReserveProjectNumberRequest,
)
from api.schemas.admin.project import (
    BatchCreateProjectsRequest,
    BatchCreateProjectsResponse,
    BatchDeleteProjectsRequest,
    BatchDeleteProjectsResponse,
    BatchUpdateProjectsRequest,
    BatchUpdateProjectsResponse,
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
from api.schemas.admin.signature import InitiateTermsSigningRequest
from api.schemas.admin.subscription import (
    CreateCheckoutSessionRequest,
    CreateProjectSubscriptionRequest,
    CreateStripeCustomerRequest,
    CreateSubscriptionPlanRequest,
    CreateSubscriptionRequest,
    GetAccountCreditResponse,
    GetCurrentSubscriptionResponse,
    GrantAccountCreditRequest,
    ListAccountCreditGrantsResponse,
    ListAccountSubscriptionsResponse,
    StripeCustomer,
    Subscription,
    SubscriptionPlan,
    SwitchPlanRequest,
    SwitchPlanResponse,
    UpdateAccountSubscriptionRequest,
    UpdateAccountSubscriptionStatusRequest,
    UpdateAccountSubscriptionStatusResponse,
    UpdateStripeCustomerRequest,
    UpdateSubscriptionPlanRequest,
)
from api.schemas.admin.team import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    AcceptMultipleInvitationsRequest,
    AcceptMultipleInvitationsResponse,
    DecodeInvitationTokenRequest,
    DecodeInvitationTokenResponse,
    InvitationDetailsResponse,
    InvitationResponse,
    InviteTeamMemberRequest,
    ResendInvitationResponse,
    SwitchAccountRequest,
    SwitchAccountResponse,
    TeamMembersListResponse,
    UpdateTeamMemberRequest,
    UpdateTeamMemberResponse,
    UserAccountsListResponse,
    UserAccountsWithUserIdListResponse,
    UserPendingInvitationsResponse,
)
from api.schemas.admin.user import SignUpRequest
from api.schemas.admin.user_management import (
    AssignAccountRequest,
    AssignAccountResponse,
    CreateUserRequest,
    ListUsersResponse,
    UserInfo,
)
from api.schemas.admin.voice_config import (
    BatchUpdateVoiceConfigsRequest,
    BatchUpdateVoiceConfigsResponse,
    CreateVoiceConfigRequest,
    ListVoiceConfigsResponse,
    UpdateVoiceConfigRequest,
    VoiceConfig,
)
from db.tables.change_log import ChangeResourceType
from db.tables.lead import BusinessSegment, LeadStatus, TargetTier
from db.tables.types import Channel, CheckStatus
from services.admin_service.schema import CognitoUser
from services.auth_service import (
    require_account_permission,
    require_agent_permission,
    require_campaign_permission,
    require_feedback_permission,
    require_history_permission,
    require_project_permission,
)
from services.auth_types import UserContext
from services.campaign_service.schema import CampaignDetails, CreateCampaignRequest
from services.google_maps_service import search_places_by_name
from services.google_maps_service.schemas import (
    GoogleMapsSearchRequest,
    GoogleMapsSearchResponse,
)

from . import (
    _account,
    _affiliate,
    _agent,
    _analytics,
    _auth,
    _billing,
    _campaign,
    _conversation,
    _email,
    _faq,
    _feedback,
    _history,
    _integration,
    _knowledge,
    _lead,
    _onboarding,
    _phone_number,
    _projects,
    _prompt,
    _subscription,
    _team,
    _users,
    _voice_config,
)
from ._auth import authenticate_user, authorize_admin, require_admin

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
async def self_onboarding(
    request: SelfOnboardingRequest,
    response: Response,
    session: Session = Depends(db.get_db),
) -> SelfOnboardingResponse:
    """
    Sign up a new user and create an account. Creates the account first, then the Cognito user.
    If Cognito user creation fails, the account will be deleted.
    """
    return await _onboarding.self_onboarding(request, response, session)


@admin_router.post("/signin/google", status_code=status.HTTP_200_OK)
def signin_google(request: SigninGoogleUserRequest) -> SigninGoogleUserResponse:
    """
    Sign in a user using Google credentials. If the user does not exist, create a new user.
    """
    return _onboarding.signin_google_user(request)


@admin_router.get("/signin/google/verify", status_code=status.HTTP_200_OK)
def is_google_user(email: str = Query(..., description="Email to Check")) -> bool:
    """
    Test if the user is a Google user.
    """
    return _onboarding.is_google_user(email)


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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Delete the account identified by name.
    """
    await _account.delete_account(account_name, hard_delete, context, session)


@admin_router.post("/accounts/{account_name}/close")
async def close_account(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Close the account by canceling the Stripe subscription and updating status to disabled.
    """
    return await _account.close_account(account_name, context, session)


@admin_router.get("/accounts/{account_name}/notification_preferences")
def get_notification_preferences(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> NotificationPreferencesResponse:
    """
    Get notification preferences for an account.
    """
    return _account.get_notification_preferences(account_name, context, session)


@admin_router.post("/accounts/{account_name}/notification_preferences")
async def update_notification_preferences(
    account_name: str,
    update_request: UpdateNotificationPreferencesRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> NotificationPreferencesResponse:
    """
    Update notification preferences for an account.
    """
    return await _account.update_notification_preferences(
        account_name, update_request, context, session
    )


@admin_router.get("/accounts/{account_name}/agents")
async def list_account_agents(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> list[AgentSummary]:
    """
    Retrieve a list of agents associated with the given account name.
    """
    return await _account.list_account_agents(account_name, context, session)


@admin_router.get("/accounts/{account_name}/projects")
async def list_account_projects(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> list[Project]:
    """
    Retrieve a list of projects associated with the given account name.
    """
    return await _projects.list_account_projects(account_name, context, session)


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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> AccountStatusResponse:
    """
    Retrieve account status by account name.
    """
    return _account.get_account_status(account_name, context, session)


@admin_router.get("/accounts/{account_name}/terms_status")
def get_account_terms_status(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> TermsStatusResponse:
    """
    Retrieve terms acceptance status by account name.
    """
    return _account.get_account_terms_status(account_name, context, session)


@admin_router.post("/accounts/{account_name}/initiate_terms_signing")
async def initiate_terms_signing_endpoint(
    account_name: str,
    request: InitiateTermsSigningRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Initiate DocuSign terms signing. Returns signing URL.
    After user signs, frontend should call /complete_terms_signing.
    """
    return await _account.initiate_terms_signing(
        account_name=account_name,
        signer_name=request.signer_name,
        signer_email=request.signer_email,
        redirect_url=str(request.redirect_url),
        frame_ancestors=request.frame_ancestors,
        context=context,
        session=session,
    )


@admin_router.post("/accounts/{account_name}/complete_terms_signing")
async def complete_terms_signing_endpoint(
    account_name: str,
    envelope_id: str = Query(..., description="DocuSign envelope ID"),
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Mark terms as accepted after DocuSign signing completes.
    Frontend calls this when DocuSign JS fires 'signing_complete' event.
    """
    return await _account.complete_terms_signing(
        account_name=account_name,
        envelope_id=envelope_id,
        context=context,
        session=session,
    )


@admin_router.put("/accounts/{account_name}/accept_terms")
async def accept_account_terms(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> AcceptTermsResponse:
    """
    Accept terms and conditions for the specified account.
    """
    return await _account.accept_account_terms(account_name, context, session)


"""
---------- Integrations Endpoints ----------
--------------------------------------------
"""


@admin_router.get("/accounts/{account_name}/integrations")
def list_integrations(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_agent_permission("agent.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_agent_permission("agent.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_agent_permission("agent.delete", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Delete the specified agent by id.
    """
    await _agent.delete_agent(agent_id, context, session)


@admin_router.get("/agents/{agent_id}/projects")
async def list_agent_projects(
    agent_id: uuid.UUID,
    context: UserContext = Depends(
        require_agent_permission("agent.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_agent_permission("agent.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_campaign_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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


@admin_router.get("/accounts/{account_name}/conversations")
async def list_account_conversations(
    account_name: str,
    keyword: str = Query("", description="Optional keyword to filter the results by"),
    channel: Channel | None = Query(
        None, description="Optional channel to filter the results by"
    ),
    project_id: uuid.UUID | None = Query(
        None, description="Optional project ID to filter conversations by"
    ),
    lookback: int | None = Query(
        None,
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
    language: list[str] | None = Query(
        None, description="Optional list of languages to filter conversations by"
    ),
    purpose: list[str] | None = Query(
        None, description="Optional list of call purposes to filter conversations by"
    ),
    ended_reason: list[str] | None = Query(
        None, description="Optional list of call end reasons to filter conversations by"
    ),
    customer_converted: bool | None = Query(
        None,
        description="Filter by customer conversion status. True for converted, False for not converted, None for all",
    ),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListUserSessionsResponse:
    """
    Retrieve the list of convo sessions for a given account. Returned conversations
    are sorted by the timestamp of the last message in reverse chronological order.
    """
    return await _conversation.list_account_conversations(
        account_name,
        keyword,
        channel,
        project_id,
        lookback,
        page,
        page_size,
        escalated,
        hide_testing_sessions,
        language,
        purpose,
        ended_reason,
        customer_converted,
        context,
        session,
    )


@admin_router.get("/accounts/{account_name}/conversations/{conversation_id}")
async def get_conversation_detail(
    account_name: str,
    conversation_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ConversationDetail:
    """
    Get conversation details for the given conversation ID, excluding messages.
    """
    return await _conversation.get_conversation_detail(
        account_name, conversation_id, context, session
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListConversationMessagesResponse:
    """
    Returns the detailed convo session messages for the given id. Messages are sorted
    in chronological order.
    """
    return await _conversation.list_conversation_messages(
        account_name, conversation_id, page, page_size, sort_order, context, session
    )


@admin_router.patch(
    "/accounts/{account_name}/conversations/{conversation_id}", status_code=200
)
async def update_conversation(
    account_name: str,
    conversation_id: uuid.UUID,
    update_request: UpdateConversationRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Update the session with the given id.
    """
    await _conversation.update_conversation(
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_feedback_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_feedback_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_feedback_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Delete the referenced feedback, return 200 OK if the feedback is successfully
    deleted or if it doesn't exist. No response content is returned.
    """
    await _feedback.delete_feedback(feedback_id, context, session)


"""
---------- FAQ Endpoints ----------
------------------------------------
"""


@admin_router.get("/accounts/{account_name}/faqs")
async def get_faqs(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
    project_id: str | None = Query(None, description="Optional project ID"),
) -> ListFAQsResponse:
    """
    Get all FAQs for an account, optionally filtered by project ID.
    """
    return await _faq.get_faqs(account_name, context, session, project_id)


@admin_router.put("/accounts/{account_name}/faqs", status_code=status.HTTP_201_CREATED)
async def create_faq(
    account_name: str,
    faq: CreateFAQRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> FAQ:
    """
    Create an FAQ for an account.
    """
    return await _faq.create_faq(account_name, faq, context, session)


@admin_router.patch("/accounts/{account_name}/faqs/{faq_id}")
async def update_faq(
    account_name: str,
    faq_id: uuid.UUID,
    update_faq: UpdateFAQRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> FAQ:
    """
    Update an FAQ
    """
    return await _faq.update_faq(account_name, faq_id, update_faq, context, session)


@admin_router.delete("/accounts/{account_name}/faqs/{faq_id}")
async def delete_faq(
    account_name: str,
    faq_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> None:
    """
    Delete an FAQ
    """
    return await _faq.delete_faq(account_name, faq_id, context, session)


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

    Optionally, you can provide a subscription_id to immediately add the project
    to an existing active subscription. If linking fails, the entire operation
    is rolled back and no project is created.

    If no subscription_id is provided, the project will be created without any
    subscription association and can be added to a subscription later via the
    subscription management endpoints.
    """
    return await _projects.create_project(project, context, session)


@admin_router.post("/projects/batch", status_code=status.HTTP_201_CREATED)
async def batch_create_projects(
    request: BatchCreateProjectsRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> BatchCreateProjectsResponse:
    """
    Create multiple projects in batch for a given account.

    This endpoint allows you to create many projects at once from JSON data,
    such as restaurant locations. Each project can include:

    - Unique project name and display name
    - Location address and timezone
    - Store hours and contact information
    - Product/menu information
    - Service instructions for the AI agent

    The response includes detailed results for each project creation attempt,
    including success/failure status and error messages for any failed creations.
    """
    return await _projects.batch_create_projects(request, context, session)


@admin_router.patch("/projects/batch", status_code=status.HTTP_200_OK)
async def batch_update_projects(
    request: BatchUpdateProjectsRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> BatchUpdateProjectsResponse:
    """
    Update multiple projects in batch for a given account.

    This endpoint allows you to update many projects at once from JSON data.

    Only fields that are provided in the request will be updated - fields set to null
    or omitted will remain unchanged. This allows for partial updates of projects.

    The response includes detailed results for each project update attempt,
    including success/failure status and error messages for any failed updates.
    """
    return await _projects.batch_update_projects(request, context, session)


@admin_router.delete("/projects/batch", status_code=status.HTTP_200_OK)
async def batch_delete_projects(
    request: BatchDeleteProjectsRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> BatchDeleteProjectsResponse:
    """
    Delete multiple projects in batch for a given account.

    This endpoint allows you to delete many projects at once by providing their IDs.
    All projects must belong to the specified account.

    The response includes detailed results for each project deletion attempt,
    including success/failure status and error messages for any failed deletions.
    """
    return await _projects.batch_delete_projects(request, context, session)


@admin_router.get("/projects/{project_id}")
def get_project(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.delete", authenticate_user)
    ),
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


@admin_router.post(
    "/projects/{project_id}/release_number_enhanced",
    response_model=EnhancedReleaseProjectNumberResponse,
    status_code=status.HTTP_200_OK,
)
async def release_phone_number_enhanced(
    project_id: uuid.UUID,
    request: EnhancedReleaseProjectNumberRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Enhanced release phone number with options for reuse or permanent deletion.

    Provides two release options:
    - return_to_pool: Keeps the number in both Twilio and Vapi, marking it AVAILABLE for reuse
    - delete_permanently: Completely removes from both Vapi and Twilio
    """
    return await _phone_number.release_phone_number_enhanced(
        project_id, request, context, session
    )


@admin_router.get("/phone_numbers", response_model=ListPhoneNumbersResponse)
async def list_phone_numbers(
    page: int = Query(
        1,
        ge=1,
        description="Page number for pagination (1-based, default: 1).",
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Number of phone numbers per page"
    ),
    friendly_name: Optional[str] = Query(
        None,
        description="Optional friendly name to filter by (exact match). Example: 'AVAILABLE' to find numbers with friendly_name '{env}: AVAILABLE'",
    ),
    phone_number: Optional[str] = Query(
        None,
        description="Optional phone number to filter by (partial match). Only returns numbers with friendly_name starting with current environment prefix. Example: '1555' to find numbers containing '1555'",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    List purchased phone numbers from Twilio account for the current environment.

    Uses efficient streaming pagination for optimal performance across all filtering scenarios:

    **Three Filtering Scenarios:**
    1. **Phone Number**: Partial match in phone number + environment prefix (hybrid: native+environment check) - HIGHEST PRIORITY
    2. **Friendly Name**: Exact match for "{env}: {friendly_name}" (hybrid: native+streaming)
    3. **Environment Only**: Returns all numbers with friendly_name starting with "{env}:" (pure streaming)

    **Filtering Details:**
    - friendly_name: Exact match (e.g., "AVAILABLE" matches "dev: AVAILABLE" only) - uses native Twilio filtering
    - phone_number: Partial match (e.g., "1555" matches "+15551234567") - uses native Twilio filtering + environment check
    - phone_number filtering takes priority over friendly_name if both provided
    - All results are environment-scoped (friendly_name must start with current env prefix)

    **Pagination:** Uses 1-based pagination with memory-efficient streaming and early termination.

    Includes project and account associations for each phone number.
    """
    return await _phone_number.list_phone_numbers(
        context=context,
        session=session,
        page=page,
        page_size=page_size,
        friendly_name=friendly_name,
        phone_number=phone_number,
    )


@admin_router.post("/phone_numbers", response_model=PurchaseNumberResponse)
async def purchase_phone_number(
    request: PurchaseNumberRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Purchase a single phone number.

    This endpoint allows administrators to purchase a phone number
    with optional criteria like area code and number patterns.

    Parameters:
    - country_code: Country code for the number (default: 'US')
    - toll_free: Whether to purchase a toll-free number (default: false)
    - area_code: Optional area code for local numbers (e.g., '415')
    - contains: Optional pattern (e.g., '*6666' for ending with 6666, '*PALONA' for ending with PALONA, '555*' for containing 555)

    Notes:
    - area_code and contains can be combined for more specific searches
    - Purchased numbers automatically use "AVAILABLE" as their merchant name
    - Numbers are ready to be assigned to projects after purchase
    - For multiple numbers, make multiple API calls from the frontend
    """
    return await _phone_number.purchase_number(request, context, session)


@admin_router.delete("/phone_numbers", response_model=ReleaseNumberResponse)
async def release_standalone_phone_number(
    request: ReleaseNumberRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete a standalone phone number (not associated with any project).

    This endpoint allows administrators to completely delete phone numbers that are not
    currently assigned to any project. The number will be permanently removed from both
    Vapi and Twilio systems.

    Parameters:
    - phone_number: The phone number to delete (e.g., '+15551234567')

    Notes:
    - Only works for numbers not currently assigned to projects
    - For project-assigned numbers, use the project-specific release endpoint
    - Number will be completely deleted from both Vapi and Twilio (irreversible)
    - Operation will fail if number not found in either system
    """
    return await _phone_number.release_standalone_number(request, context, session)


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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListUsersResponse:
    """
    Retrieve a list of admin users for a specific account.
    """
    return await _users.list_account_users(account_name, context, session)


@admin_router.put("/accounts/{account_name}/users")
async def create_account_user(
    account_name: str,
    user: CreateUserRequest,
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> UserInfo:
    """
    Create a new admin user for a specific account.
    Uses AdminCreateUser flow to create the user in Cognito.
    """
    return await _users.create_account_user(account_name, user, context, session)


@admin_router.delete("/accounts/{account_name}/users")
async def delete_account_user(
    account_name: str,
    email: str = Query(..., description="Email address for the user to be deleted"),
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Delete an admin user for a specific account by user email
    """
    await _users.delete_account_user(account_name, email, context, session)


@admin_router.post("/users/assign-account")
async def assign_account_to_user(
    request: AssignAccountRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AssignAccountResponse:
    """
    Assign an existing user to an account with a specified role.

    This is an admin-only endpoint that creates:
    1. AccountUser record (membership)
    2. ResourceRoleAssignment record (role on account resource)

    The user must already exist in Cognito.
    """
    return await _users.assign_account_to_user(request, context, session)


"""
---------- Billing & Invoice Management Endpoints ----------
------------------------------------------------------------
"""


@admin_router.patch("/accounts/{account_name}/billing/payment-method")
async def update_payment_method(
    account_name: str,
    request: UpdatePaymentMethodRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> UpdatePaymentMethodResponse:
    """
    Update the payment method for an account's subscription.

    Switches between:
    - 'autopay': Automatic credit card charges (default)
    - 'invoice': Manual invoicing with payment terms
    """
    return await _billing.update_payment_method(account_name, request, context, session)


@admin_router.post("/accounts/{account_name}/billing/invoices")
async def generate_invoice(
    account_name: str,
    request: GenerateInvoiceRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> GenerateInvoiceResponse:
    """
    Manually generate and send an invoice for an account.

    This endpoint:
    1. Creates a draft invoice with all pending charges
    2. Finalizes the invoice
    3. Sends it to the customer via email

    Only works for accounts with payment_method='invoice'.
    """
    return await _billing.generate_invoice(account_name, request, context, session)


@admin_router.get("/accounts/{account_name}/billing/invoices")
async def list_invoices(
    account_name: str,
    limit: int = Query(10, description="Maximum number of invoices to return"),
    status: str | None = Query(
        None,
        description="Filter by status (draft, open, paid, void, uncollectible)",
    ),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListInvoicesResponse:
    """
    List invoices for an account.

    Args:
        limit: Maximum number of invoices to return (default: 10)
        status: Filter by status (draft, open, paid, void, uncollectible)
    """
    return await _billing.list_invoices(account_name, context, session, limit, status)


@admin_router.post("/accounts/{account_name}/billing/invoices/{invoice_id}/finalize")
async def finalize_invoice(
    account_name: str,
    invoice_id: str,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> InvoiceActionResponse:
    """
    Finalize and send a draft invoice.

    This locks the invoice and emails it to the customer.
    """
    request = InvoiceActionRequest(invoice_id=invoice_id)
    return await _billing.finalize_invoice(account_name, request, context, session)


@admin_router.post("/accounts/{account_name}/billing/invoices/{invoice_id}/void")
async def void_invoice(
    account_name: str,
    invoice_id: str,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> InvoiceActionResponse:
    """
    Void (cancel) an invoice.
    """
    request = InvoiceActionRequest(invoice_id=invoice_id)
    return await _billing.void_invoice(account_name, request, context, session)


"""
---------- Team Management Endpoints ----------
-----------------------------------------------
"""


@admin_router.post("/accounts/{account_name}/team/invite")
async def invite_team_member(
    account_name: str,
    request: InviteTeamMemberRequest,
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> InvitationResponse:
    """
    Invite a new team member to the account with specified role.

    Creates a pending invitation and returns invitation token.
    Owner permission required.
    """
    return await _team.invite_team_member(account_name, request, context, session)


@admin_router.get("/accounts/{account_name}/team")
async def list_team_members(
    account_name: str,
    role: str | None = Query(None, description="Filter by role"),
    status: str | None = Query(
        None, description="Filter by status (active, deactivated)"
    ),
    search: str | None = Query(None, description="Search by email or name"),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> TeamMembersListResponse:
    """
    List all team members for an account.

    Supports filtering by role, status, and search.
    Any authenticated user with account access can view team members.
    """
    return await _team.list_team_members(
        account_name, context, session, role, status, search
    )


@admin_router.patch("/accounts/{account_name}/team/{user_email}")
async def update_team_member_role(
    account_name: str,
    user_email: str,
    request: UpdateTeamMemberRequest,
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> UpdateTeamMemberResponse:
    """
    Update a team member's role.

    Cannot demote the last owner. Owner permission required.
    """
    return await _team.update_team_member_role(
        account_name, user_email, request, context, session
    )


@admin_router.delete(
    "/accounts/{account_name}/team/{user_email}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_team_member(
    account_name: str,
    user_email: str,
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Remove a team member from the account.

    Cannot remove the last owner. Owner permission required.
    """
    await _team.remove_team_member(account_name, user_email, context, session)


"""
---------- Invitation Endpoints ----------
------------------------------------------
"""


@admin_router.get("/invitations/pending")
async def get_pending_invitations(
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UserPendingInvitationsResponse:
    """
    Get all pending invitations for the authenticated user.

    Returns list of invitations with account details and expiration info.
    """
    return await _team.get_pending_invitations_for_user(context, session)


@admin_router.get("/invitations/{token}")
async def get_invitation_details(
    token: str,
    session: Session = Depends(db.get_db),
) -> InvitationDetailsResponse:
    """
    Get invitation details by token (public endpoint, no auth required).

    Returns account name, invited by, role, and expiration info.
    """
    return await _team.get_invitation_details(token, session)


@admin_router.post("/invitations/decode")
async def decode_invitation_token(
    request: DecodeInvitationTokenRequest,
) -> DecodeInvitationTokenResponse:
    """
    Decode invitation JWT token to extract credentials (public endpoint, no auth required).

    Returns email and temporary password (if present) for auto-populating sign-in form.
    """
    return await _team.decode_invitation_token(request)


@admin_router.post("/invitations/accept")
async def accept_invitation(
    request: AcceptInvitationRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AcceptInvitationResponse:
    """
    Accept an invitation and join the account.

    Creates account membership and role assignment.
    User must be authenticated.
    """
    return await _team.accept_invitation(request, context, session)


@admin_router.post("/invitations/accept-multiple")
async def accept_multiple_invitations(
    request: AcceptMultipleInvitationsRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AcceptMultipleInvitationsResponse:
    """
    Accept multiple invitations at once.

    Processes all invitations and returns results for each.
    Continues processing even if some fail.
    """
    return await _team.accept_multiple_invitations(request, context, session)


@admin_router.post("/accounts/{account_name}/team/invitations/{invitation_id}/resend")
async def resend_invitation(
    account_name: str,
    invitation_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.team_manage", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ResendInvitationResponse:
    """
    Resend invitation email for a pending invitation.

    Only pending invitations can be resent. Owner permission required.
    """
    return await _team.resend_invitation(account_name, invitation_id, context, session)


"""
---------- Multi-Account Support Endpoints ----------
-----------------------------------------------------
"""


@admin_router.get("/users/me/accounts")
async def list_user_accounts(
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UserAccountsListResponse:
    """
    List all accounts the current user has access to.

    Used for account switcher UI. Returns account details with roles.
    """
    return await _team.list_user_accounts(context, session)


@admin_router.get("/users/{email}/accounts")
async def list_user_accounts_by_email(
    email: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> UserAccountsWithUserIdListResponse:
    """
    List all accounts a specific user has access to by their email.

    This is an admin-only endpoint for looking up account memberships by user email.
    The email is converted to user_id internally for the lookup.
    Useful for support, user management, and account administration.

    Admin authorization is enforced at the service layer to prevent cross-tenant
    information leaks.

    Args:
        email: Email address of the user to look up (converted to user_id internally)

    Returns:
        UserAccountsWithUserIdListResponse: List of accounts with user_id, roles and last access time

    Raises:
        403: User is not an admin (enforced in service layer)
        404: User not found
        500: Error retrieving accounts
    """
    return await _team.list_user_accounts_by_email(context, email, session)


@admin_router.post("/users/me/switch-account")
async def switch_account(
    request: SwitchAccountRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> SwitchAccountResponse:
    """
    Switch active account context.

    Backend is stateless, this is for frontend state management.
    Verifies user has access to the account.
    """
    return await _team.switch_account(request, context, session)


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
    menu_last_updated: Optional[str] = Query(
        None, description="Last updated date of the menu"
    ),
    selected_menus: Optional[list[str]] = Query(
        None, description="List of menu names to process"
    ),
    context: UserContext = Depends(authenticate_user),
    db_session: Session = Depends(db.get_db),
) -> dict:
    """
    Update the knowledge base for an agent by downloading menu data, generating embeddings, and storing in Pinecone.

    Args:
        account_name: Account name
        project_id: Project UUID
        pinecone_index_name: Pinecone index name for storing embeddings
        debug: Enable debug mode to return additional metadata
        include_category_in_doc_name: Include category name in document names

    Returns:
        dict: Contains system_prompt_menu, pinecone_namespace, and pinecone_index_name.
              When debug=True, also includes POS integration details.

    Raises:
        HTTPException: 400 for validation errors, 500 for processing errors
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
        menu_last_updated,
        selected_menus,
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_history_permission("account.read", authenticate_user)
    ),
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


@admin_router.post("/changes/{change_log_id}/revert")
async def revert_change_log(
    change_log_id: uuid.UUID,
    context: UserContext = Depends(
        require_history_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ChangeLogDetails:
    """
    Revert a change log by applying the old values to the resource.
    Creates a new change log entry for the revert action.
    """
    return await _history.revert_change_log(
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


@admin_router.post("/onboarding/generate_prompts", status_code=status.HTTP_200_OK)
async def generate_agent_prompts_api(
    request: GenerateAgentPromptsRequest,
    context: UserContext = Depends(authenticate_user),
) -> GenerateAgentPromptsResponse:
    """
    Generate agent prompts for a new account.
    """
    return await _onboarding.generate_agent_prompts_api(request, context)


@admin_router.post("/onboarding/build_menu", status_code=status.HTTP_200_OK)
async def build_menu_api(
    request: BuildMenuRequest,
    context: UserContext = Depends(authenticate_user),
) -> BuildMenuResponse:
    """
    Build menu data from a restaurant URL using Firecrawl.
    """
    return await _onboarding.build_menu_api(request, context)


@admin_router.post(
    "/onboarding/{project_id}/upload_menu", status_code=status.HTTP_202_ACCEPTED
)
async def upload_menu_api(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(
        ..., description="Menu image files to process (supports multiple files)"
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> MenuUploaderResponse:
    """
    Start menu upload processing from image file(s) using OpenAI API.

    Upload one or more menu images to extract structured menu data.
    The processing happens asynchronously in the background, and this endpoint
    returns immediately with a status response.

    Supports multiple file uploads - all files will be processed and combined into a single menu.
    The project's menu will be automatically updated once processing completes.

    Accepts common image formats (JPEG, PNG, etc.).

    Returns:
        - status: "processing"
        - message: Description of the operation
        - project_id: The project being updated
    """
    # Handle single file vs multiple files for the backend
    upload_files = files[0] if len(files) == 1 else files

    return await _onboarding.upload_menu_api(upload_files, context, project_id)


@admin_router.post("/onboarding/scrape_brand_from_url", status_code=status.HTTP_200_OK)
async def scrape_brand_from_url_api(
    request: ScrapeBrandFromUrlRequest,
) -> ScrapeBrandFromUrlResponse:
    """
    Scrape brand from a URL using Firecrawl.
    """
    return await _onboarding.scrape_brand_from_url(request)


@admin_router.post("/onboarding", status_code=status.HTTP_201_CREATED)
async def onboard(
    request: OnboardingRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> OnboardingResponse:
    """
    Onboard a new account with agents and projects in a single transaction.
    Phone numbers must be reserved separately using the phone number APIs.
    Returns the created project UUIDs for subsequent phone number reservation.
    """
    return await _onboarding.create_onboarding(request, context, session)


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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> ListAccountSubscriptionsResponse:
    """
    TO BE DEPRECATED! Use get_current_account_subscription in the future.
    Retrieves all active subscriptions for the given account.
    Scheduled subscriptions are sorted by start_date if there are multiple.
    """
    return _subscription.list_account_subscriptions(context, session, account_name)


@admin_router.get("/accounts/{account_name}/subscriptions/current")
def get_current_account_subscription(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> GetCurrentSubscriptionResponse:
    """
    Retrieves the current subscription for the account.
    """
    return _subscription.get_current_subscription(context, session, account_name)


@admin_router.get("/accounts/{account_name}/subscriptions/details")
def get_subscription_details(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
):
    """
    Get comprehensive subscription and billing details for the frontend.

    Returns detailed information including:
    - Current subscription and plan features
    - Usage metrics (calls used, overage)
    - Billing cycle and next billing date
    - Recent invoices with download links
    - Payment method information
    - Upgrade/downgrade options with 3 randomly selected featured benefits
    """
    return _subscription.get_subscription_details(context, session, account_name)


@admin_router.patch("/accounts/{account_name}/subscriptions/{external_id}")
def update_account_subscription(
    account_name: str,
    external_id: uuid.UUID,
    request: UpdateAccountSubscriptionRequest,
    force_update: bool = Query(
        False, description="Whether to allow updates on non-active subscriptions"
    ),
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> dict:
    """
    Cancels a subscription for the given account.

    This operation cannot be reverted unless they sign up again.
    """
    return _subscription.cancel_account_subscription(
        context, session, account_name, external_id
    )


@admin_router.post("/accounts/{account_name}/subscriptions/sync-stripe")
async def sync_stripe_subscriptions(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    """
    Sync subscription statuses with Stripe for an account.

    Fetches current status from Stripe API and updates local database
    if the status is out of sync. Returns a summary of synced subscriptions.
    """
    return await _subscription.sync_stripe_subscriptions(
        context, async_session, account_name
    )


@admin_router.post("/accounts/{account_name}/subscriptions/{external_id}/checkout")
def create_subscription_checkout_session(
    account_name: str,
    external_id: uuid.UUID,
    request: CreateCheckoutSessionRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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


@admin_router.get("/accounts/{account_name}/subscriptions/{external_id}/projects")
def list_project_subscriptions_by_subscription_external_id(
    account_name: str,
    external_id: uuid.UUID,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    db_session: Session = Depends(db.get_db),
):
    """List all project subscriptions for a given subscription external ID."""
    return _subscription.list_project_subscriptions_by_subscription_external_id(
        context, db_session, account_name, external_id
    )


@admin_router.put("/accounts/{account_name}/subscriptions/{external_id}/projects")
def create_project_subscription(
    account_name: str,
    external_id: uuid.UUID,
    request: CreateProjectSubscriptionRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    db_session: Session = Depends(db.get_db),
):
    """Remove a project subscription."""
    return _subscription.remove_project_subscription(
        context, db_session, account_name, external_id, project_id
    )


@admin_router.post(
    "/accounts/{account_name}/switch_plan", status_code=status.HTTP_200_OK
)
def switch_subscription_plan(
    account_name: str,
    request: SwitchPlanRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> SwitchPlanResponse:
    return _subscription.switch_subscription_plan(
        context=context,
        session=session,
        account_name=account_name,
        request=request,
    )


@admin_router.post(
    "/accounts/{account_name}/reset_current_subscription",
    status_code=status.HTTP_200_OK,
)
def unlink_subscription_from_account(
    account_name: str,
    force_unlink: bool = Query(False, description="Forces backend to unlink the sub"),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Unlink the current subscription from an account.
    Only allows unlinking if the subscription status is not active or pending.
    """
    return _subscription.unlink_subscription_from_account(
        context, session, account_name, force_unlink
    )


@admin_router.post("/accounts/{account_name}/stripe_customer")
def create_stripe_customer(
    account_name: str,
    request: CreateStripeCustomerRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> StripeCustomer:
    """
    Create a Stripe customer for an account.
    """
    return _subscription.create_stripe_customer(
        context,
        session,
        account_name,
        request.name,
        request.email,
    )


@admin_router.get("/accounts/{account_name}/stripe_customer")
def get_stripe_customer(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> StripeCustomer:
    """
    Get Stripe customer information for an account.
    """
    return _subscription.get_stripe_customer_info(context, session, account_name)


@admin_router.patch("/accounts/{account_name}/stripe_customer")
def update_stripe_customer(
    account_name: str,
    request: UpdateStripeCustomerRequest,
    context: UserContext = Depends(
        require_account_permission("account.write", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> StripeCustomer:
    """
    Update Stripe customer information for an account.
    """
    return _subscription.update_stripe_customer_info(
        context, session, account_name, request
    )


@admin_router.post("/accounts/{account_name}/credits", status_code=status.HTTP_200_OK)
@admin_router.post(
    "/accounts/{account_name}/stripe_customer/credits", status_code=status.HTTP_200_OK
)
def grant_account_credit(
    account_name: str,
    request: GrantAccountCreditRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> StripeCustomer:
    """
    Grant additional credit to the account. The amount must be in the smallest divisible
    unit like "cents" for USD.
    Positive value issues a credit for the user, and a negative value issues a debit for
    the user. For our use cases, this number is almost always positive!
    """
    return _subscription.grant_credit_for_account(
        context, session, account_name, request
    )


@admin_router.get("/accounts/{account_name}/credits", status_code=status.HTTP_200_OK)
def get_account_credit(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> GetAccountCreditResponse:
    return _subscription.get_credit_amount(context, session, account_name)


@admin_router.get(
    "/accounts/{account_name}/credits/grants", status_code=status.HTTP_200_OK
)
def list_account_credit_grants(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListAccountCreditGrantsResponse:
    return _subscription.list_account_credit_grants(
        context=context,
        session=session,
        account_name=account_name,
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


"""
---------- Google Maps Endpoints ----------
------------------------------------
"""


@admin_router.post("/google-maps/search", status_code=status.HTTP_200_OK)
async def search_places(
    request: GoogleMapsSearchRequest,
    context: UserContext = Depends(authenticate_user),
) -> GoogleMapsSearchResponse:
    """
    Search for places by name using Google Maps Places API.
    """
    authorize_admin(context)
    return await search_places_by_name(request)


"""
---------- Voice Config Endpoints ----------
--------------------------------------------
"""


@admin_router.patch("/voice_configs/batch", status_code=status.HTTP_200_OK)
async def batch_update_voice_configs(
    request: BatchUpdateVoiceConfigsRequest,
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> BatchUpdateVoiceConfigsResponse:
    """
    Update voice configs for multiple projects in batch.

    This endpoint allows you to update voice configurations for multiple projects at once.
    For each project, it will update the first voice config found. If no voice config exists
    for a project, it will be skipped with an error message.

    Only fields that are provided in the request will be updated - fields set to null
    or omitted will remain unchanged. This allows for partial updates of voice configs.

    The response includes detailed results for each voice config update attempt,
    including success/failure status and error messages for any failed updates.
    """
    return await _voice_config.batch_update_voice_configs(
        request, context, async_session
    )


@admin_router.get("/projects/{project_id}/voice_configs")
async def list_voice_configs(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> ListVoiceConfigsResponse:
    """
    Retrieve a list of voice configs for the specified project.
    """
    return await _voice_config.list_voice_configs_by_project(
        project_id, context, async_session
    )


@admin_router.get("/voice_configs/{voice_config_id}")
async def get_voice_config(
    voice_config_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> VoiceConfig:
    """
    Retrieve voice config details by voice config ID.
    """
    return await _voice_config.get_voice_config(voice_config_id, context, async_session)


@admin_router.put("/voice_configs", status_code=status.HTTP_201_CREATED)
async def create_voice_config(
    voice_config: CreateVoiceConfigRequest,
    context: UserContext = Depends(authenticate_user),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> VoiceConfig:
    """
    Create a new voice config for a project.
    """
    return await _voice_config.create_voice_config(voice_config, context, async_session)


@admin_router.patch("/voice_configs/{voice_config_id}")
async def update_voice_config(
    voice_config_id: uuid.UUID,
    voice_config: UpdateVoiceConfigRequest,
    context: UserContext = Depends(authenticate_user),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> VoiceConfig:
    """
    Update an existing voice config.
    """
    return await _voice_config.update_voice_config(
        voice_config_id, voice_config, context, async_session
    )


@admin_router.delete("/voice_configs/{voice_config_id}")
async def delete_voice_config(
    voice_config_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    async_session: AsyncSession = Depends(db.get_db_async),
):
    """
    Delete a voice config.
    """
    return await _voice_config.delete_voice_config(
        voice_config_id, context, async_session
    )


"""Square Integration Endpoints"""


@admin_router.get(
    "/accounts/{account_name}/integrations/{integration_id}/locations",
    status_code=status.HTTP_200_OK,
)
async def get_merchant_locations(
    account_name: str,
    integration_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
):
    """
    Get all locations for a merchant.
    """
    session = next(db.get_db())
    return _implementation.get_merchant_locations(session, account_name, integration_id)


"""
---------- Analytics Endpoints ----------
------------------------------------
"""


@admin_router.post("/slack/events")
async def slack_events(request: Request):
    """
    Handle Slack events (including URL verification and messages with 'daily').
    """
    from services import slack_service

    return await slack_service.handle_slack_events(request)


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
    group_by: Optional[list[str]] = Query(
        default=None,
        description="List of fields to group the report data by (e.g., ['account_id', 'project_id']).",
    ),
    project_ids: Optional[list[uuid.UUID]] = Query(
        default=None,
        description="Optional list of project IDs to filter the reports by.",
    ),
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> GetAllReportsResponse:
    """
    Retrieve unified analytics reports for this account.
    Data is filtered by the specified date range (default: last 7 days).
    """

    # Get unified reports using async session
    return await _analytics.get_accounts_reports(
        account_name,
        context,
        session,
        start_date,
        end_date,
        group_by=group_by if group_by else None,
        filter_by={"project_id": project_ids} if project_ids else None,
    )


@admin_router.get("/accounts/reports", status_code=status.HTTP_200_OK)
async def get_reports(
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
    group_by: Optional[list[str]] = Query(
        default=None,
        description="List of fields to group the report data by (e.g., ['account_id', 'project_id']).",
    ),
) -> GetAllReportsResponse:
    """
    Retrieve unified analytics reports for this account.
    Data is filtered by the specified date range (default: last 7 days).
    """

    # Get unified reports using async session
    return await _analytics.get_company_reports(
        context,
        session,
        start_date,
        end_date,
        group_by=group_by if group_by else None,
    )


"""
---------- Affiliate Endpoints ----------
------------------------------------------
"""


@admin_router.put("/affiliates", status_code=status.HTTP_201_CREATED)
async def create_affiliate(
    request: CreateAffiliateRequest,
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> AffiliateResponse:
    """
    Create a new affiliate in Rewardful and store locally.
    """
    return await _affiliate.create_affiliate(request, context, async_session)


@admin_router.get("/affiliates/{affiliate_id}")
async def get_affiliate(
    affiliate_id: uuid.UUID,
    expand: list[str] | None = Query(
        None, description="Fields to expand (campaign, links, coupon)"
    ),
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> AffiliateResponse:
    """
    Get affiliate by ID with data from Rewardful.
    """
    return await _affiliate.get_affiliate(affiliate_id, context, async_session, expand)


@admin_router.get("/affiliates")
async def list_affiliates(
    limit: int = Query(100, gt=0, le=100, description="Results per page (max 100)"),
    page: int = Query(1, gt=0, description="Page number"),
    campaign_id: str | None = Query(None, description="Filter by campaign ID"),
    expand: list[str] | None = Query(None, description="Fields to expand"),
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    """
    List affiliates from Rewardful with pagination.
    """
    return await _affiliate.list_affiliates(
        context, async_session, limit, page, campaign_id, expand
    )


@admin_router.patch("/affiliates/{affiliate_id}")
async def update_affiliate(
    affiliate_id: uuid.UUID,
    request: UpdateAffiliateRequest,
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> AffiliateResponse:
    """
    Update affiliate in Rewardful.
    """
    return await _affiliate.update_affiliate(
        affiliate_id, request, context, async_session
    )


@admin_router.delete("/affiliates/{affiliate_id}")
async def delete_affiliate(
    affiliate_id: uuid.UUID,
    context: UserContext = Depends(require_admin),
    async_session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    """
    Disable affiliate in Rewardful (sets state to "disabled").
    Note: Rewardful doesn't support actual deletion. The local record is kept for historical tracking.
    """
    return await _affiliate.delete_affiliate(affiliate_id, context, async_session)
