import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints

from . import _feedback, _implementation, _projects

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


@admin_router.get("/feedback", status_code=200)
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


@admin_router.post("/feedback", status_code=200)
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


@admin_router.get("/feedback/{feedback_id}", status_code=200)
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


@admin_router.post("/feedback/{feedback_id}", status_code=200)
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


@admin_router.get("/inbox")
def get_inbox(
    request: Request,
    page: int = Query(..., description="Current page number"),
    page_size: int = Query(..., description="Number of items per page"),
    session: Session = Depends(db.get_db),
):
    """
    Retrieve the inbox conversations for the account associated with the request.

    Args:
        request: The incoming HTTP request.
        session: The database session.

    Returns:
        JSONResponse: The inbox conversations.
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


@admin_router.delete("/instagram/deauthorize/{ig_user_id}", status_code=200)
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


@admin_router.get("/projects", status_code=200)
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


@admin_router.post("/projects/{project_id}/instagram/connect", status_code=200)
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


@admin_router.delete("/projects/{project_id}/instagram/connect", status_code=200)
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


@admin_router.get("/projects/{project_id}/instagram/status", status_code=200)
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


@admin_router.get("/projects/{project_id}/instagram/username", status_code=200)
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
