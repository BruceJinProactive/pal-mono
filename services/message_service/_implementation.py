import random
import time
import uuid
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import Agent
from agent.input_output import Output
from api.schemas.admin.analytics import Event as AnalyticsEvent
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Channel,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from services import agent_service, analytics_service, project_service, user_service
from utils.log import logger

from . import _utils


def get_filler_message(message: Message) -> Message:
    # Collection of filler phrases for voice responses
    FILLER_PHRASES = [
        "Working on it.",
        "Bear with me.",
        "One brief moment.",
        "Brief moment.",
        "Working on your request.",
        "Just a short wait.",
    ]
    # Randomly select a filler phrase
    filler_content = random.choice(FILLER_PHRASES)
    filler_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        text=TextObject(body=filler_content),
        metadata=message.metadata,
    )

    return filler_message


async def get_chat_response_async(
    session: AsyncSession, message: Message
) -> list[Message]:
    logger.info(f"get_chat_response_async received message: {message}")
    user = None
    extras = {}
    metadata = {}
    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    start_time = time.time()  # Start time for profiling latency
    try:
        logger.info(f"Step 1: Initialization - {time.time() - start_time:.4f}s")

        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        logger.info(f"Step 2: Retrieved project - {time.time() - start_time:.4f}s")

        metadata["project_name"] = project.name

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )

        if user is None:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)

            # Get opt-in message and append to list of messages if applicable
            if is_new_sms_user:
                opt_in_message = build_opt_in_message(message, metadata, extras)
                if opt_in_message:
                    if user:
                        # Save the opt-in message to the database
                        await message_repo.create_message(
                            user_id=user.id, message_body=opt_in_message.to_dict()
                        )

                    response_messages.append(opt_in_message)

        logger.info(
            f"Step 3: Retrieved or created user - {time.time() - start_time:.4f}s"
        )

        # Ensure user is fully loaded before accessing attributes
        await session.refresh(user)

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        await session.refresh(project, attribute_names=["account"])
        account_name = project.account.name
        is_testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )

        event_properties = {
            "account_name": account_name,
            "channel": message.channel.value,
            "conversation_id": str(request_message.conversation_id),
            "testing": is_testing,
        }

        analytics_service.track_event(
            user_id=str(user.id),
            event_name=AnalyticsEvent.USER_MESSAGE,
            event_properties=event_properties,
        )

        if not request_message:
            raise ValueError("Failed to create request message")
        conversation_id = request_message.conversation_id

        logger.info(f"Step 4: Saved request message - {time.time() - start_time:.4f}s")

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        logger.info(
            f"User channel identifier: {message.channel.value}:{message.sender_identifier}"
        )

        # Construct config
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=conversation_id,
            stream=False,
        )
        logger.info(f"Agent config: {config}")
        agent = Agent(config=config)
        logger.info(f"Step 5: Retrieved agent - {time.time() - start_time:.4f}s")

        # Get Input
        input = _utils.get_agent_input_from_message(message=message)
        logger.info(f"Input: {input}")

        # Get Output
        output: Output = await agent.arun(input)  # type: ignore # Temporarily disble specific pyright errors since Datadog annotations are not fully compatible with pyright yet.
        logger.info(
            f"Step 6: Agent response received - {time.time() - start_time:.4f}s"
        )
        logger.info(f"Output: {output}")

        # Check if output.content contains a link and create additional SMS response if message.channel is VOICE
        new_flow_response_messages = _utils.get_messages_from_agent_output(
            output=output, input_message=message, project_name=project.name
        )

        for message in new_flow_response_messages:
            # Save response message to database
            await message_repo.create_message(
                user_id=user.id, message_body=message.to_dict()
            )

        # Track only one event (for example, using the first message):
        if new_flow_response_messages:
            first_msg = new_flow_response_messages[0]
            analytics_service.track_event(
                user_id=str(user.id),
                event_name=AnalyticsEvent.AGENT_MESSAGE,
                event_properties={
                    "account_name": account_name,
                    "channel": first_msg.channel.value,
                    "conversation_id": str(conversation_id),
                    "testing": is_testing,
                },
            )

        # Make sure to handle the case after the response messages are created
        # Check if output.closing_conversation is True and mark the conversation as closing
        if output.closing_conversation:
            conversation = await db.ConversationRepositoryAsync(
                session
            ).get_conversation_by_id(conversation_id=conversation_id)
            if conversation:
                conversation.status = db.ConversationStatus.CLOSING
                await session.flush()

        return new_flow_response_messages

    except Exception:
        # Log any error and set default error response
        logger.exception("Error in get_chat_response_async")

    logger.info(f"Total execution time: {time.time() - start_time:.4f}s")
    return response_messages


