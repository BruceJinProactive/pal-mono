import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    CreateFeedbackResponse,
    GetFeedbackResponse,
)
from services.account_service import get_account
from services.admin_service import get_messages_by_conversation_id
from services.feedback_service import (
    create_feedback,
    get_feedback_by_id,
    update_feedback_by_id,
)

from . import _auth


def _get_account_from_id_token(request: Request, session: Session) -> db.Account:
    try:
        decrypted_id_token = _auth.parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # Get Account from ID Token
    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )

    if account is None:
        raise HTTPException(
            status_code=500,
            detail="Account not found.",
            headers={"Content-Type": "application/json"},
        )

    return account


def get_messages_with_feedback_by_conversation_id(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    """
    This endpoint retrieves all Messages within a specific Conversation, along with their associated Feedback.
    """
    account = _get_account_from_id_token(request, session)

    try:
        messages = get_messages_by_conversation_id(session, account.id, conversation_id)
    except ValueError:
        """
        Only say "Conversation not found" because if the Admin does not
        have access to the conversation, they should not know that
        the conversation exists in the first place.
        """
        raise HTTPException(
            status_code=400,
            detail="Conversation not found.",
            headers={"Content-Type": "application/json"},
        )

    return JSONResponse(content=jsonable_encoder(messages))


async def submit_feedback(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint is used to create feedback in the database.
    """
    _get_account_from_id_token(request, session)

    # Try to create Feedback object
    try:
        request_json = await request.json()
        feedback_request = CreateFeedbackRequest(**request_json)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback data: {str(e)}",
            headers={"Content-Type": "application/json"},
        )

    feedback = db.Feedback(
        message_id=feedback_request.message_id,
        author_identifier=feedback_request.author_identifier,
        reaction=feedback_request.reaction.value if feedback_request.reaction else None,
        tags=(
            [tag.value for tag in feedback_request.tags]
            if feedback_request.tags
            else None
        ),
        note=feedback_request.note,
    )

    # Pass Feedback object into service layer
    try:
        persisted_feedback = create_feedback(session, feedback)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    response = CreateFeedbackResponse(
        feedback_id=str(persisted_feedback.id),
        submitted_at=str(persisted_feedback.created_at.isoformat()),
    )

    return response


def retrieve_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    This endpoint is used to retrieve feedback by id from the database.
    """
    _get_account_from_id_token(request, session)

    # Validate feedback_id
    try:
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback UUID: {str(e)}",
            headers={"Content-Type": "application/json"},
        )

    # Get Feedback object from service layer
    try:
        persisted_feedback = get_feedback_by_id(session, feedback_uuid)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    if not persisted_feedback:
        raise HTTPException(
            status_code=404,
            detail="Feedback not found.",
            headers={"Content-Type": "application/json"},
        )

    feedback_response = GetFeedbackResponse(
        id=str(persisted_feedback.id),
        message_id=str(persisted_feedback.message_id),
        author_identifier=persisted_feedback.author_identifier,
        reaction=persisted_feedback.reaction,
        tags=persisted_feedback.tags,
        note=persisted_feedback.note,
        timestamp=str(persisted_feedback.updated_at.isoformat()),
    )

    return feedback_response


async def change_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    This endpoint is used to update feedback by id in the database.
    """
    _get_account_from_id_token(request, session)

    # Try to create Feedback object
    try:
        request_json = await request.json()
        feedback_request = CreateFeedbackRequest(**request_json)
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feedback data: {str(e)}",
            headers={"Content-Type": "application/json"},
        )

    feedback = db.Feedback(
        message_id=feedback_request.message_id,
        author_identifier=feedback_request.author_identifier,
        reaction=feedback_request.reaction.value if feedback_request.reaction else None,
        tags=(
            [tag.value for tag in feedback_request.tags]
            if feedback_request.tags
            else None
        ),
        note=feedback_request.note,
    )

    # Pass Feedback object into service layer
    try:
        persisted_feedback = update_feedback_by_id(session, feedback_uuid, feedback)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    response = CreateFeedbackResponse(
        feedback_id=str(persisted_feedback.id),
        submitted_at=str(persisted_feedback.updated_at.isoformat()),
    )

    return response
