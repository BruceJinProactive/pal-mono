import datetime
import random
import time
import uuid
from typing import AsyncIterator

from agno.models.openai.chat import OpenAIChat
from agno.run.response import RunResponse
from openai.types.chat import (
    ChatCompletionChunk,
)
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
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
    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    try:
        # ==== Step 1: Get project, user, and save request message ====
        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)
        # Ensure user is fully loaded before accessing attributes
        await session.refresh(user)

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )

        # Send analytics event
        await session.refresh(project, attribute_names=["account"])
        account_name = project.account.name
        testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )
        analytics_service.track_event(
            user_id=str(user.id),
            event_name=AnalyticsEvent.USER_MESSAGE,
            event_properties={
                "account_name": account_name,
                "channel": message.channel.value,
                "conversation_id": str(request_message.conversation_id),
                "testing": testing,
            },
        )

        if not request_message:
            raise ValueError("Failed to create request message")

        # ================= Step 2: Construct agent, get input, and generate output =================
        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        # Construct agent config
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=request_message.conversation_id,
            stream=False,
        )

        logger.info(f"Agent config: {config}")
        agent = Agent(config=config)

        # Get Input
        input = _utils.get_agent_input_from_message(message=message)
        logger.info(f"Input: {input}")

        # Get Output
        output: Output = await agent.arun(input)  # type: ignore # Temporarily disable specific pyright errors since Datadog annotations are not fully compatible with pyright yet.
        logger.info(f"Output: {output}")

        # ================ Step 3: Get response messages ================
        # Check if output.content contains a link and create additional SMS response if message.channel is VOICE
        output_message_metadata = Metadata(
            account_name=account_name,
            project_name=project.name,
            agent_id=str(agent_id),
            user_id=str(user.id),
            session_id=str(request_message.conversation_id),
            testing=testing,
        )

        # Get opt-in message and append to list of messages if applicable
        if is_new_sms_user:
            opt_in_message = build_opt_in_message(message, output_message_metadata)
            if opt_in_message:
                if user:
                    # Save the opt-in message to the database
                    await message_repo.create_message(
                        user_id=user.id, message_body=opt_in_message.to_dict()
                    )
                response_messages.append(opt_in_message)

        # Get output messages from agent output
        output_messages = _utils.get_messages_from_agent_output(
            output=output, input_message=message, metadata=output_message_metadata
        )

        # Check if messages need to be split into multiple messages using <BREAK> token
        final_output_messages = []
        for message in output_messages:
            if not message.text:
                logger.error(f"Message {message} text is None, skipping message.")
                continue

            split_texts = message.text.body.split("<BREAK>")

            for text in split_texts:
                sub_message = message.model_copy(deep=True)
                sub_message.text = TextObject(body=text.strip())
                final_output_messages.append(sub_message)

        for message in final_output_messages:
            # Append response message to list of response messages
            response_messages.append(message)
            # Save response message to database
            await message_repo.create_message(
                user_id=user.id, message_body=message.to_dict()
            )

        # Track only one event (for example, using the first message):
        if output_messages:
            first_msg = output_messages[0]
            analytics_service.track_event(
                user_id=str(user.id),
                event_name=AnalyticsEvent.AGENT_MESSAGE,
                event_properties={
                    "account_name": account_name,
                    "channel": first_msg.channel.value,
                    "conversation_id": str(request_message.conversation_id),
                    "testing": testing,
                },
            )

        # Make sure to handle the case after the response messages are created
        # Check if output.closing_conversation is True and mark the conversation as closing
        if output.closing_conversation:
            conversation = await db.ConversationRepositoryAsync(
                session
            ).get_conversation_by_id(conversation_id=request_message.conversation_id)
            if conversation:
                conversation.status = db.ConversationStatus.CLOSING
                await session.flush()

    except Exception:
        # Log any error and set default error response
        logger.exception("Error in get_chat_response_async")

    return response_messages


async def get_chat_response_stream_cached(
    session: AsyncSession, message: Message
) -> AsyncIterator[Message]:
    logger.info(f"get_chat_response_stream received message: {message}")
    # user = None
    # message_repo = db.MessageRepositoryAsync(session)
    logger.info("Access db")
    try:
        agent_id = uuid.UUID("82dcb010-2fb9-47f9-bb14-96ce08fed8c4")  # project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        # Construct config
        agent = message.cache.get(message.sender_identifier)  # type: ignore
        if not message.cache.has(message.sender_identifier) or agent is None:  # type: ignore

            config = await agent_service.construct_agent_config(
                session=session,
                agent_id=agent_id,
                user_id=uuid.UUID(message.sender_identifier),  # user.id,
                project_id=uuid.UUID(
                    "e31cdd5f-7718-4985-b284-2795b08bcd6f"
                ),  # project.id,
                conversation_id=uuid.UUID(
                    message.sender_identifier
                ),  # conversation_id,
                stream=True,
            )
            config.stream = True
            logger.info(f"Agent config: {config}")
            agent = Agent(config=config)
            agent._agent._agent.model = OpenAIChat(id="gpt-4o-mini")
            message.cache.set(message.sender_identifier, agent)  # type: ignore
            logger.info(f"Set config {message.sender_identifier}")
        else:
            logger.info(f"Use existing config {message.sender_identifier}")

        input = _utils.get_agent_input_from_message(message=message)
        logger.info("Input: Start")
        flow_response_messages = await agent.arun(input)  # type: ignore
        logger.info("Output: Done")
        return flow_response_messages

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