async def get_chat_response_stream(
    session: AsyncSession, message: Message
) -> AsyncIterator[Message]:
    logger.info(f"get_chat_response_stream received message: {message}")
    user = None
    message_repo = db.MessageRepositoryAsync(session)

    try:
        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # If user not found, just create one (no opt-in here)
            user = await user_service.create_user_async(session, project, message)

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        if not request_message:
            raise ValueError("Failed to create request message")
        conversation_id = request_message.conversation_id
        is_testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )

        account_name = project.account.name
        event_properties = {
            "account_name": account_name,
            "channel": message.channel.value,
            "conversation_id": str(conversation_id),
            "testing": is_testing,
        }
        analytics_service.track_event(
            user_id=str(user.id),
            event_name=AnalyticsEvent.USER_MESSAGE,
            event_properties=event_properties,
        )
        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        # Construct config
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=conversation_id,
            stream=True,
        )
        agent = Agent(config=config)

        input = _utils.get_agent_input_from_message(message=message)
        logger.info(f"Input: {input}")

        output: Output = await agent.arun(input)  # type: ignore # Temporarily disble specific pyright errors since Datadog annotations are not fully compatible with pyright yet.

        logger.info(f"Output: {output}")

        new_flow_response_messages = _utils.get_messages_from_agent_output(
            output=output, input_message=message, project_name=project.name
        )

        if new_flow_response_messages:
            first_msg = new_flow_response_messages[0]

            event_properties = {
                "account_name": account_name,
                "channel": first_msg.channel.value,
                "conversation_id": str(conversation_id),
                "testing": is_testing,
            }
            analytics_service.track_event(
                user_id=str(user.id),
                event_name=AnalyticsEvent.AGENT_MESSAGE,
                event_properties=event_properties,
            )

        async def message_response_generator() -> AsyncIterator[Message]:
            for message in new_flow_response_messages:
                yield message

        return message_response_generator()

    except Exception:
        # Log any error and return error message stream
        logger.exception("Error in get_chat_response_stream")

        async def error_response_generator() -> AsyncIterator[Message]:
            error_message = Message(
                author_type=AuthorType.AGENT,
                sender_identifier=message.recipient_identifier,
                recipient_identifier=message.sender_identifier,
                channel=message.channel,
                broker=message.broker,
                channel_info=message.channel_info,
                text=TextObject(body="Something went wrong. Please try again."),
                metadata=message.metadata,
                extras=Extras(),
            )
            yield error_message

        return error_response_generator()


def get_chat_response(_session: Session, message: Message) -> Message:
    logger.info(message)
    response = "Synch mode chat has been deprecated."
    response_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        channel_info=message.channel_info,
        text=TextObject(body=response),
    )

    return response_message


def get_message_by_id(session: Session, message_id: uuid.UUID) -> db.Message | None:
    """
    Retrieves a Message by its unique identifier.

    This function queries the database to fetch the Message associated with the specified Message ID.

    Args:
        session (Session): The database connection.
        message_id (uuid.UUID): The unique identifier of the Message being retrieved.

    Returns:
        db.Message | None: The Message object associated with the unique identifier, or None if not found.
    """
    message = db.MessageRepository(session).get_message_by_id(message_id=message_id)
    return message


def get_messages_by_ids(
    session: Session, message_ids: list[uuid.UUID]
) -> list[db.Message]:
    messages = db.MessageRepository(session).get_messages_by_ids(
        message_ids=message_ids
    )
    return messages


def get_messages_by_conversation(
    session: Session, conversation_id: uuid.UUID
) -> list[db.Message]:
    """
    Retrieves all Messages for a given Conversation.

    This function queries the database to fetch all Messages associated with the specified Conversation ID.

    Args:
        session (Session): The database connection.
        conversation_id (uuid.UUID): The unique identifier of the Conversation for which Messages are being retrieved.

    Returns:
        list[db.Message]: A list of Message objects representing the messages in the specified Conversation.
    """
    messages = db.MessageRepository(session).get_messages_by_conversation(
        conversation_id=conversation_id
    )
    return messages


def get_conversations_by_user(
    session: Session, user_id: uuid.UUID, create_new_conversation: bool = False
) -> list[db.Conversation]:
    conversation_repository = db.ConversationRepository(session)
    conversations = conversation_repository.get_conversations_by_user(
        user_id=user_id,
    )

    if conversations:
        return conversations

    if create_new_conversation:
        new_conversation = conversation_repository.create_conversation(user_id=user_id)
        return [new_conversation] if new_conversation else []

    return []


def get_session_ids_by_users(
    session: Session, user_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    conversation_repository = db.ConversationRepository(session)
    session_ids = conversation_repository.get_conversation_ids_by_user_ids(user_ids)
    return session_ids


def get_conversations_by_users(
    session: Session,
    page: int,
    page_size: int,
    user_ids: list[uuid.UUID],
) -> tuple[int, list[db.Conversation]]:
    conversation_repository = db.ConversationRepository(session)
    conversations, total_conversations = (
        conversation_repository.get_conversations_by_users(
            page=page,
            page_size=page_size,
            user_ids=user_ids,
        )
    )
    return total_conversations, conversations


def create_conversation(session: Session, user_id: uuid.UUID) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    return conversation_repository.create_conversation(user_id=user_id)


def build_opt_in_message(
    message: Message, metadata: dict, extras: dict
) -> Message | None:
    if message.broker == Broker.TWILIO and message.channel == Channel.SMS:
        opt_in_text = (
            "You have successfully been subscribed to messages from this number. "
            "Reply STOP to unsubscribe. Msg&Data Rates May Apply."
        )
        return Message(
            author_type=AuthorType.AGENT,
            sender_identifier=message.recipient_identifier,  # Swap sender and recipient
            recipient_identifier=message.sender_identifier,
            channel=message.channel,
            broker=message.broker,
            channel_info=message.channel_info,
            text=TextObject(body=opt_in_text),
            metadata=Metadata(**metadata),
            extras=Extras(**extras),
        )

    return None
