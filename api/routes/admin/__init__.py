import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._utils import SortOrder, UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.account import (
    Account,
    AccountStatisticsResponse,
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
from api.schemas.admin.analytics import GetAllReportsResponse, GetReportResponse
from api.schemas.admin.conversation import (
    ListConversationMessagesResponse,
    ListUserSessionsResponse,
)
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    Feedback,
    FeedbackDetail,
    ListFeedbacksResponse,
    UpdateFeedbackRequest,
)
from api.schemas.admin.knowledge import ListKnowledgeFileResponse, ResourceType
from api.schemas.admin.onboarding import OnboardingRequest
from api.schemas.admin.project import (
    CreateProjectRequest,
    Project,
    ProjectSummary,
    UpdateProjectRequest,
)
from api.schemas.admin.user_management import (
    CreateUserRequest,
    ListUsersResponse,
    UserInfo,
)
from api.schemas.chat.message import Channel

from . import (
    _account,
    _agent,
    _analytics,
    _conversation,
    _feedback,
    _knowledge,
    _projects,
    _users,
)
from ._auth import authenticate_user, get_user_info
from ._onboarding import create_onboarding
from .legacy import legacy_router

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
admin_router.include_router(legacy_router)


@admin_router.get("/me")
def get_user(context: UserContext = Depends(authenticate_user)):
    """
    Retrieve information about the currently logged-in user.
    """
    return get_user_info(context)


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
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    Delete the account identified by name.
    """
    await _account.delete_account(account_name, context, session)


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
) -> list[ProjectSummary]:
    """
    Retrieve a list of projects associated with the given account name.
    """
    return await _projects.list_account_projects(account_name, context, session)


@admin_router.get("/accounts/{account_name}/reports", status_code=status.HTTP_200_OK)
def get_account_reports(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> GetAllReportsResponse:
    """
    Retrieve all available report data for this account.
    """
    return GetAllReportsResponse(reports=_analytics.get_all_reports(account_name))


@admin_router.get("/accounts/{account_name}/stat")
async def get_account_statistics(
    account_name: str,
    lookback: int = Query(
        0,
        description="Number of seconds to search back in time for stat, e.g. if 60, it will only return stat for sessions created in the last 60 seconds.",
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> AccountStatisticsResponse:
    """
    Return basic account statistics such as total unique users and active sessions.
    """
    return await _account.get_account_statistics(
        account_name, lookback, context, session
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


"""
---------- Conversation Endpoints ----------
--------------------------------------------
"""
DEFAULT_SESSION_AGE = 3600 * 24 * 365  # 365 days of history


@admin_router.get("/accounts/{account_name}/sessions")
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


@admin_router.get("/sessions/{session_id}/messages")
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
        session_id, page, page_size, sort_order, context, session
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


@admin_router.get("/projects")
async def list_projects(
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """
    List all projects associated with the account.
    """
    return await _projects.list_projects(context, session)


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


"""
---------- Insights Endpoints ----------
----------------------------------------
"""


@admin_router.get("/reports", status_code=status.HTTP_200_OK)
def get_report(
    request: Request,
    report_name: str = Query(..., description="Report Name"),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> GetReportResponse:
    """
    Retrieve report data for the specified report name.
    """
    report_data = _analytics.get_report(request, report_name, session) or {}

    return GetReportResponse(report_data=report_data)


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
    await create_onboarding(request, context, session)
