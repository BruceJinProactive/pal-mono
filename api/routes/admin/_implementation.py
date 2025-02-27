import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from services.admin_service import get_brand as get_brand_from_db
from services.admin_service import (
    get_conversation_messages,
    get_inbox_conversations,
    get_knowledge_base,
    get_knowledge_base_by_document_id,
    update_knowledge_by_id,
)
from services.agent_service import update_agent_config

from . import _auth, _utils

"""
######################################################
# Guide for Admin API implementation
######################################################

- Keep all functions in alphabetical order.
- Use `Depends` to inject the database session.
- Use type hints for all arguments and the return value.
- Feel free to decouple specific namespaces to separate modules (i.e. `_projects`).
"""


def get_agent_config(
    request: Request, session: Session = Depends(db.get_db)
) -> JSONResponse:
    account = _auth.get_account_from_id_token(request, session)
    return JSONResponse(account.agents[0].raw_config)


def get_brand(request: Request, session: Session = Depends(db.get_db)):
    account = _auth.get_account_from_id_token(request, session)
    account_name = account.name
    branding_jsons = get_brand_from_db(session, account_name)
    return branding_jsons


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
            status_code=404,
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
):
    account = _auth.get_account_from_id_token(request, session)
    inbox = get_inbox_conversations(
        session, account_id=account.id, page=page, page_size=page_size
    )
    return JSONResponse(content=jsonable_encoder(inbox))


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
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        ) from e

    return {"document_id": document_id}


async def upsert_brand(request: Request, session: Session = Depends(db.get_db)):
    account = _auth.get_account_from_id_token(request, session)
    agent_raw_config = account.agents[0].raw_config
    request_brand_key_value = await _utils.retrieve_body_brand(request)

    if "brand" not in agent_raw_config:
        agent_raw_config["brand"] = {}
    agent_raw_config["brand"][request_brand_key_value[0]] = request_brand_key_value[1]

    try:
        update_agent_config(
            session,
            agent_id=account.agents[0].id,
            config=agent_raw_config,
        )
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail="An error occurred while updating the brand. Please try again.",
            headers={"Content-Type": "application/json"},
        )

    return agent_raw_config
