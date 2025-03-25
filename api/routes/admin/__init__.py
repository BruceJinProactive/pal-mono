import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.routes.endpoints import endpoints
from api.schemas.admin.account import Account, ListAccountsResponse
from api.schemas.admin.agent import Agent
from api.schemas.admin.analytics import GetReportResponse
from api.schemas.admin.conversation import InboxResponse
from api.schemas.admin.project import Project

from . import _account, _agent, _analytics, _feedback, _implementation, _projects

"""
######################################################
# Guide for the Admin APIs
######################################################

The API routes for the Admin Console are organized in alphabetical order for
better readability and maintainability.

The implementation is divided into separate modules based on the functionality.

Submodules are to organized in function name alphabetical order unless
otherwise specified.
"""

admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])


@admin_router.get("/me")
def get_user(request: Request, context: UserContext = Depends(authenticate_user)):
    """
    Retrieves information about the currently logged-in user.
    Args:
        request: The incoming HTTP request
        context: The authenticated user's context

    Returns:
        User: Information for the user in the current session.
    """
    return _implementation.get_user_info(context)


@admin_router.get("/account")
def read_account(request: Request):
    """
    Retrieve the account information from the decrypted ID token.

    Args:
        request: The incoming HTTP request.

    Returns:
        JSONResponse: The account information.
    """
    return _implementation.read_account(request)


