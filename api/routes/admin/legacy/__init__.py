import uuid

from fastapi import Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.admin import _feedback, admin_router
from api.schemas.admin.conversation import InboxResponse

from . import _implementation


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
