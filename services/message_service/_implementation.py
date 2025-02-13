import random
import time
import uuid
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import Agent
from agent.input_output import Output
from agent.model import BaseOutputModel
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Channel,
    Extras,
    MediaObject,
    Message,
    TextObject,
)
from api.schemas.chat.message import Type as MessageType
from services import agent_service, project_service, user_service
from utils.log import logger

from . import _utils


def get_filler_message(message: Message) -> Message:
    # Collection of filler phrases for voice responses
    FILLER_PHRASES = [
        "One moment, please.",
        "Just a moment.",
        "Be right with you.",
        "Working now.",
        "Gathering info.",
        "Bear with me.",
        "Processing now.",
        "Stay on the line.",
        "Help is coming.",
        "Please hold.",
        "Answer soon.",
        "One brief moment.",
        "Brief moment.",
        "Hold the line.",
        "Working on it.",
        "Stay connected.",
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
    )
    _add_message_info_to_metadata(message=message, metadata=filler_message.metadata)
    return filler_message


async def get_chat_response_async(
    session: AsyncSession, message: Message
) -> list[Message]:
    logger.info(f"get_chat_response_async received message: {message}")
    user = None
    extras = {}
    metadata = {"instance": "BaseModel"}
    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    start_time = time.time()  # Start time for profiling latency
    try:
        logger.info(f"Step 1: Initialization - {time.time() - start_time:.4f}s")

        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        logger.info(f"Step 2: Retrieved project - {time.time() - start_time:.4f}s")

        metadata["project_name"] = project.name

        # Add MessageSid or CallSid to the metadata based on the channel
        _add_message_info_to_metadata(message, metadata)

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

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
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

        # ========================== New - Start ==========================
        # Explicitly load the project.account attribute
        await session.refresh(project, attribute_names=["account"])
        new_agents = ["palona", "windsor", "new-pizzamyheart"]
        if project.account.name in new_agents:
            logger.info("Test new agent building flow.")

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

            # Get Input
            input = _utils.get_agent_input_from_message(message=message)
            logger.info(f"Input: {input}")

            # Get Output
            output: Output = await agent.arun(input)  # type: ignore # Temporarily disble specific pyright errors since Datadog annotations are not fully compatible with pyright yet.

            logger.info(f"Output: {output}")

            return _utils.get_messages_from_agent_output(
                output=output, input_message=message
            )

        # ========================== New - End ==========================

        else:
            agent = await agent_service.get_ai_agent_async(
                session=session,
                agent_id=agent_id,
                user_id=user.id,
                project_id=project.id,
                conversation_id=conversation_id,
            )

        logger.info(f"Step 5: Retrieved agent - {time.time() - start_time:.4f}s")

        # Get response from agent
        request_content = message.get_content()
        response_object = await agent.arun(request_content, stream=False)
        response_content = response_object.content

        logger.info(
            f"Step 6: Agent response received - {time.time() - start_time:.4f}s"
        )

        if isinstance(response_content, str):
            response = response_content
        elif isinstance(response_content, BaseOutputModel):
            response = response_content.content
            extras = {"escalated": response_content.escalated}
            response_parts = _utils.extract_image_links(response)

            # process each part of the response after regex processing
            response_message = None
            for msg_type, msg_content in response_parts:
                if msg_type == "text":
                    # Strip markdown content from response
                    msg_content = _utils.strip_markdown_content(msg_content)
                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        text=TextObject(body=msg_content),
                        metadata=metadata,
                        extras=Extras(**extras),
                    )
                elif msg_type == "image":
                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        type=MessageType.MEDIA,
                        media=MediaObject(
                            url=msg_content, media_type="image", caption=msg_content
                        ),
                        metadata=metadata,
                        extras=Extras(**extras),
                    )

                if response_message:
                    if user:
                        # Save response message to database
                        await message_repo.create_message(
                            user_id=user.id, message_body=response_message.to_dict()
                        )

                    response_messages.append(response_message)

                logger.info(
                    f"Step 8: Response processing completed - {time.time() - start_time:.4f}s"
                )
        else:
            raise ValueError(
                f"Can't handle response content type {type(response_content)} for userid {user.id} with request content {request_content}."
            )

    except Exception:
        # Log any error and set default error response
        logger.exception("Error in get_chat_response_async")
        response = "Something went wrong. Please try again."

    logger.info(f"Total execution time: {time.time() - start_time:.4f}s")
    return response_messages