@admin_router.get("/accounts")
def get_accounts(
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListAccountsResponse:
    """
    Retrieves a list of accounts that are associated with the current user.

    Args:
        request: The incoming HTTP request.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        ListAccountsResponse: The list of accounts.
    """
    return _account.list_accounts(context, session)


@admin_router.get("/agents/{agent_id}")
def get_agent(
    request: Request,
    agent_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Retrieves the agent configuration for the agent_id.

    Args:
        request: The incoming HTTP request.
        agent_id: UUID of the agent.
        context: The user context of this request.
        session: The database session.

    Returns:
        Agent: The agent configuration.
    """
    return _agent.get_agent(agent_id, context, session)


@admin_router.get("/projects/{project_id}")
def get_project(
    request: Request,
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Fetch detailed information about a specific project by its uuid.

    Args:
        request: The incoming HTTP request.
        project_id: UUID of the project.
        context: The user context of this request.
        session: The database session.

    Returns:
        Project: The project configuration.
    """
    return _projects.get_project(project_id, context, session)


@admin_router.put("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """
    Create a new account based on the provided request data.

    Args:
        request: The incoming HTTP request that contains the account data.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Account: The created account information.
    """
    return await _account.create_account(request, session)


@admin_router.patch("/accounts/{account_name}")
async def update_account(
    request: Request,
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """
    Update the account based on the provided request data.

    Args:
        request: The incoming HTTP request that contains the account data.
        account_name: The name of the account to update.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Account: The updated account information.
    """
    return await _account.update_account(request, account_name, session)


@admin_router.put("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Creates a new agent based on the provided request data. An agent must
    have a name and a valid account associated with it.

    Args:
        request: The incoming HTTP request that contains the agent data.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Agent: The created agent information.
    """
    return await _agent.create_agent(request, session)


@admin_router.patch("/agents/{agent_id}")
async def update_agent(
    request: Request,
    agent_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Agent:
    """
    Updates the agent config for the given agent_id. Note that the account
    associated with the agent cannot be modified once created.

    Args:
        request: The incoming HTTP request that contains the agent data.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Agent: The updated agent information.
    """
    return await _agent.update_agent(request, agent_id, session)


@admin_router.put("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    request: Request,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Create a new project based on the provided request data. A project must
    have a name and a valid account associated with it.

    Args:
        request: The incoming HTTP request that contains the project data.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Project: The created project information.
    """
    return await _projects.create_project(request, session)


@admin_router.patch("/projects/{project_id}")
async def update_project(
    request: Request,
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    """
    Update a project based on the provided request data. Project's account can
    not be updated once created.

    Args:
        request: The incoming HTTP request that contains the project data.
        project_id: UUID of the project to update.
        context: The authenticated user's context.
        session: The database session.

    Returns:
        Project: The updated project information.
    """
    return await _projects.update_project(request, project_id, session)


@admin_router.get("/agent_config")
def get_agent_config(
    request: Request, session: Session = Depends(db.get_db)
) -> JSONResponse:
    """
    Retrieve the agent configuration for the account associated with the request.

    Args:
        request: The incoming HTTP request.
        session: The database session.

    Returns:
        JSONResponse: The agent configuration.
    """
    return _implementation.get_agent_config(request, session)


@admin_router.get("/brand")
def get_brand(request: Request, session: Session = Depends(db.get_db)):
    """
    Retrieve the branding information for the account associated with the request.

    Args:
        request: The incoming HTTP request.
        session: The database session.

    Returns:
        list: The branding information.
    """
    return _implementation.get_brand(request, session)


@admin_router.post("/brand")
async def upsert_brand(request: Request, session: Session = Depends(db.get_db)):
    """
    Upserts brand information for an account.

    This endpoint retrieves the 'brandKey' and 'brandValue' fields from the request body,
    updates the agent's branding configuration, and saves it to the database.

    Args:
        request (Request): The FastAPI request object containing the JSON body with branding information.
        session (Session): The database session dependency.

    Returns:
        dict: The updated agent raw configuration.

    Raises:
        HTTPException: If the authorization token is invalid, the account or agent is not found,
                       or if there is an error in processing the request body.
    """
    return await _implementation.upsert_brand(request, session)


@admin_router.get("/conversations/{conversation_id}/messages")
def get_messages_with_feedback_by_conversation_id(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    """
    Retrieve all messages within a specific conversation along with their associated feedback.

    Args:
        request (Request): The HTTP request object.
        conversation_id (uuid.UUID): The UUID of the conversation.
        session (Session): The database session.

    Returns:
        list[GetMessageResponse]: A list of messages with their associated feedback.
    """
    return _feedback.get_messages_with_feedback_by_conversation_id(
        request, conversation_id, session
    )


@admin_router.get("/feedback", status_code=status.HTTP_200_OK)
def retrieve_all_feedbacks(request: Request, session: Session = Depends(db.get_db)):
    """
    Retrieve all feedback from the database.

    Args:
        request (Request): The HTTP request object.
        session (Session): The database session.

    Returns:
        list[Feedback]: A list of feedback objects.
    """
    return _feedback.retrieve_all_feedbacks(request, session)


@admin_router.post("/feedback", status_code=status.HTTP_200_OK)
async def submit_feedback(request: Request, session: Session = Depends(db.get_db)):
    """
    Create feedback in the database.

    Args:
        request (Request): The HTTP request object.
        session (Session): The database session.

    Returns:
        CreateFeedbackResponse: The response containing the feedback ID and submission timestamp.
    """
    return await _feedback.submit_feedback(request, session)


@admin_router.get("/feedback/{feedback_id}", status_code=status.HTTP_200_OK)
def retrieve_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Retrieve feedback by ID from the database.

    Args:
        feedback_id (str): The ID of the feedback.
        request (Request): The HTTP request object.
        session (Session): The database session.

    Returns:
        Feedback: The feedback object.
    """
    return _feedback.retrieve_feedback_by_id(feedback_id, request, session)


@admin_router.post("/feedback/{feedback_id}", status_code=status.HTTP_200_OK)
async def change_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Update feedback by ID in the database.

    Args:
        feedback_id (str): The ID of the feedback.
        request (Request): The HTTP request object.
        session (Session): The database session.

    Returns:
        CreateFeedbackResponse: The response containing the feedback ID and update timestamp.
    """
    return await _feedback.change_feedback_by_id(feedback_id, request, session)


@admin_router.delete("/feedback/{feedback_id}", status_code=status.HTTP_200_OK)
async def delete_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Delete feedback by ID from the database

    Args:
        feedback_id (str): The ID of the feedback.
        request (Request): The HTTP request object.
        session (Session): The database session.

    Returns:
        CreateFeedbackResponse: The response containing the feedback ID and update timestamp.
    """
    return _feedback.remove_feedback_by_id(feedback_id, request, session)


@admin_router.get("/inbox")
def get_inbox(
    request: Request,
    page: int = Query(..., description="Current page number"),
    page_size: int = Query(..., description="Number of items per page"),
    session: Session = Depends(db.get_db),
) -> InboxResponse:
    """
    Retrieve the inbox conversations for the account associated with the request.

    Args:
        request: The incoming HTTP request.
        page: The current page number.
        page_size: The number of items per page.
        session: The database session.

    Returns:
        InboxResponse: The total number of pages and the paginated list of conversations.
    """
    return _implementation.get_inbox(request, page, page_size, session)


@admin_router.get("/inbox/{conversation_id}")
def get_conversation(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    """
    Retrieve the messages for a specific conversation.

    Args:
        request: The incoming HTTP request.
        conversation_id: The ID of the conversation.
        session: The database session.

    Returns:
        JSONResponse: The messages in the conversation.

    Raises:
        HTTPException: If the conversation is not found or the account does not have access.
    """
    return _implementation.get_conversation(request, conversation_id, session)


@admin_router.delete(
    "/instagram/deauthorize/{ig_user_id}", status_code=status.HTTP_200_OK
)
async def handle_instagram_deauthorization(
    ig_user_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Handle Instagram deauthorization request.

    Args:
        ig_user_id (str): The Instagram user ID.
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        dict: A message indicating the Instagram account is deauthorized.
    """
    return await _projects.handle_instagram_deauthorization(
        ig_user_id, request, session
    )


@admin_router.get("/knowledge")
def get_knowledge(request: Request, session: Session = Depends(db.get_db)):
    """
    Retrieve the knowledge base for the account associated with the request.

    Args:
        request: The incoming HTTP request.
        session: The database session.

    Returns:
        JSONResponse: The knowledge base.
    """
    return _implementation.get_knowledge(request, session)


@admin_router.get("/knowledge/{document_id}")
def get_document(
    document_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Retrieve a document by its ID.

    Args:
        document_id: The ID of the document.
        request: The incoming HTTP request.
        session: The database session.

    Returns:
        JSONResponse: The document.
    """
    return _implementation.get_document(request, document_id, session)


@admin_router.post("/knowledge/{document_id}")
async def update_document(
    document_id: str, request: Request, session: Session = Depends(db.get_db)
):
    return await _implementation.update_document(request, document_id, session)


@admin_router.get("/projects", status_code=status.HTTP_200_OK)
async def read_projects(request: Request, session: Session = Depends(db.get_db)):
    """
    Read projects associated with the account.

    Args:
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        JSONResponse: A JSON response containing the projects.
    """
    return await _projects.read_projects(request, session)


@admin_router.post(
    "/projects/{project_id}/instagram/connect", status_code=status.HTTP_200_OK
)
async def connect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Connect an Instagram account to a project.

    Args:
        project_id (str): The ID of the project.
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        dict: A message indicating the Instagram account is connected.
    """
    return await _projects.connect_instagram(project_id, request, session)


@admin_router.delete(
    "/projects/{project_id}/instagram/connect", status_code=status.HTTP_200_OK
)
async def disconnect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Disconnect an Instagram account from a project.

    Args:
        project_id (str): The ID of the project.
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        dict: A message indicating the Instagram account is disconnected.
    """
    return await _projects.disconnect_instagram(project_id, request, session)


@admin_router.get(
    "/projects/{project_id}/instagram/status", status_code=status.HTTP_200_OK
)
async def get_project_instagram_connected(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Check if an Instagram account is connected to a project.

    Args:
        project_id (str): The ID of the project.
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        dict: A boolean indicating if the Instagram account is connected.
    """
    return await _projects.get_project_instagram_connected(project_id, request, session)


@admin_router.get(
    "/projects/{project_id}/instagram/username", status_code=status.HTTP_200_OK
)
async def get_project_instagram_username(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    Get the username of the Instagram account connected to a project.

    Args:
        project_id (str): The ID of the project.
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        dict: The username of the connected Instagram account.
    """
    return _projects.get_project_instagram_username(project_id, request, session)


@admin_router.get("/reports", status_code=status.HTTP_200_OK)
def get_report(
    request: Request,
    report_name: str = Query(..., description="Report Name"),
    session: Session = Depends(db.get_db),
) -> GetReportResponse:
    """
    Retrieve report data for the specified report name.

    Args:
        request (Request): The request object containing headers.
        session (Session): The database session.

    Returns:
        GetReportResponse: The response object containing the report data.
    """
    report_data = _analytics.get_report(request, report_name, session) or {}

    return GetReportResponse(report_data=report_data)
