from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from requests import Session

from api.models.message import (
    AuthorType,
    ChannelPlatform,
    ChatRequestBody,
    Message,
    MessagingBroker,
    TextObject,
)
from api.routes.admin.auth import parse_admin_console_id_token
from api.routes.endpoints import endpoints
from db.session import get_db
from services.admin_service import (
    create_account_with_defaults,
    get_account,
    get_inbox_messages,
    get_knowledge_base,
)
from services.conversation_service import get_conversations_by_user
from services.message_service.message_service import (
    get_chat_response,
    get_messages_by_conversation,
)
from services.user_service import get_user
from utils.log import logger

######################################################
## Router for Admin Console
######################################################

"""
NOTE: 
- This code is a work in progress. The rest of the implementation will be done with a fast-follow.
- Only code with complete Python Docstrings are complete.
"""


admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])


@admin_router.post("/create_account")
def create_account(request: Request):
    """
    This endpoint is used to create an account in the database.
    Without the account in the database, the rest of the functionality will not work.

    Args:
        request (Request): The request object containing the headers and other request data.

    Returns:
        str: A JSON string indicating that the account has been created.
    """
    decrypted_id_token = parse_admin_console_id_token(
        request.headers.get("Authorization")
    )
    create_account_with_defaults(decrypted_id_token["custom:account_name"])
    return '{"message": "Account created"}'


@admin_router.get("/account")
def read_account(request: Request):
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/inbox")
def read_inbox(request: Request):
    try:
        _ = parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # 1. Check admin level
    # 2. Check organization
    # 3. Get inbox messages
    chat_data = get_inbox_messages()
    return JSONResponse(content=chat_data)


@admin_router.get("/chat")
def read_chat(request: Request, db: Session = Depends(get_db)):
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # Step 1: Get the account information from the ID Token
    account = get_account(db, account_name=decrypted_id_token["custom:account_name"])

    if account is None:
        raise ValueError("Account not found")

    # Step 2: Get the user from the account id and cognito:username (latter of which is stored in raw_config)
    user = get_user(
        db=db,
        account_id=str(account.id),
        channel_platform=ChannelPlatform.ADMIN_CONSOLE,
        channel_identifier=decrypted_id_token["cognito:username"],
        create_new_user=True,
    )

    if user is None:
        raise ValueError("User not found")

    logger.info(f"User: {str(user.id)}")
    logger.info(f"cognito:username: {decrypted_id_token['cognito:username']}")

    # Step 3: Get all conversations associated with the admin
    conversations = get_conversations_by_user(
        db=db, user_id=str(user.id), create_new_conversation=True
    )

    if not conversations:
        raise ValueError("No conversations found")

    """ 
    We assume that an Admin Console admin only has one conversation.
    If we want an admin to be able to create more than one conversation,
    then we will need to update the DB schema.
    """
    messages = get_messages_by_conversation(
        db=db, conversation_id=str(conversations[0].id)
    )

    logger.info(f"# Messages: {len(messages)}")
    return messages


@admin_router.post("/chat")
async def respond_to_message(request: Request, db: Session = Depends(get_db)):
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    body = await request.json()
    try:
        body_data = ChatRequestBody(**body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,  # Unprocessable Entity
            detail=f"Validation error: {e.errors()}\n\nInvalid request body: {body}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unexpected error: {e}\n\nInvalid request body: {body}",
        )

    # Steps largely the same as the GET endpoint
    account = get_account(db, account_name=decrypted_id_token["custom:account_name"])

    if account is None:
        raise ValueError("Account not found")

    user = get_user(
        db=db,
        account_id=str(account.id),
        channel_platform=ChannelPlatform.ADMIN_CONSOLE,
        channel_identifier=decrypted_id_token["cognito:username"],
        create_new_user=True,
    )

    if user is None:
        raise ValueError("User not found")

    message = Message(
        author_type=AuthorType.USER,
        sender_channel_identifier=decrypted_id_token["cognito:username"],
        recipient_channel_identifier=decrypted_id_token["custom:account_name"],
        channel_platform=ChannelPlatform.ADMIN_CONSOLE,
        messaging_broker=MessagingBroker.WEB,
        text=TextObject(body=body_data.message),
    )

    """ 
    get_chat_response uses the first conversation associated with the Message.
    Since we assume that an admin console will only ever have one conversation,
    get_chat_response stores the message and the response to the correct conversation.
    """
    chat_response = get_chat_response(db, message)
    return JSONResponse(content=jsonable_encoder(chat_response))


@admin_router.get("/knowledge")
def read_knowledge(request: Request):
    try:
        _ = parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    knowledge_base_json = get_knowledge_base()

    return knowledge_base_json


# This renders the "Users" page in the Admin Console.
# This page is used to view all the "consumers" for the "client" (organization).
#   Example: Max's Coffee's customers.
@admin_router.get("/users")
def read_users(request: Request):
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/campaigns")
def read_campaigns(request: Request):
    try:
        decrypted_id_token = parse_admin_console_id_token(
            request.headers.get("Authorization")
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)
