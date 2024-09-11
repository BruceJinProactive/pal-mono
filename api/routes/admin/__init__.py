import uuid

from fastapi import APIRouter, Depends, Request
from requests import Session

from . import _implementation
from api.routes.endpoints import endpoints
from db.session import get_db

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
def create_account(request: Request, db: Session = Depends(get_db)):
    """
    This endpoint is used to create an account in the database.
    Without the account in the database, the rest of the functionality will not work.

    Args:
        request (Request): The request object containing the headers and other request data.

    Returns:
        str: A JSON string indicating that the account has been created.
    """
    return _implementation.create_account(request, db)


@admin_router.get("/account")
def read_account(request: Request):
    return _implementation.read_account(request)


@admin_router.get("/inbox")
def read_inbox(request: Request, db: Session = Depends(get_db)):
    """
    This endpoint allows an Admin to retrieve a list of `ConversationPreview` objects.

    Args:
        request (Request): The request object containing the headers and other request data.
        db (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of ConversationPreviews.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account associated with the token is not found.
    """

    return _implementation.read_inbox(request, db)


@admin_router.get("/inbox/{conversation_id}")
def read_conversation(
    request: Request, conversation_id: uuid.UUID, db: Session = Depends(get_db)
):
    """
    This endpoint allows an Admin to retrieve all Messages within a specific Conversation.

    Args:
        request (Request): The request object containing the headers and other request data.
        conversation_id (uuid.UUID): The unique identifier of the Conversation requested, as a path param.
        db (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of messages in the specified conversation.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account, User, or Conversation is not found.
        HTTPException: If the requesting Admin does not have access to the Conversation.
    """
    return _implementation.read_conversation(request, conversation_id, db)


@admin_router.get("/chat")
def read_chat(request: Request, db: Session = Depends(get_db)):
    """
    This endpoint allows an Admin to retrieve all Messages within the Conversation within
    the Admin Console chat, which is assumed to be unique.

    Args:
        request (Request): The request object containing the headers and other request data.
        db (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded list of Messages.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the Account or User is not found.
    """
    return _implementation.read_chat(request, db)


@admin_router.post("/chat")
async def respond_to_message(request: Request, db: Session = Depends(get_db)):
    """
    This endpoint generates a response to a chat message in the Admin Console chat.
    It stores both the message received and the response in the database.

    Args:
        request (Request): The request object containing the headers and other request data.
        db (Session): The database connection.

    Returns:
        JSONResponse: A JSON-encoded Message.

    Raises:
        HTTPException: If the ID token is invalid or missing.
        HTTPException: If the request body is malformed.
        HTTPException: If the Account or User is not found.
    """
    return _implementation.respond_to_message(request, db)


@admin_router.get("/knowledge")
def read_knowledge(request: Request):
    return _implementation.read_knowledge(request)


# This renders the "Users" page in the Admin Console.
# This page is used to view all the "consumers" for the "client" (organization).
#   Example: ABC Coffee's customers.
@admin_router.get("/users")
def read_users(request: Request):
    return _implementation.read_users(request)


@admin_router.get("/campaigns")
def read_campaigns(request: Request):
    return _implementation.read_campaigns(request)


__all__ = [
    "create_account",
    "read_account",
    "read_inbox",
    "read_conversation",
    "read_chat",
    "respond_to_message",
    "read_knowledge",
    "read_users",
    "read_campaigns",
]
