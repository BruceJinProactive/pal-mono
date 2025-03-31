import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.admin import _auth
from api.schemas.admin.conversation import InboxResponse
from api.schemas.admin.feedback import (
    CreateFeedbackRequest,
    CreateFeedbackResponse,
    Feedback,
)
from api.schemas.admin.message import GetMessageResponse
from services.admin_service import (
    get_conversation_ids_by_message_ids,
    get_conversation_messages,
    get_inbox_conversations,
    get_knowledge_base,
    get_knowledge_base_by_document_id,
    get_messages_by_conversation_id,
    update_knowledge_by_id,
)
from services.feedback_service import (
    create_feedback,
    delete_feedback_by_id,
    get_feedback_by_id,
    get_feedbacks,
    update_feedback_by_id,
)
from services.message_service import get_message_by_id


def get_conversation(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    account = _auth.get_account_from_id_token(request, session)
    try:
        messages = get_conversation_messages(session, account.id, conversation_id)
    except ValueError:
        """
        Only say "Conversation not found" because if the Admin does not
        have access to the conversation, they should not know that
        the conversation exists in the first place.
        """
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
            headers={"Content-Type": "application/json"},
        )
    return JSONResponse(content=jsonable_encoder(messages))


def get_document(
    request: Request, document_id: str, session: Session = Depends(db.get_db)
):
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    document = get_knowledge_base_by_document_id(session, account_name, document_id)
    return JSONResponse(content=jsonable_encoder(document))


def get_inbox(
    request: Request, page: int, page_size: int, session: Session = Depends(db.get_db)
) -> InboxResponse:
    account = _auth.get_account_from_id_token(request, session)
    total_conversations, inbox = get_inbox_conversations(
        session, account_id=account.id, page=page, page_size=page_size
    )
    total_pages = (total_conversations + page_size - 1) // page_size
    return InboxResponse(
        total_conversations=total_conversations, total_pages=total_pages, inbox=inbox
    )


def get_knowledge(request: Request, session: Session = Depends(db.get_db)):
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    knowledge_json = get_knowledge_base(session, account_name)
    return knowledge_json


def read_account(request: Request):
    decrypted_id_token = _auth.decrypt_id_token(request)
    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


async def update_document(
    request: Request, document_id: str, session: Session = Depends(db.get_db)
):
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    content_data = await request.json()
    content = content_data["content"]
    try:
        update_knowledge_by_id(
            session,
            account_name,
            document_id,
            content,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        ) from e

    return {"document_id": document_id}


async def change_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    _auth.get_account_from_id_token(request, session)

    # Try to create Feedback object
    try:
        request_json = await request.json()
        feedback_request = CreateFeedbackRequest(**request_json)
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    response = CreateFeedbackResponse(
        feedback_id=str(persisted_feedback.id),
        submitted_at=persisted_feedback.updated_at.isoformat(),
    )

    return response


def get_messages_with_feedback_by_conversation_id(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    account = _auth.get_account_from_id_token(request, session)

    try:
        messages = get_messages_by_conversation_id(session, account.id, conversation_id)
    except ValueError:
        """
        Only say "Conversation not found" because if the Admin does not
        have access to the conversation, they should not know that
        the conversation exists in the first place.
        """
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
            headers={"Content-Type": "application/json"},
        )

    # Cast to API response schema
    messages_response: list[GetMessageResponse] = [
        GetMessageResponse(
            id=str(message.id),
            timestamp=message.created_at.isoformat(),
            conversation_id=str(message.conversation_id),
            body=message.body,
            feedback=[
                Feedback(
                    id=str(f.id),
                    message_id=str(f.message_id),
                    message_content=getattr(
                        get_message_by_id(session, f.message_id), "body", {}
                    )
                    .get("text", {})
                    .get("body"),
                    author_identifier=f.author_identifier,
                    reaction=f.reaction,
                    tags=f.tags,
                    note=f.note,
                    timestamp=f.updated_at.isoformat(),
                )
                for f in message.feedback
            ],
        )
        for message in messages
    ]

    return messages_response


def remove_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    _auth.get_account_from_id_token(request, session)

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
        persisted_feedback = delete_feedback_by_id(session, feedback_uuid)
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

    response = CreateFeedbackResponse(
        feedback_id=str(persisted_feedback.id),
        submitted_at=persisted_feedback.created_at.isoformat(),
    )

    return response


def retrieve_all_feedbacks(request: Request, session: Session = Depends(db.get_db)):
    _auth.get_account_from_id_token(request, session)

    # Get Feedback objects from service layer
    try:
        feedbacks = get_feedbacks(session)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )
    if feedbacks:
        message_ids = [feedback.message_id for feedback in feedbacks]
        conversation_ids = get_conversation_ids_by_message_ids(session, message_ids)

        feedbacks_response = [
            {
                "feedback": Feedback(
                    id=str(feedback.id),
                    message_id=str(feedback.message_id),
                    message_content=getattr(
                        get_message_by_id(session, feedback.message_id), "body", {}
                    )
                    .get("text", {})
                    .get("body"),
                    author_identifier=feedback.author_identifier,
                    reaction=feedback.reaction,
                    tags=feedback.tags,
                    note=feedback.note,
                    timestamp=feedback.updated_at.isoformat(),
                ),
                "conversation_id": conversation_ids.get(feedback.message_id),
            }
            for feedback in feedbacks
        ]
    else:
        feedbacks_response = []

    return feedbacks_response


def retrieve_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    _auth.get_account_from_id_token(request, session)

    # Validate feedback_id
    try:
        feedback_uuid = uuid.UUID(feedback_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feedback UUID: {str(e)}",
            headers={"Content-Type": "application/json"},
        )

    # Get Feedback object from service layer
    try:
        persisted_feedback = get_feedback_by_id(session, feedback_uuid)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )
    if not persisted_feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found.",
            headers={"Content-Type": "application/json"},
        )

    feedback_response = Feedback(
        id=str(persisted_feedback.id),
        message_id=str(persisted_feedback.message_id),
        message_content=getattr(
            get_message_by_id(session, persisted_feedback.message_id), "body", {}
        )
        .get("text", {})
        .get("body"),
        author_identifier=persisted_feedback.author_identifier,
        reaction=persisted_feedback.reaction,
        tags=persisted_feedback.tags,
        note=persisted_feedback.note,
        timestamp=persisted_feedback.updated_at.isoformat(),
    )

    return feedback_response


async def submit_feedback(request: Request, session: Session = Depends(db.get_db)):
    _auth.get_account_from_id_token(request, session)

    # Try to create Feedback object
    try:
        request_json = await request.json()
        feedback_request = CreateFeedbackRequest(**request_json)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    response = CreateFeedbackResponse(
        feedback_id=str(persisted_feedback.id),
        submitted_at=persisted_feedback.created_at.isoformat(),
    )

    return response
