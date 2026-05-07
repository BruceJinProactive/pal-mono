import uuid
from collections.abc import Callable
from typing import AsyncIterator

from openai.types.chat import ChatCompletionChunk
from pal_agents.input import RuntimeContext
from pal_agents.spec import Spec
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.chat.message import Message
from db.tables.types import Channel
from utils.otel import traced
from utils.request_context import RequestContext

from . import _implementation


def get_filler_message(message: Message) -> Message:
    return _implementation.get_filler_message(message)


@traced("Message Service Async Processing")
async def get_chat_response_async(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> list[Message]:
    """
    Processes an incoming message and generates a response from the appropriate agent.

    Args:
        session (Session): The database session.
        message (Message): The incoming message object.
        context_modifier: Optional callback to modify RuntimeContext after construction.
        spec_modifier: Optional callback to modify the pal-agents ``Spec`` after
            construction and before the agent runs. Used by eval drivers to
            force safety flags (e.g. ``toast.submit_orders=False``) regardless
            of what the project's DB config says. Production callers leave
            this ``None``.

    Returns:
        list[Message]: A list of message objects.

    Raises:
        ValueError: If any required information (account name, account, projects, user, agent ID) is not found.
        ValueError: If the response type from the agent is unexpected.
    """
    return await _implementation.get_chat_response_async(
        session,
        message,
        request_context,
        context_modifier=context_modifier,
        spec_modifier=spec_modifier,
    )


# Cannot trace iterator consumption here
async def get_chat_response_stream(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    call_id: str | None = None,
    room_name: str | None = None,
    participant_identity: str | None = None,
    sip_provider: str | None = None,
) -> AsyncIterator[ChatCompletionChunk]:
    """
     Get a stream of chat responses for a given message.

     This function retrieves a stream of chat responses from the agent for the provided message.
     It saves the request message to the database, retrieves the appropriate agent, and streams
     the responses from the agent.

     Args:
         session (AsyncSession): The asynchronous database session to use for the query.
         message (Message): The message object containing the details of the user's message.
         request_context (RequestContext): The request context containing metadata about the request.
         call_id (str | None): The voice call ID for voice calls. When provided, the message will
             be added to the existing conversation associated with this call_id.
         room_name (str | None): The LiveKit room name for LiveKit voice calls.
         participant_identity (str | None): The LiveKit participant identity for LiveKit voice calls.
         sip_provider (str | None): SIP provider: "pizzacloud", "twilio", or "snet".

     Returns:
        AsyncIterator[Message]: A stream of response messages from the agent.

    Raises:
        ValueError: If any required information (account name, account, projects, user, agent ID) is not found.
        ValueError: If the response type from the agent is unexpected.
    """
    return _implementation.get_chat_response_stream(
        session,
        message,
        request_context,
        call_id,
        room_name,
        participant_identity,
        sip_provider,
    )


def get_chat_response(session: Session, message: Message) -> Message:
    """
    Processes an incoming message and generates a response from the appropriate agent.

    Args:
        session (Session): The database session.
        message (Message): The incoming message object.

    Returns:
        Message: The response message object.

    Raises:
        ValueError: If any required information (account name, account, projects, user, agent ID) is not found.
        ValueError: If the response type from the agent is unexpected.
    """
    return _implementation.get_chat_response(session, message)


def get_message_by_id(session: Session, message_id: uuid.UUID) -> db.Message | None:
    """
    Retrieves a message by its unique identifier.

    Args:
        session (Session): The database session.
        message_id (uuid.UUID): The unique identifier of the message.

    Returns:
        db.Message | None: The message object associated with the unique identifier.
    """
    return _implementation.get_message_by_id(session, message_id)


def get_messages_by_ids(
    session: Session, message_ids: list[uuid.UUID]
) -> list[db.Message]:
    """
    Retrieves multiple messages by UUIDs.

    Args:
        session (Session): The database session.
        message_ids (list[uuid.UUID]): The unique identifiers of the messages.

    Returns:
        list[db.Message]: The messages retrieved
    """
    return _implementation.get_messages_by_ids(session, message_ids)


def get_messages_by_conversation(
    session: Session, conversation_id: uuid.UUID
) -> list[db.Message]:
    """
    Retrieves all messages for a given conversation.

    Args:
        session (Session): The database session.
        conversation_id (uuid.UUID): The unique identifier of the conversation.

    Returns:
        List[db.Message]: A list of Message objects associated with the conversation.
    """
    return _implementation.get_messages_by_conversation(session, conversation_id)


def get_conversations_by_user(
    session: Session, user_id: uuid.UUID, create_new_conversation: bool = False
) -> list[db.Conversation]:
    """
    Retrieves all conversations associated with a given user ID. Optionally creates a new conversation
    if no existing conversations are found and the 'create_new_conversation' flag is set to True.

    Args:
        session (Session): The database session.
        user_id (uuid.UUID): The unique identifier of the user.
        create_new_conversation (bool): Flag to determine if a new conversation should be created if none exist.

    Returns:
        List[db.Conversation]: A list of Conversation objects.
    """
    return _implementation.get_conversations_by_user(
        session, user_id, create_new_conversation
    )


def get_conversations_by_users(
    session: Session,
    page: int,
    page_size: int,
    user_ids: list[uuid.UUID],
) -> tuple[int, list[db.Conversation]]:
    """
    Retrieves conversations associated with a list of user IDs.

    Args:
        session (Session): The database session.
        user_ids (List[uuid.UUID]): List of user IDs to retrieve conversations for.

    Returns:
        tuple[int, List[db.Conversation]]: A tuple containing the total number of conversations and a list of Conversation objects.
    """
    return _implementation.get_conversations_by_users(
        session, page, page_size, user_ids
    )


def create_conversation(
    session: Session,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    channel: Channel | None = None,
) -> db.Conversation | None:
    """
    Creates a new conversation for the user, optionally tracking voice call usage for Stripe billing.

    Args:
        session (Session): The database session.
        user_id (uuid.UUID): The user id associated with the new conversation
        project_id (uuid.UUID | None): Optional project id - if provided, will track voice call usage for Stripe billing

    Returns:
        db.Conversation: A new conversation
    """
    return _implementation.create_conversation(session, user_id, project_id, channel)


@traced("Message Service Create Voice Call Conversation")
async def create_voice_call_conversation(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    message_body: dict,
    call_id: str,
) -> db.Message:
    """Create a new conversation + initial message for a voice call."""
    return await _implementation.create_voice_call_conversation(
        session, user_id, project_id, message_body, call_id
    )


__all__ = [
    "get_chat_response",
    "get_chat_response_async",
    "get_chat_response_stream",
    "get_message_by_id",
    "get_messages_by_ids",
    "get_messages_by_conversation",
    "get_conversations_by_user",
    "get_conversations_by_users",
    "create_conversation",
    "create_voice_call_conversation",
]
