import datetime
import random
import uuid
from typing import AsyncIterator

from agno.run.response import RunResponse
from openai.types.chat import ChatCompletionChunk
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
    Extras,
    Message,
    Metadata,
    TextObject,
)
from db.tables.types import Channel
from services import (
    agent_service,
    analytics_service,
    project_service,
    subscription_service,
    user_service,
)
from services.subscription_service import _stripe_product
from services.subscription_service.stripe_usage_billing import send_meter_event
from utils.dd import send_dd_histogram_metrics, trace_async_block
from utils.log import logger
from utils.request_context import RequestContext

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
    session: AsyncSession, message: Message, request_context: RequestContext
) -> list[Message]:
    logger.info(f"get_chat_response_async received message: {message}")

    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    try:
        # ==== Step 1: Get project, user, and save request message ====
        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        # Store project_id early while object is attached to session
        project_id = project.id

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, project_id=project_id, message_body=message.to_dict()
        )

        # Send analytics event
        await session.refresh(user, attribute_names=["id"])
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
            project_id=project_id,
            conversation_id=request_message.conversation_id,
            channel=message.channel,
        )

        logger.debug(f"Agent config: {config}")
        agent = Agent(config=config)

        # Get Input with conversation history
        input = await _utils.get_agent_input_from_message(
            message=message,
            stream=False,
            request_context=request_context,
        )
        logger.debug(f"Input: {input}")

        # Get Output
        output: Output = await agent.arun(input)  # type: ignore # Temporarily disable specific pyright errors since Datadog annotations are not fully compatible with pyright yet.
        logger.debug(f"Output: {output}")

        # Process output for URL updates
        await _utils.process_output_for_url_updates(
            output.content, message.recipient_identifier
        )

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
                        user_id=user.id,
                        project_id=project_id,
                        message_body=opt_in_message.to_dict(),
                    )

                    await session.refresh(user, attribute_names=["id"])
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

        user_id = user.id
        for message in final_output_messages:
            # Append response message to list of response messages
            response_messages.append(message)
            # Save response message to database
            await message_repo.create_message(
                user_id=user_id, project_id=project_id, message_body=message.to_dict()
            )

        await session.refresh(user, attribute_names=["id"])
        await session.refresh(request_message, attribute_names=["conversation_id"])
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

    except Exception as e:
        logger.exception("Error in get_chat_response_async")
        raise e

    return response_messages


