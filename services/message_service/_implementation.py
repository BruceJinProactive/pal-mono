import asyncio
import datetime
import random
import uuid
from typing import AsyncIterator

from agno.run.response import RunResponse
from ddtrace.llmobs import LLMObs
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from pal_agents import Agent as PalAgent
from pal_agents import Input as PalInput
from pal_agents.input import RuntimeContext
from pal_agents.providers.memory.ingestion import get_ingestion_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from agent import Agent
from agent.framework.internal.filler_words_manager import FillerWordsManager
from agent.input_output import Output
from agent.storage._implementation import query_history_messages
from api.schemas.chat.message import (
    AuthorType,
    Broker,
    Extras,
    Message,
    Metadata,
    TextObject,
)
from db.tables.types import Channel
from services import agent_service, project_service, user_service
from utils.dd import is_testing_mode, send_dd_histogram_metrics, trace_async_block
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
    # Initialize LLMObs for Datadog LLM Observability
    if is_testing_mode():
        # Explicitly disable LLMObs for testing requests to prevent data collection
        LLMObs.disable()
    else:
        LLMObs.enable(ml_app="pal", agentless_enabled=True)

    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    try:
        # ==== Step 1: Get project, user, and save request message ====
        # find project with matching channel platform, identifier pair
        project = await project_service.get_project_async(session, message)

        # Store project_id, account_id, and raw_config early while object is attached to session
        project_id = project.id
        project_account_id = project.account_id  # Capture early for memory ingestion
        project_raw_config = project.raw_config or {}

        # Check if project uses pal-agents framework (from raw_config)
        use_pal_agents = project_raw_config.get("use_pal_agents", False)

        # Get user_id by sender channel/number with user_service
        user, is_new_sms_user = await user_service.get_user_async(
            session, project, message
        )
        if user is None:
            # Create new user record
            user = await user_service.create_user_async(session, project, message)

        # Capture user_id early while object is attached to session (for memory ingestion)
        ingestion_user_id = user.id

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id,
            project_id=project_id,
            message_body=message.to_dict(),
            channel=message.channel.value if message.channel else "unknown",
        )

        # Get account info for metadata
        await session.refresh(user, attribute_names=["id"])
        await session.refresh(project, attribute_names=["account"])
        account_name = project.account.name
        testing = (
            getattr(message.metadata, "testing", False) if message.metadata else False
        )

        if not request_message:
            raise ValueError("Failed to create request message")

        # Capture conversation_id early while object is attached to session (for memory ingestion)
        request_conversation_id = request_message.conversation_id

        # Get agent_id (needed for metadata regardless of which flow)
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        # **************** Step 2: Construct agent, get input, and generate output ****************
        # Initialize current_message for memory ingestion (defined in pal-agents branch)
        current_message = ""
        if use_pal_agents:
            # NEW FLOW: Use pal-agents

            spec = await agent_service.construct_agent_spec(
                session=session,
                agent_id=agent_id,
                user_id=user.id,
                project_id=project_id,
                conversation_id=request_message.conversation_id,
                channel=message.channel,
                sender_identifier=message.sender_identifier,
                raw_config=project_raw_config,
            )

            pal_agent = PalAgent(spec=spec)

            # Build RuntimeContext for tool execution
            # Determines customer_phone based on channel type
            customer_phone = None
            if message.channel and message.channel.value.lower() in [
                "sms",
                "voice",
                "whatsapp",
            ]:
                customer_phone = message.sender_identifier

            runtime_context = RuntimeContext(
                user_id=str(user.id),
                session_id=str(request_message.conversation_id),
                customer_phone=customer_phone,
                project_id=str(project_id),
                account_id=str(project.account_id),
                account_name=account_name,
                agent_id=str(agent_id),
                timezone=project.timezone or "America/Los_Angeles",
                channel=message.channel.value,
            )

            # Fetch conversation history
            history_messages = await query_history_messages(
                request_message.conversation_id,
                limit=100,
            )

            # Format history for context
            # Match legacy flow's defensive pattern: verify last message matches
            # current input before excluding (see agent/framework/agno.py:356-377)
            current_message = message.text.body if message.text else ""
            history_text = ""
            if history_messages:
                # Check if last message matches current input (should be the case
                # since create_message commits before we fetch history)
                if (
                    history_messages[-1].content == current_message
                    and history_messages[-1].role == "user"
                ):
                    # Exclude current message from history
                    prior_messages = history_messages[:-1]
                else:
                    # Defensive: log warning but include all history
                    # (safer to have potential duplicate than missing context)
                    logger.warning(
                        "[pal-agents] Last history message does not match current input. "
                        f"Expected: {current_message[:50]}..., "
                        f"Got: {(history_messages[-1].content or '')[:50]}..."
                    )
                    prior_messages = history_messages

                if prior_messages:
                    history_text = "\n".join(
                        [
                            f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}"
                            for msg in prior_messages
                            if msg.content  # Filter out None/empty content
                        ]
                    )

            # Build content with history
            if history_text:
                full_content = (
                    f"<conversation_history>\n{history_text}\n</conversation_history>\n\n"
                    f"User: {current_message}"
                )
            else:
                full_content = f"User: {current_message}"

            pal_input = PalInput(
                content=full_content,
                runtime_context=runtime_context,
            )

            pal_output = await pal_agent.run(pal_input)

            # Use pal-agents Output fields directly (v0.2.1+)
            output = Output(
                content=pal_output.content,
                escalated=pal_output.escalated,
                closing_conversation=pal_output.closing_conversation,
            )
        else:
            # EXISTING FLOW: Use current agent system

            # Construct agent config
            config = await agent_service.construct_agent_config(
                session=session,
                agent_id=agent_id,
                user_id=user.id,
                project_id=project_id,
                conversation_id=request_message.conversation_id,
                channel=message.channel,
                sender_identifier=message.sender_identifier,
                receiver_identifier=message.recipient_identifier,
            )

            agent = Agent(config=config)

            # Get Input with conversation history
            input = await _utils.get_agent_input_from_message(
                message=message,
                stream=False,
                request_context=request_context,
            )
            # Get Output
            output: Output = await agent.arun(input)  # type: ignore # Temporarily disable specific pyright errors since Datadog annotations are not fully compatible with pyright yet.

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
                        channel=(
                            opt_in_message.channel.value
                            if opt_in_message.channel
                            else "unknown"
                        ),
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
                user_id=user_id,
                project_id=project_id,
                message_body=message.to_dict(),
                channel=message.channel.value if message.channel else "unknown",
            )

        await session.refresh(user, attribute_names=["id"])
        await session.refresh(request_message, attribute_names=["conversation_id"])

        # Memory ingestion for pal-agents flow (fire-and-forget)
        # Only triggers for pal-agents projects; agno agents are unaffected
        if use_pal_agents:
            # Use early-captured values to avoid SQLAlchemy lazy load issues
            asyncio.create_task(
                get_ingestion_service().ingest_interaction(
                    account_id=str(project_account_id),
                    user_id=str(ingestion_user_id),
                    conversation_id=str(request_conversation_id),
                    user_message=current_message,
                    assistant_message=output.content,
                )
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
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    call_id: str | None = None,
    room_name: str | None = None,
    participant_identity: str | None = None,
) -> AsyncIterator[ChatCompletionChunk]:
    # Initialize LLMObs for Datadog LLM Observability
    if is_testing_mode():
        # Explicitly disable LLMObs for testing requests to prevent data collection
        LLMObs.disable()
    else:
        LLMObs.enable(ml_app="pal", agentless_enabled=True)

    async with trace_async_block("Message Service Stream Processing"):
        message_repo = db.MessageRepositoryAsync(session)
        stream_id = f"chatcmpl-{uuid.uuid4().hex}"

        try:
            # ==== Step 1: Get project, user, and save request message ====
            project = await project_service.get_project_async(session, message)
            # Capture account_id and raw_config early while object is attached to session
            project_account_id = project.account_id
            project_raw_config = project.raw_config or {}

            # Check if project uses pal-agents framework (from raw_config)
            use_pal_agents = project_raw_config.get("use_pal_agents", False)

            user, is_new_sms_user = await user_service.get_user_async(
                session, project, message
            )

            if is_new_sms_user:
                raise ValueError("Stream mode should be only for voice mode")

            if user is None:
                user = await user_service.create_user_async(session, project, message)
            await session.refresh(user, attribute_names=["id"])

            # Capture user_id early while object is attached to session (for memory ingestion)
            ingestion_user_id = user.id

            # For VOICE channel with call_id, use voice-specific message creation
            # to reuse the conversation created during handle_assistant_request
            if message.channel == Channel.VOICE and call_id:
                request_message = await message_repo.add_message_to_voice_conversation(
                    user_id=user.id,
                    message_body=message.to_dict(),
                    call_id=call_id,
                )
            else:
                # Warn if voice message is missing call_id - this shouldn't happen
                if message.channel == Channel.VOICE and not call_id:
                    logger.warning(
                        "[get_chat_response_stream] Voice message missing call_id, "
                        "falling back to text message conversation logic",
                        extra={
                            "user_id": str(user.id),
                            "project_id": str(project.id),
                            "sender_identifier": message.sender_identifier,
                            "recipient_identifier": message.recipient_identifier,
                        },
                    )
                # Existing text message logic with conversation reuse
                request_message = await message_repo.create_message(
                    user_id=user.id,
                    project_id=project.id,
                    message_body=message.to_dict(),
                    channel=message.channel.value if message.channel else "unknown",
                )

            if not request_message:
                raise ValueError("Failed to create request message")

            # Capture conversation_id early while object is attached to session (for memory ingestion)
            request_conversation_id = request_message.conversation_id

            # Get account info for metadata
            # NOTE: Adding "agent" here causes a redundant DB load since construct_agent_spec()
            # also loads the agent via get_agent(agent_id). Future optimization: return
            # filler_words_config from construct_agent_spec() to eliminate this extra query.
            # See: services/agent_service/_implementation.py lines 239-241
            await session.refresh(user, attribute_names=["id"])
            await session.refresh(project, attribute_names=["account", "agent"])
            account_name = project.account.name
            testing = (
                getattr(message.metadata, "testing", False)
                if message.metadata
                else False
            )

            # ==== Step 2: Set up agent and generate streaming response ====
            agent_id = project.agent_id
            if agent_id is None:
                raise ValueError("Agent ID not found")

            collected_content: list[str] = []
            # Initialize current_message for memory ingestion (defined in pal-agents branch)
            current_message = ""

            # ========== CHUNK GENERATION (if/else by project config) ==========
            if use_pal_agents:
                # PAL-AGENTS PATH

                spec = await agent_service.construct_agent_spec(
                    session=session,
                    agent_id=agent_id,
                    user_id=user.id,
                    project_id=project.id,
                    conversation_id=request_message.conversation_id,
                    channel=message.channel,
                    sender_identifier=message.sender_identifier,
                    raw_config=project_raw_config,
                    room_name=room_name,
                    participant_identity=participant_identity,
                )
                pal_agent = PalAgent(spec=spec)

                # Build RuntimeContext (same as non-streaming)
                customer_phone = None
                if message.channel and message.channel.value.lower() in [
                    "sms",
                    "voice",
                    "whatsapp",
                ]:
                    customer_phone = message.sender_identifier

                # Pre-fetch voice-specific data for RuntimeContext
                vapi_control_url = None
                if message.channel == Channel.VOICE and call_id:
                    try:
                        conversation = await db.ConversationRepositoryAsync(
                            session
                        ).get_conversation_by_id(
                            conversation_id=request_message.conversation_id
                        )
                        vapi_control_url = conversation.vapi_control_url
                    except Exception as e:
                        # Catch all exceptions for graceful degradation during voice calls.
                        # VapiTool has fallback to fetch control_url from Vapi API if None.
                        logger.warning(
                            "Failed to fetch conversation for vapi_control_url: %s",
                            str(e),
                            extra={
                                "conversation_id": str(request_message.conversation_id),
                                "call_id": call_id,
                                "exception_type": type(e).__name__,
                            },
                        )

                runtime_context = RuntimeContext(
                    user_id=str(user.id),
                    session_id=str(request_message.conversation_id),
                    customer_phone=customer_phone,
                    project_id=str(project.id),
                    account_id=str(project.account_id),
                    account_name=account_name,
                    agent_id=str(agent_id),
                    timezone=project.timezone or "America/Los_Angeles",
                    channel=message.channel.value,
                    # Voice-specific fields (extra="allow" permits these)
                    call_id=call_id,  # type: ignore[call-arg]
                    vapi_control_url=vapi_control_url,  # type: ignore[call-arg]
                    room_name=room_name,  # type: ignore[call-arg]
                    participant_identity=participant_identity,  # type: ignore[call-arg]
                )

                # Fetch and format conversation history (same as non-streaming)
                history_messages = await query_history_messages(
                    request_message.conversation_id,
                    limit=100,
                )

                current_message = message.text.body if message.text else ""
                history_text = ""
                if history_messages:
                    if (
                        history_messages[-1].content == current_message
                        and history_messages[-1].role == "user"
                    ):
                        prior_messages = history_messages[:-1]
                    else:
                        logger.warning(
                            "[pal-agents streaming] Last history message does not match current input. "
                            f"Expected: {current_message[:50]}..., "
                            f"Got: {(history_messages[-1].content or '')[:50]}..."
                        )
                        prior_messages = history_messages

                    if prior_messages:
                        history_text = "\n".join(
                            [
                                f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}"
                                for msg in prior_messages
                                if msg.content  # Filter out None/empty content
                            ]
                        )

                if history_text:
                    full_content = (
                        f"<conversation_history>\n{history_text}\n</conversation_history>\n\n"
                        f"User: {current_message}"
                    )
                else:
                    full_content = f"User: {current_message}"

                pal_input = PalInput(
                    content=full_content,
                    runtime_context=runtime_context,
                )

                send_dd_histogram_metrics(
                    "message_service.start_streaming",
                    request_context.request_time,
                    [
                        f"agent_id:{agent_id}",
                        f"account_name:{account_name}",
                    ],
                )

                # ════════════════════════════════════════════════════════
                # CHAT FILLER INJECTION (mirrors agno implementation)
                # ════════════════════════════════════════════════════════
                # Wrapped in try/except to ensure filler failures don't break streaming.
                # Filler is a UX enhancement; graceful degradation is appropriate.
                chat_filler = ""
                try:
                    filler_words_config = project.agent.filler_words or {}
                    chat_filler_percentage = filler_words_config.get(
                        "chat_filler_words_percentage", 80
                    )

                    filler_manager = FillerWordsManager(
                        agent_id=str(agent_id),
                        account_name=account_name,
                        chat_filler_words_percentage=chat_filler_percentage,
                        tool_calling_filler_words_percentage=0,  # Not used
                    )
                    chat_filler = filler_manager.get_chat_filler_for_input(
                        current_message
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to generate chat filler",
                        extra={
                            "error": str(e),
                            "agent_id": str(agent_id),
                            "account_name": account_name,
                        },
                    )

                if chat_filler:
                    send_dd_histogram_metrics(
                        "message_service.filler_chunk_yielded",
                        request_context.request_time,
                        [
                            f"agent_id:{agent_id}",
                            f"account_name:{account_name}",
                        ],
                    )
                    filler_chunk = ChatCompletionChunk(
                        id=stream_id,
                        object="chat.completion.chunk",
                        created=int(
                            datetime.datetime.now(datetime.timezone.utc).timestamp()
                        ),
                        model=message.recipient_identifier,
                        choices=[
                            ChunkChoice(
                                index=0,
                                delta=ChoiceDelta(
                                    role="assistant", content=chat_filler
                                ),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield filler_chunk
                    collected_content.append(chat_filler)

                # Stream from pal-agents
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

                    try:
                        pal_stream = await pal_agent.run(pal_input, stream=True)
                        if pal_stream is None:
                            # Gracefully stop streaming when upstream cancellation/teardown
                            # results in a missing iterator from pal-agents.
                            logger.warn(
                                "[MessageService] pal-agents stream unavailable, ending stream",
                                extra={
                                    "agent_id": str(agent_id),
                                    "conversation_id": str(request_conversation_id),
                                },
                            )
                            return
                        if not hasattr(pal_stream, "__aiter__"):
                            raise TypeError(
                                "Expected async iterator from pal_agent.run(stream=True), "
                                f"got {type(pal_stream).__name__}"
                            )

                        async for chunk in pal_stream:
                            if index == 0:
                                send_dd_histogram_metrics(
                                    "message_service.received_first_chunk",
                                    request_context.request_time,
                                    [
                                        f"agent_id:{agent_id}",
                                        f"account_name:{account_name}",
                                    ],
                                )

                            if not chunk.content:
                                continue

                            completion_chunk = ChatCompletionChunk(
                                id=stream_id,
                                object="chat.completion.chunk",
                                created=int(
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).timestamp()
                                ),
                                model=message.recipient_identifier,
                                choices=[
                                    ChunkChoice(
                                        index=0,
                                        delta=ChoiceDelta(
                                            role="assistant", content=chunk.content
                                        ),
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield completion_chunk
                            collected_content.append(chunk.content)
                            index += 1
                    except asyncio.CancelledError:
                        logger.debug("[MessageService] pal-agents stream cancelled")
                        return
                    except RuntimeError as stream_error:
                        # ddtrace's async generator wrapper can convert normal
                        # StopAsyncIteration completion into a RuntimeError.
                        if (
                            isinstance(stream_error.__cause__, StopAsyncIteration)
                            or str(stream_error)
                            == "async generator raised StopAsyncIteration"
                        ):
                            logger.debug(
                                "pal-agents stream ended with wrapped StopAsyncIteration",
                                extra={
                                    "agent_id": str(agent_id),
                                    "conversation_id": str(request_conversation_id),
                                    "error": str(stream_error),
                                    "error_type": type(stream_error).__name__,
                                    "cause": str(stream_error.__cause__),
                                    "cause_type": (
                                        type(stream_error.__cause__).__name__
                                        if stream_error.__cause__
                                        else None
                                    ),
                                },
                            )
                        else:
                            raise

            else:
                # LEGACY PATH - existing agent system
                config = await agent_service.construct_agent_config(
                    session=session,
                    agent_id=agent_id,
                    user_id=user.id,
                    project_id=project.id,
                    conversation_id=request_message.conversation_id,
                    channel=message.channel,
                    sender_identifier=message.sender_identifier,
                    receiver_identifier=message.recipient_identifier,
                    room_name=room_name,
                    participant_identity=participant_identity,
                )
                config.stream = True

                agent = Agent(config=config)

                input = await _utils.get_agent_input_from_message(
                    message=message,
                    stream=True,
                    request_context=request_context,
                )
                send_dd_histogram_metrics(
                    "message_service.start_streaming",
                    request_context.request_time,
                    [
                        f"agent_id:{agent_id}",
                        f"account_name:{account_name}",
                    ],
                )

                response_stream: AsyncIterator[Output] = await agent.arun(input)  # type: ignore

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
                                    "conversation_id": str(
                                        request_message.conversation_id
                                    ),
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

                                # Update span tags with content (skip if span is None in testing mode)
                                if span:
                                    span.set_tag(
                                        "content",
                                        (
                                            content[:100]
                                            if len(content) > 100
                                            else content
                                        ),
                                    )

                                # Create and yield chunk
                                completion_chunk = ChatCompletionChunk(
                                    id=stream_id,
                                    object="chat.completion.chunk",
                                    created=int(
                                        datetime.datetime.now(
                                            datetime.timezone.utc
                                        ).timestamp()
                                    ),
                                    model=message.recipient_identifier,
                                    choices=[
                                        ChunkChoice(
                                            index=0,
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
            # (shared by both pal-agents and legacy paths)
            if collected_content:
                output_message_metadata = Metadata(
                    account_name=account_name,
                    project_name=project.name,
                    agent_id=str(agent_id),
                    user_id=str(user.id),
                    session_id=str(request_message.conversation_id),
                    testing=testing,
                )

                full_response = "".join(collected_content)

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

                # Use add_message_to_conversation with the known conversation_id
                # instead of create_message which does a lookup that can find
                # the wrong conversation when multiple active conversations exist
                await message_repo.add_message_to_conversation(
                    conversation_id=request_conversation_id,
                    message_body=response_message.to_dict(),
                )

                await session.refresh(user, attribute_names=["id"])

                # Memory ingestion for pal-agents flow (fire-and-forget)
                # Only triggers for pal-agents projects; agno agents are unaffected
                if use_pal_agents:
                    # Use early-captured values to avoid SQLAlchemy lazy load issues
                    asyncio.create_task(
                        get_ingestion_service().ingest_interaction(
                            account_id=str(project_account_id),
                            user_id=str(ingestion_user_id),
                            conversation_id=str(request_conversation_id),
                            user_message=current_message,
                            assistant_message=full_response,
                        )
                    )

        except asyncio.CancelledError:
            logger.debug("[MessageService] Stream cancelled (client disconnect)")
            return

        except Exception as e:
            # Log error and return a single error chunk
            logger.exception(f"Error in get_chat_response_stream: {e}")
            error_message = ChatCompletionChunk(
                id=stream_id,
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