async def get_chat_response_stream(
    session: AsyncSession, message: Message
) -> AsyncIterator[Message]:
    user = None
    message_repo = db.MessageRepositoryAsync(session)

    async def error_response_generator() -> AsyncIterator[Message]:
        error_message = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=message.recipient_identifier,
            recipient_identifier=message.sender_identifier,
            channel=message.channel,
            broker=message.broker,
            text=TextObject(body="Something went wrong. Please try again."),
            metadata={"instance": "BaseModel"},
            extras=Extras(),
        )
        yield error_message

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

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        agent = await agent_service.get_ai_agent_async(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=conversation_id,
            stream=True,
        )

        # Get response from agent
        request_content = message.get_content()
        response_stream = await agent.arun(request_content, stream=True)
        return response_stream

    except Exception:
        # Log any error and return error message stream
        logger.exception("Error in get_chat_response_stream")
        return error_response_generator()


def get_chat_response(session: Session, message: Message) -> Message:
    logger.info(message)

    user = None
    metadata = {"instance": "BaseModel"}
    extras = {}

    try:
        # find project with matching channel platform, identifier pair
        project = project_service.get_project_sync(session, message)

        if project is None:
            raise ValueError(
                f"Project with channel platform '{message.channel.value}', channel_identifier '{message.recipient_identifier}' not found."
            )

        metadata["project_name"] = project.name

        # Add MessageSid or CallSid to the metadata based on the channel
        _add_message_info_to_metadata(message=message, metadata=metadata)

        # Get user_id by sender channel/number with user_service
        user_channel_identifier = f"{message.channel.value}:{message.sender_identifier}"
        user = user_service.get_user_by_channel_identifier(
            session=session,
            account_id=project.account_id,
            channel_identifier=user_channel_identifier,
            create_new_user=False,
        )

        if user is None:
            # Return user opt-in message if broker is Twilio
            opt_in_message = build_opt_in_message(message, metadata, extras)
            if opt_in_message:
                # Create new user record right away:
                user = user_service.get_user_by_channel_identifier(
                    session=session,
                    account_id=project.account_id,
                    channel_identifier=user_channel_identifier,
                    create_new_user=True,
                )

                if user:
                    # Save request message to database
                    db.MessageRepository(session).create_message(
                        user_id=user.id, message_body=message.to_dict()
                    )

                    # Save response message to database
                    db.MessageRepository(session).create_message(
                        user_id=user.id, message_body=opt_in_message.to_dict()
                    )

                return opt_in_message
            else:
                raise ValueError("User not found")

        # Save request message to database
        request_message = db.MessageRepository(session).create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        conversation_id = request_message.conversation_id

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        agent = agent_service.get_ai_agent(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=conversation_id,
        )

        # Get response from agent
        request_content = message.get_content()
        response_object = agent.run(request_content, stream=False)
        if isinstance(response_object.content, str):
            response = response_object.content
        elif isinstance(response_object.content, BaseOutputModel):
            response = response_object.content.content
            extras = {"escalated": response_object.content.escalated}
        else:
            raise ValueError(
                f"Can't handle response content type {type(response_object.content)} for userid {user.id} with request content {request_content}."
            )

        # Strip markdown content from response
        response = _utils.strip_markdown_content(response)

    except Exception as e:
        # Log any error and set default error response
        logger.error(e)
        response = "Something went wrong. Please try again."

    response_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        text=TextObject(body=response),
        metadata=metadata,
        extras=Extras(**extras),
    )

    if user:
        # Save response message to database
        db.MessageRepository(session).create_message(
            user_id=user.id, message_body=response_message.to_dict()
        )

    return response_message


def _add_message_info_to_metadata(message: Message, metadata: dict) -> None:
    """
    Add MessageSid or CallSid to the metadata based on the channel type.

    Args:
        message (Message): The message containing channel and metadata information
        metadata (dict): The metadata dictionary to update
    """
    if message.channel == Channel.SMS and "MessageSid" in message.metadata:
        metadata["MessageSid"] = message.metadata["MessageSid"]
    elif message.channel == Channel.VOICE and "CallSid" in message.metadata:
        metadata["CallSid"] = message.metadata["CallSid"]


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


def get_conversations_by_users(
    session: Session, user_ids: list[uuid.UUID]
) -> list[db.Conversation]:
    conversation_repository = db.ConversationRepository(session)
    return conversation_repository.get_conversations_by_users(
        user_ids=user_ids,
    )


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
            text=TextObject(body=opt_in_text),
            metadata=metadata,
            extras=Extras(**extras),
        )

    return None
