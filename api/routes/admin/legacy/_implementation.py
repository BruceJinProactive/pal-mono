import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.admin import _auth
from api.schemas.admin.conversation import InboxResponse
from services.admin_service import (
    get_conversation_messages,
    get_inbox_conversations,
    get_knowledge_base,
    get_knowledge_base_by_document_id,
    update_knowledge_by_id,
)


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