async def get_chat_response_stream(
    session: AsyncSession, message: Message, request_context: RequestContext
) -> AsyncIterator[ChatCompletionChunk]:
    logger.info(f"get_chat_response_stream received message: {message}")

    async with trace_async_block("Message Service Stream Processing"):
        message_repo = db.MessageRepositoryAsync(session)

        try:
            # ==== Step 1: Get project, user, and save request message ====
            project = await project_service.get_project_async(session, message)

            user, is_new_sms_user = await user_service.get_user_async(
                session, project, message
            )

            if is_new_sms_user:
                raise ValueError("Stream mode should be only for voice mode")

            if user is None:
                user = await user_service.create_user_async(session, project, message)
            await session.refresh(user, attribute_names=["id"])

            logger.debug(
                f"Persist streaming inbound message: {message.to_dict()} from user: {user.id}"
            )
            request_message = await message_repo.create_message(
                user_id=user.id, project_id=project.id, message_body=message.to_dict()
            )
            if not request_message:
                raise ValueError("Failed to create request message")

            # Track user message event
            await session.refresh(user, attribute_names=["id"])
            await session.refresh(project, attribute_names=["account"])
            account_name = project.account.name
            testing = (
                getattr(message.metadata, "testing", False)
                if message.metadata
                else False
            )
            event_properties = {
                "account_name": account_name,
                "channel": message.channel.value,
                "conversation_id": str(request_message.conversation_id),
                "testing": testing,
            }

            analytics_service.track_event(
                user_id=str(user.id),
                event_name=AnalyticsEvent.USER_MESSAGE,
                event_properties=event_properties,
            )

            # ==== Step 2: Set up agent and generate streaming response ====
            agent_id = project.agent_id
            if agent_id is None:
                raise ValueError("Agent ID not found")

            # Configure agent for streaming
            config = await agent_service.construct_agent_config(
                session=session,
                agent_id=agent_id,
                user_id=user.id,
                project_id=project.id,
                conversation_id=request_message.conversation_id,
                channel=message.channel,
            )
            config.stream = True

            # Initialize agent and set up streaming input
            agent = Agent(config=config)

            logger.debug(f"Agent config stream mode: {config}")

            # Get Input with conversation history
            input = await _utils.get_agent_input_from_message(
                message=message,
                stream=True,
                request_context=request_context,
            )
            logger.debug(f"Input stream mode: {input}")
            send_dd_histogram_metrics(
                "message_service.start_streaming",
                request_context.request_time,
                [
                    f"agent_id:{agent_id}",
                    f"account_name:{account_name}",
                ],
            )

            # Get streaming response
            response_stream: AsyncIterator[Output] = await agent.arun(input)  # type: ignore
            collected_content = []

            # ==== Step 3: Process the streaming response ====
            if response_stream:
                async with trace_async_block("Message Service Streaming"):
                    index = 0
                    send_dd_histogram_metrics(
                        "message_service.waiting_first_chunk",
                        request_context.request_time,
                        [
                            f"agent_id:{agent_id}",
                            f"account_name:{account_name}",
                        ],
                    )

                    async for chunk in response_stream:
                        if index == 0:
                            send_dd_histogram_metrics(
                                "message_service.received_first_chunk",
                                request_context.request_time,
                                [
                                    f"agent_id:{agent_id}",
                                    f"account_name:{account_name}",
                                ],
                            )

                        async with trace_async_block(
                            "Process Stream Chunk",
                            tags={
                                "chunk_index": index,
                                "conversation_id": str(request_message.conversation_id),
                                "chunk_type": type(chunk).__name__,
                            },
                        ) as span:
                            # Process different chunk types into content string
                            content = ""
                            if isinstance(chunk, Output):
                                content = chunk.content
                                # Check for conversation closing if available
                                if (
                                    hasattr(chunk, "closing_conversation")
                                    and chunk.closing_conversation
                                ):
                                    conversation = await db.ConversationRepositoryAsync(
                                        session
                                    ).get_conversation_by_id(
                                        conversation_id=request_message.conversation_id
                                    )
                                    if conversation:
                                        conversation.status = (
                                            db.ConversationStatus.CLOSING
                                        )
                                        await session.flush()
                            elif isinstance(chunk, RunResponse):
                                content = chunk.get_content_as_string()
                            elif isinstance(chunk, tuple):
                                content = chunk[0]
                            elif isinstance(chunk, Message):
                                content = chunk.text.body if chunk.text else ""
                            elif chunk:
                                if not isinstance(chunk, (str, int, float, bool)):
                                    logger.warning(
                                        f"Unexpected chunk type: {type(chunk)}"
                                    )
                                    continue
                                content = str(chunk)

                            # Skip empty chunks
                            if not content:
                                continue

                            # Update span tags with content
                            span.set_tag(
                                "content",
                                content[:100] if len(content) > 100 else content,
                            )

                            # Create and yield chunk
                            chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
                            completion_chunk = ChatCompletionChunk(
                                id=chunk_id,
                                object="chat.completion.chunk",
                                created=int(
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).timestamp()
                                ),
                                model=message.recipient_identifier,
                                choices=[
                                    ChunkChoice(
                                        index=index,
                                        delta=ChoiceDelta(
                                            role="assistant", content=content
                                        ),
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield completion_chunk
                            # Store original content for relay service
                            collected_content.append(content)
                            index += 1

                # ==== Step 4: After streaming, save final messages to database ====
                if collected_content:
                    # Construct final messages from collected content
                    output_message_metadata = Metadata(
                        account_name=account_name,
                        project_name=project.name,
                        agent_id=str(agent_id),
                        user_id=str(user.id),
                        session_id=str(request_message.conversation_id),
                        testing=testing,
                    )

                    full_response = "".join(collected_content)

                    # Process output for URL updates
                    await _utils.process_output_for_url_updates(
                        full_response, message.recipient_identifier
                    )

                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        channel_info=message.channel_info,
                        text=TextObject(body=full_response),
                        metadata=output_message_metadata,
                    )

                    logger.debug(
                        f"Persist streaming outbound message: {response_message.to_dict()} to user: {user.id}"
                    )
                    await message_repo.create_message(
                        user_id=user.id,
                        project_id=project.id,
                        message_body=response_message.to_dict(),
                    )

                    await session.refresh(user, attribute_names=["id"])
                    # Send analytics for agent response (only once)
                    analytics_service.track_event(
                        user_id=str(user.id),
                        event_name=AnalyticsEvent.AGENT_MESSAGE,
                        event_properties=event_properties,
                    )

        except Exception as e:
            # Log error and return a single error chunk
            logger.exception(f"Error in get_chat_response_stream: {e}")
            error_message = ChatCompletionChunk(
                id=f"chatcmpl-{uuid.uuid4().hex}",
                object="chat.completion.chunk",
                created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
                model=message.recipient_identifier if message else "unknown",
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=ChoiceDelta(role="assistant", content=""),
                        finish_reason="stop",  # Using a valid finish_reason value
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


def create_conversation(
    session: Session,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    channel: Channel | None = None,
) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    conversation = conversation_repository.create_conversation(user_id=user_id)

    if not conversation:
        logger.error(f"Failed to create conversation for user {user_id}")
        return None

    if project_id and channel == Channel.VOICE:
        try:
            stripe_customer_id = (
                subscription_service.get_stripe_customer_id_for_project(
                    session, project_id
                )
            )
            if not stripe_customer_id:
                logger.warning(
                    f"No Stripe customer ID found for project {project_id} - skipping call usage tracking",
                    extra={
                        "project_id": str(project_id),
                        "user_id": str(user_id),
                        "conversation_id": str(conversation.id),
                    },
                )
            else:
                event_name = _stripe_product.get_call_meter_event_name(project_id)
                success = send_meter_event(
                    event_name=event_name,
                    stripe_customer_id=stripe_customer_id,
                    value=1,
                )

                if not success:
                    logger.error(
                        f"Failed to track call usage for conversation {conversation.id}",
                        extra={
                            "conversation_id": str(conversation.id),
                            "project_id": str(project_id),
                            "user_id": str(user_id),
                            "stripe_customer_id": stripe_customer_id,
                            "event_name": event_name,
                        },
                    )
        except Exception as e:
            logger.error(
                f"Error tracking call usage for conversation {conversation.id}: {e}",
                extra={
                    "conversation_id": str(conversation.id),
                    "project_id": str(project_id),
                    "user_id": str(user_id),
                    "event_name": _stripe_product.get_call_meter_event_name(project_id),
                },
                exc_info=True,
            )

    return conversation


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


async def create_phone_call_record(
    session: AsyncSession,
    message: dict,
    call_id: str,
    conversation_id: uuid.UUID,
) -> db.PhoneCall:
    """
    Create a phone call record.

    Args:
        session: Async database session
        message: Raw message data containing call information
        call_id: Call ID
        conversation_id: Associated conversation ID

    Returns:
        PhoneCall: The created phone call record

    Raises:
        ValueError: If required message data is missing
        SQLAlchemyError: If there is a database error
    """
    from ._utils import transform_vapi_call_data

    try:
        # Transform VAPI data to our schema
        call_metrics = transform_vapi_call_data(message)

        # Create phone call record
        phone_call_repo = db.PhoneCallRepositoryAsync(session)
        phone_call = await phone_call_repo.create_phone_call(
            call_id=call_id, conversation_id=conversation_id, **call_metrics
        )

        logger.info(f"Phone call record created: {phone_call.id} for call {call_id}")
        return phone_call

    except Exception as e:
        logger.error(f"Error creating phone call record: {e}")
        raise


def create_phone_call_record_sync(
    session: Session,
    message: dict,
    call_id: str,
    conversation_id: uuid.UUID,
) -> db.PhoneCall:
    """
    Create a phone call record (sync version).

    Args:
        session: Database session
        message: Raw message data containing call information
        call_id: Call ID
        conversation_id: Associated conversation ID

    Returns:
        PhoneCall: The created phone call record

    Raises:
        ValueError: If required message data is missing
        SQLAlchemyError: If there is a database error
    """
    from ._utils import transform_vapi_call_data

    try:
        # Transform VAPI data to our schema
        call_metrics = transform_vapi_call_data(message)

        # Create phone call record
        phone_call_repo = db.PhoneCallRepository(session)
        phone_call = phone_call_repo.create_phone_call(
            call_id=call_id, conversation_id=conversation_id, **call_metrics
        )

        logger.info(f"Phone call record created: {phone_call.id} for call {call_id}")
        return phone_call

    except Exception as e:
        logger.error(f"Error creating phone call record: {e}")
        raise