async def get_chat_response_stream(
    session: AsyncSession, message: Message
) -> AsyncIterator[ChatCompletionChunk]:
    sender_identifier = message.sender_identifier

    logger.info(
        f"{sender_identifier}: get_chat_response_stream received message: {message}"
    )
    user = None
    commit_start = time.perf_counter()
    message_repo = db.MessageRepositoryAsync(session)
    logger.info(
        f"{sender_identifier}: message_repo, Took {time.perf_counter() - commit_start:.4f}s"
    )
    try:
        # find project with matching channel platform, identifier pair
        commit_start = time.perf_counter()
        project = await project_service.get_project_async(session, message)
        logger.info(
            f"{sender_identifier}: Access project: {project}, Took {time.perf_counter() - commit_start:.4f}s"
        )
        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # If user not found, just create one (no opt-in here)
            commit_start = time.perf_counter()
            user = await user_service.create_user_async(session, project, message)
            logger.info(
                f"{sender_identifier}: Create new user: {user}, Took {time.perf_counter() - commit_start:.4f}s"
            )
        logger.info(f"{sender_identifier}: Access user")
        await session.refresh(user)
        # Save request message to database
        commit_start = time.perf_counter()
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        logger.info(
            f"{sender_identifier}: Save msg: {request_message.conversation_id}, Took {time.perf_counter() - commit_start:.4f}s"
        )
        if not request_message:
            raise ValueError("Failed to create request message")
        conversation_id = request_message.conversation_id
        testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )
        await session.refresh(project, attribute_names=["account"])
        account_name = project.account.name
        event_properties = {
            "account_name": account_name,
            "channel": message.channel.value,
            "conversation_id": str(conversation_id),
            "testing": testing,
        }
        commit_start = time.perf_counter()
        analytics_service.track_event(
            user_id=str(user.id),
            event_name=AnalyticsEvent.USER_MESSAGE,
            event_properties=event_properties,
        )
        logger.info(
            f"{sender_identifier}: Track_event, Took {time.perf_counter() - commit_start:.4f}s"
        )
        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        # Construct config
        commit_start = time.perf_counter()
        config = await agent_service.construct_agent_config(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            project_id=project.id,
            conversation_id=conversation_id,
            stream=True,
        )
        logger.info(
            f"{sender_identifier}: Agent config, Took {time.perf_counter() - commit_start:.4f}s"
        )
        config.stream = True
        commit_start = time.perf_counter()
        agent = Agent(config=config)
        logger.info(
            f"{sender_identifier}: Agent init, Took {time.perf_counter() - commit_start:.4f}s"
        )
        input = _utils.get_agent_input_from_message(message=message)
        logger.info(f"{sender_identifier}: Input: Start")
        commit_start = time.perf_counter()
        response_stream = await agent.arun(input)  # type: ignore
        logger.info(
            f"{sender_identifier}: Output: Done, Took {time.perf_counter() - commit_start:.4f}s"
        )
        output_messages = []
        if response_stream:
            i = 0
            async for chunk in response_stream:
                rid = f"chatcmpl-{uuid.uuid4().hex}"  # TODO: fix this
                if isinstance(chunk, RunResponse):
                    content = chunk.get_content_as_string()
                elif isinstance(chunk, tuple):
                    content = chunk[0]
                elif isinstance(chunk, Message):
                    content = chunk.text.body if chunk.text else ""
                    rid = chunk.id
                elif chunk:
                    if not isinstance(chunk, (str, int, float, bool)):
                        logger.warning(f"Unexpected chunk type: {type(chunk)}")
                        continue
                    content = str(chunk)
                else:
                    content = ""
                logger.info(f"{sender_identifier}: Sending chunk: {content}")
                chunk = ChatCompletionChunk(
                    id=rid,
                    object="chat.completion.chunk",
                    created=int(
                        datetime.datetime.now(datetime.timezone.utc).timestamp()
                    ),
                    model=message.recipient_identifier,
                    choices=[
                        ChunkChoice(
                            index=i,
                            delta=(ChoiceDelta(role="assistant", content=content)),
                            finish_reason=None,
                        )
                    ],
                )
                yield chunk
                i += 1
                output_messages.append(content)

        if response_stream:
            analytics_service.track_event(
                user_id=str(user.id),
                event_name=AnalyticsEvent.AGENT_MESSAGE,
                event_properties={
                    "account_name": account_name,
                    "channel": message.channel.value,
                    "conversation_id": str(request_message.conversation_id),
                    "testing": testing,
                },
            )

            # Make sure to handle the case after the response messages are created
            # Check if output.closing_conversation is True and mark the conversation as closing

            conversation = await db.ConversationRepositoryAsync(
                session
            ).get_conversation_by_id(conversation_id=request_message.conversation_id)
            if conversation:
                conversation.status = db.ConversationStatus.CLOSING
                commit_start = time.perf_counter()
                await session.flush()

                logger.info(
                    f"{sender_identifier}: Conversation status updated to CLOSING, Took {time.perf_counter() - commit_start:.4f}s"
                )
            # await session.commit()
    except Exception as e:
        # Log any error and return error message stream
        logger.error(f"Error in get_chat_response_stream: {message},{e}")
        error_message = ChatCompletionChunk(
            id=f"chatcmpl-{uuid.uuid4().hex}",  # TODO: fix this,
            object="chat.completion.chunk",
            created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            model=message.recipient_identifier,
            choices=[
                ChunkChoice(
                    index=0,
                    delta=(ChoiceDelta(role="assistant", content="")),
                    finish_reason=None,
                )
            ],
        )
        yield error_message


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


def build_opt_in_message(message: Message, metadata: Metadata) -> Message | None:
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
            metadata=metadata,
            extras=Extras(),
        )

    return None
