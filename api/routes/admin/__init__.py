import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

import db
from api.routes.admin._utils import UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.account import (
    Account,
    CreateAccountRequest,
    ListAccountsResponse,
    UpdateAccountRequest,
)
from api.schemas.admin.agent import Agent, CreateAgentRequest, UpdateAgentRequest
from api.schemas.admin.analytics import GetReportResponse
from api.schemas.admin.conversation import (
    ListConversationMessagesResponse,
    ListConversationsResponse,
)
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    Feedback,
    FeedbackDetail,
    ListFeedbacksResponse,
    UpdateFeedbackRequest,
)
from api.schemas.admin.project import (
    CreateProjectRequest,
    Project,
    UpdateProjectRequest,
)

from . import _account, _agent, _analytics, _conversation, _feedback, _projects
from ._auth import authenticate_user, get_user_info
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
) -> ListAccountsResponse:
    """
    Retrieve a list of accounts that are associated with the current user.
    """
    return _account.list_accounts(context, session)


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


"""
---------- Conversation Endpoints ----------
--------------------------------------------
"""


@admin_router.get("/accounts/{account_name}/conversations")
async def list_account_conversations(
    account_name: str,
    page: int = Query(..., description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        ..., description="Size of each page, cannot be less than 1", gt=0
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListConversationsResponse:
    """
    Retrieve the list of conversations for a given account. Returned conversations
    are sorted by the timestamp of the last message in reverse chronological order.
    """
    return await _conversation.list_account_conversations(
        account_name, page, page_size, context, session
    )


@admin_router.get("/conversations/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: uuid.UUID,
    page: int = Query(..., description="Current page, first page starts at 1", gt=0),
    page_size: int = Query(
        ..., description="Size of each page, cannot be less than 1", gt=0
    ),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListConversationMessagesResponse:
    """
    Returns the detailed conversation messages for the given id. Messages are sorted
    in chronological order.
    """
    return await _conversation.list_conversation_messages(
        conversation_id, page, page_size, context, session
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
