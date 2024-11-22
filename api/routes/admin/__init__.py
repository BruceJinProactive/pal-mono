import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.schemas.chat.message import AuthorType, Channel, Message, TextObject
from services.account_service import create_account_with_defaults, get_account
from services.admin_service import (
    get_brandings,
    get_conversation_messages,
    get_inbox_conversations,
    get_instagram_connected,
    remove_instagram_access_token,
    set_instagram_access_token,
)
from services.message_service import (
    get_chat_response,
    get_conversations_by_user,
    get_messages_by_conversation,
)
from services.user_service import get_user_by_channel_identifier

from . import _auth, _implementation, _utils

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
def create_account(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint is used to create an account in the database.
    Without the account in the database, the rest of the functionality will not work.

    Args:
        request (Request): The request object containing the headers and other request data.
        session (Session): The database connection.

    Returns:
        str: A JSON string indicating that the account has been created.
    """
    decrypted_id_token = _auth.parse_admin_console_id_token(
        request.headers.get("Authorization")
    )
    create_account_with_defaults(session, decrypted_id_token["custom:account_name"])
    return '{"message": "Account created"}'


@admin_router.get("/account")
def read_account(request: Request):
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
    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/inbox")
def read_inbox(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint allows an Admin to retrieve a list of `ConversationPreview` objects.

    Args:
        request (Request): The request object containing the headers and other request data.
        session (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of ConversationPreviews.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account associated with the token is not found.
    """

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

    inbox = get_inbox_conversations(session, account_id=account.id)

    return JSONResponse(content=jsonable_encoder(inbox))


@admin_router.get("/conversations/{conversation_id}/messages")
def get_messages_with_feedback_by_conversation_id(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    return _implementation.get_messages_with_feedback_by_conversation_id(
        request, conversation_id, session
    )


@admin_router.get("/inbox/{conversation_id}")
def read_conversation(
    request: Request, conversation_id: uuid.UUID, session: Session = Depends(db.get_db)
):
    """
    This endpoint allows an Admin to retrieve all Messages within a specific Conversation.

    Args:
        request (Request): The request object containing the headers and other request data.
        conversation_id (uuid.UUID): The unique identifier of the Conversation requested, as a path param.
        session (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of messages in the specified conversation.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account, User, or Conversation is not found.
        HTTPException: If the requesting Admin does not have access to the Conversation.
    """
    # Validate ID Token
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


@admin_router.get("/chat")
def read_chat(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint allows an Admin to retrieve all Messages within the Conversation within
    the Admin Console chat, which is assumed to be unique.

    Args:
        request (Request): The request object containing the headers and other request data.
        session (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of Messages.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account or User is not found.
    """
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

    # Step 1: Get the account information from the ID Token
    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )

    if account is None:
        raise HTTPException(
            status_code=500,
            detail="Account not found.",
            headers={"Content-Type": "application/json"},
        )

    # Step 2: Get the user from the account id and cognito:username (latter of which is stored in raw_config)
    user = get_user_by_channel_identifier(
        session=session,
        account_id=account.id,
        channel_identifier=f"{Channel.API}:{decrypted_id_token['cognito:username']}",
        create_new_user=True,
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
            headers={"Content-Type": "application/json"},
        )

    # Step 3: Get all conversations associated with the admin
    conversations = get_conversations_by_user(
        session=session, user_id=user.id, create_new_conversation=True
    )

    # Skip the rest of the steps if there are no conversations
    # Send an empty list of messages
    if not conversations or conversations[0] is None:
        return JSONResponse(content=jsonable_encoder([]))

    """
    We assume that an Admin Console admin only has one conversation.
    If we want an admin to be able to create more than one conversation,
    then we will need to update the DB schema.
    """
    messages = get_messages_by_conversation(
        session=session, conversation_id=conversations[0].id
    )

    return JSONResponse(content=jsonable_encoder(messages))


@admin_router.post("/chat")
async def respond_to_message(request: Request, session: Session = Depends(db.get_db)):
    """
    Endpoint to handle chat messages from the Admin Console.

    This endpoint processes incoming chat messages, generates a response, and
    stores both the received message and the generated response in the database.

    Args:
        request (Request): The incoming request containing headers and a JSON
            body with the chat message, e.g., {'message': 'test'}.
        session (Session): The database session for storing messages and responses.

    Returns:
        JSONResponse: A JSON-encoded response containing the chat message and the generated reply.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the request body is malformed.
        HTTPException: If the Account or User is not found.
        HTTPException: If the 'message' field is missing or not a string.
    """
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

    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )

    if account is None:
        raise HTTPException(status_code=500, detail="Account not found")

    body_message = await _utils.retrieve_body_message(request)

    # Steps largely the same as the GET endpoint

    user = get_user_by_channel_identifier(
        session=session,
        account_id=account.id,
        channel_identifier=f"{Channel.API}:{decrypted_id_token['cognito:username']}",
        create_new_user=True,
    )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier=decrypted_id_token["cognito:username"],
        recipient_identifier=decrypted_id_token["custom:account_name"],
        channel=Channel.API,
        text=TextObject(body=body_message),
    )

    """
    get_chat_response uses the first conversation associated with the Message.
    Since we assume that an admin console will only ever have one conversation,
    get_chat_response stores the message and the response to the correct conversation.
    """
    chat_response = get_chat_response(session, message)
    return JSONResponse(content=jsonable_encoder(chat_response))


@admin_router.get("/brandings")
def read_brandings(request: Request, session: Session = Depends(db.get_db)):
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

    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )
    if account is None:
        raise HTTPException(status_code=500, detail="Account not found")

    account_name = account.name
    """
    get_brandings returns a list of JSON object that represents the brandings.
    """
    branding_jsons = get_brandings(session, account_name)
    return branding_jsons


# This renders the "Users" page in the Admin Console.
# This page is used to view all the "consumers" for the "client" (organization).
#   Example: ABC Coffee's customers.
@admin_router.get("/users")
def read_users(request: Request):
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

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.get("/campaigns")
def read_campaigns(request: Request):
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

    json_compatible_item_data = jsonable_encoder(decrypted_id_token)
    return JSONResponse(content=json_compatible_item_data)


@admin_router.post("/feedback", status_code=200)
async def submit_feedback(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint is used to create feedback in the database.
    """
    return await _implementation.submit_feedback(request, session)


@admin_router.get("/feedback/{feedback_id}", status_code=200)
def retrieve_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    return _implementation.retrieve_feedback_by_id(feedback_id, request, session)


@admin_router.post("/feedback/{feedback_id}", status_code=200)
async def change_feedback_by_id(
    feedback_id: str, request: Request, session: Session = Depends(db.get_db)
):
    return await _implementation.change_feedback_by_id(feedback_id, request, session)


@admin_router.get("/projects", status_code=200)
async def read_projects(request: Request, session: Session = Depends(db.get_db)):
    """
    This endpoint is used to retrieve all projects for an account.
    """
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

    account = get_account(
        session, account_name=decrypted_id_token["custom:account_name"]
    )
    if account is None:
        raise HTTPException(status_code=500, detail="Account not found")

    return JSONResponse(jsonable_encoder(account.projects))


@admin_router.get("/projects/{project_id}/instagram/status", status_code=200)
async def get_project_instagram_connected(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    This endpoint is used to check if an Instagram account is connected to the admin console.
    """
    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        connected = get_instagram_connected(session, project_uuid)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"connected": connected}


@admin_router.post("/projects/{project_id}/instagram/connect/", status_code=200)
async def connect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    This endpoint is used to connect an Instagram account.
    """

    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    ig_access_token = request.headers.get("Access-Token", "")
    if not ig_access_token:
        raise HTTPException(
            status_code=400,
            detail="No IG access token provided",
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        set_instagram_access_token(session, project_uuid, ig_access_token)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account connected"}


@admin_router.delete("/projects/{project_id}/instagram/connect", status_code=200)
async def disconnect_instagram(
    project_id: str, request: Request, session: Session = Depends(db.get_db)
):
    """
    This endpoint is used to disconnect an Instagram account.
    """

    try:
        _auth.parse_admin_console_id_token(request.headers.get("Authorization"))
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        remove_instagram_access_token(session, project_uuid)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=500,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account disconnected"}
