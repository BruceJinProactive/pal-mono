import asyncio
import datetime
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from urlextract import URLExtract

import db
from agent.model import ModelOptions, call_llm_default
from api.routes.chat._utils import create_url_filter
from api.routes.chat.chat import chat_router
from api.schemas.chat.message import AuthorType, Broker, Message, Metadata, TextObject
from api.schemas.error.error import ErrorResponse
from db.tables.types import Channel
from services.message_service import get_chat_response_stream
from services.relay_service import send_message
from utils.log import logger
from utils.otel import increment_counter, record_duration
from utils.request_context import RequestContext

_CHAT_COMPLETIONS_TURN_BRIDGE_METRIC = "chat.completions.turn.bridge"
_CHAT_COMPLETIONS_TURN_BRIDGE_DURATION_METRIC = "chat.completions.turn.bridge.duration"


def resolve_outbound_tn(sender_tn: str, broker: Broker) -> str:
    """Map internal routing TN to real outbound TN. Passthrough for non-PizzaCloud.

    Reads PIZZACLOUD_OUTBOUND_TN_MAP env var on every call so updates
    take effect without redeployment.

    Raises ValueError if the mapping is misconfigured or the sender TN
    is not found — PizzaCloud SMS must not be sent from an unmapped TN.
    """
    if broker != Broker.PIZZACLOUD:
        return sender_tn
    raw = os.environ.get("PIZZACLOUD_OUTBOUND_TN_MAP", "")
    if not raw:
        raise ValueError(
            f"PIZZACLOUD_OUTBOUND_TN_MAP env var is not set; "
            f"cannot resolve outbound TN for {sender_tn}"
        )
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("PIZZACLOUD_OUTBOUND_TN_MAP is not valid JSON")
    if not isinstance(mapping, dict):
        raise ValueError("PIZZACLOUD_OUTBOUND_TN_MAP must be a JSON object")
    resolved = mapping.get(sender_tn)
    if resolved is None:
        raise ValueError(
            f"No outbound TN mapping found for {sender_tn} in "
            f"PIZZACLOUD_OUTBOUND_TN_MAP"
        )
    if not isinstance(resolved, str):
        raise ValueError(f"Outbound TN mapping value for {sender_tn} is not a string")
    logger.info(f"Outbound TN override: ***{sender_tn[-4:]} -> ***{resolved[-4:]}")
    return resolved


# Request model with FastAPI validation
class ChatCompletionRequest(BaseModel):
    model: str
    message: Optional[str] = Field(default=None, description="The message to process")
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = True
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None


def _record_chat_turn_bridge_outcome(
    outcome: str,
    reason: str,
    start_time: datetime.datetime,
    framework: str,
) -> None:
    """Record the voice chat bridge SLO outcome."""
    # Migration label: remove once Agno is gone and dashboards no longer split by backend.
    attributes = {
        "outcome": outcome,
        "reason": reason,
        "framework": framework,
    }
    increment_counter(_CHAT_COMPLETIONS_TURN_BRIDGE_METRIC, attributes=attributes)
    record_duration(
        _CHAT_COMPLETIONS_TURN_BRIDGE_DURATION_METRIC,
        start_time,
        attributes=attributes,
    )


@asynccontextmanager
async def _managed_session(
    session: AsyncSession | None,
) -> AsyncIterator[AsyncSession]:
    if session is not None:
        yield session
        return

    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as managed_session:
        try:
            yield managed_session
        except Exception:
            await managed_session.rollback()
            raise


@chat_router.post(
    "/completions",
    response_model=Dict[str, Any],  # Use a generic dict response model
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat_completions(request: ChatCompletionRequest):
    request_context = RequestContext()
    model = request.model
    return await chat_completions_agno(request, model, request_context)


def _extract_content_from_request(request: ChatCompletionRequest) -> str:
    """Extract content from the request object."""
    if request.messages:
        # Build a message from the messages array
        user_messages = []
        for message in reversed(request.messages):
            if message.get("role") != "user":
                break
            user_messages.append(message)

        user_messages_content = [
            msg.get("content", "") for msg in reversed(user_messages)
        ]
        if not user_messages_content:
            logger.error(
                f"[chat_completions] Missing user inputs for the current turn: {request.messages[-1]}"
            )
            # Sending a fake inputs, asking agent to repeat his last response so the conversation can continue
            content = "Could you say it again?"
        else:
            content = " ".join(user_messages_content)
    elif request.message:
        content = request.message
    else:
        raise ValueError("Either 'message' or 'messages' must be provided")

    return content


def _parse_caller_info(
    model: str,
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None]:
    """Parse model string to extract voice caller context."""
    try:
        # Parse model as JSON, it could be a string representation of JSON
        caller_info = json.loads(model) if isinstance(model, str) else model

        # Validate required fields
        if (
            "sender_identifier" not in caller_info
            or "recipient_identifier" not in caller_info
        ):
            logger.warning(f"Missing required fields in caller_info: {caller_info}")
            # Use defaults if missing
            sender_identifier = caller_info.get("sender_identifier", "user")
            recipient_identifier = caller_info.get(
                "recipient_identifier",
                model if isinstance(model, str) else "default",
            )
        else:
            sender_identifier = caller_info["sender_identifier"]
            recipient_identifier = caller_info["recipient_identifier"]

        # Extract call_id for voice calls
        call_id = caller_info.get("call_id")

        # Extract LiveKit context for LiveKit voice calls
        room_name = caller_info.get("room_name")
        participant_identity = caller_info.get("participant_identity")

        # SIP provider: "pizzacloud", "twilio", or "snet"
        sip_provider = caller_info.get("sip_provider")
        language = caller_info.get("language")

        return (
            sender_identifier,
            recipient_identifier,
            call_id,
            room_name,
            participant_identity,
            sip_provider,
            language,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        # Handle case where model isn't valid JSON
        raise Exception(f"Error parsing model as JSON: {e}.")


def _convert_chunk_to_dict(chunk):
    """Convert a chunk to a dictionary representation."""
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()

    # Fall back to dict representation
    return {
        "id": chunk.id,
        "object": chunk.object,
        "created": chunk.created,
        "model": chunk.model,
        "choices": [
            {
                "index": choice.index,
                "delta": {
                    "role": (
                        choice.delta.role if hasattr(choice.delta, "role") else None
                    ),
                    "content": (
                        choice.delta.content
                        if hasattr(choice.delta, "content")
                        else None
                    ),
                },
                "finish_reason": choice.finish_reason,
            }
            for choice in chunk.choices
        ],
    }


def _extract_item_recap_from_sms_followup_event(event: Dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    item_recap = payload.get("item_recap")
    if not isinstance(item_recap, str):
        return None

    item_recap = item_recap.strip()
    return item_recap or None


def _create_fallback_chunk(model: str, content: str) -> dict:
    """Create a fallback chunk for streaming responses."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }


def is_invalid_url(url_string: str) -> bool:
    """
    Check if a URL string is invalid based on common false positive patterns, e.g. moment.It
    Returns True if the URL should be rejected.
    """
    # Common valid URL extensions/TLDs
    valid_extensions = {
        "com",
        "org",
        "net",
        "us",
        "edu",
        "info",
        "biz",
        "app",
        "dev",
        "tech",
        "store",
        "online",
        "media",
        "ai",
    }

    # Check if it's exactly two words with a dot
    parts = url_string.split(".")
    if len(parts) == 2:
        first_word, second_word = parts

        # Both parts should be alphabetic for this check
        if first_word.isalpha() and second_word.isalpha():
            # If second word is not a valid extension, it's invalid
            if second_word.lower() not in valid_extensions:
                return True

    return False


async def _send_urls_via_sms(
    collected_content: List[str],
    sender_identifier: str,
    recipient_identifier: str,
    call_id: Optional[str] = None,
    sip_provider: Optional[str] = None,
    item_recap: str | None = None,
) -> None:
    """
    Extract URLs from collected content and send them via SMS if found.
    Uses OpenAI to generate a short summary that includes the URLs.

    Creates its own database session for persistence to avoid using request-scoped sessions
    in background tasks.

    Args:
        collected_content: List of content strings to search for URLs
        sender_identifier: The sender identifier for the relay message
        recipient_identifier: The recipient identifier for the relay message
        call_id: Call ID for looking up the conversation (for voice calls)
        item_recap: Optional item recap context from pal-agents sms_followup events.
    """
    try:
        if not sender_identifier or not recipient_identifier:
            logger.error("Invalid sender or recipient identifier provided")
            return

        # Check for URLs in the collected content
        full_content = "".join(collected_content)

        # Use URLExtract to find URLs
        extractor = URLExtract()
        potential_urls: List[str] = extractor.find_urls(full_content)  # type: ignore

        # Filter out invalid URLs (false positives)
        urls = [url for url in potential_urls if not is_invalid_url(url)]

        if urls:
            logger.debug(f"Found URLs in response: {urls}")

            # Check for multiple URLs and log error if found
            if len(urls) > 1:
                logger.warning(
                    f"Multiple URLs found in content: {urls}. Only using the first URL: {urls[0]}"
                )

            first_url = urls[0]
            item_recap_context = (
                f"\nOrder item recap context:\n{item_recap}\n" if item_recap else ""
            )
            item_recap_instruction = (
                """
        - If order item recap context is provided, use it for the item recap
        - Format item quantities in parentheses at the start of each item line, e.g. "- (1) Large pizza" """
                if item_recap
                else ""
            )

            try:
                # Create a prompt for summarization
                prompt = f"""
Please create a short, SMS-friendly summary of the following content. DO NOT write out or paraphrase the full URL. Instead, insert the EXACT placeholder [INSERT_URL_HERE] where we will insert the link manually ourselves.

Content:
{full_content}
{item_recap_context}

CRITICAL INSTRUCTION: You MUST use the exact text [INSERT_URL_HERE] as the placeholder. Do NOT use variations like [here], [click here], [link], or any other text. Use EXACTLY: [INSERT_URL_HERE]

Instructions:
- If the content is about a pending-payment order:
    - Start with a sentence stating the order status (e.g., "Your order is pending")
    - Include a section titled "Order Summary:" **if any order details are present** (items, subtotal, sales tax, discount, order total)
{item_recap_instruction}
        - List each ordered item on a new line, prefixed with a dash (-) and using the exact item name
        - Include any of the following breakdown lines if they are explicitly present in the content: Subtotal, Sales Tax, Discount, Order Total
    - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Pay here: [INSERT_URL_HERE]")
    - **Do not fabricate missing details**; only include what is explicitly in the content
- If the content is not about a pending-payment order:
    - Provide a clear, short summary of the main point
    - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Order here: [INSERT_URL_HERE]")

- Use line breaks for clarity
- REMEMBER: Use the EXACT placeholder [INSERT_URL_HERE] - no variations!
"""
                chat_complete_params = {
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,  # Lower temperature for more consistent placeholder usage
                    "max_tokens": 100,
                }
                response = await call_llm_default(
                    model_option=ModelOptions.GPT_4O, params=chat_complete_params
                )

                if (
                    not response.choices
                    or not response.choices[0]
                    or not response.choices[0].message
                ):
                    raise RuntimeError(
                        f"No response from LLM: {response.model_dump_json()}"
                    )
                summary_content = response.choices[0].message.content
                logger.debug(
                    f"Generated SMS summary: {summary_content} from original content {full_content}"
                )

            except Exception as e:
                logger.error(f"Error generating SMS summary with OpenAI: {str(e)}")
                # Fall back to original content if OpenAI fails
                summary_content = full_content

            if not summary_content:
                logger.error(
                    f"The summarized content is empty from original content {full_content}"
                )
            else:
                # Replace placeholder if found, otherwise append payment link
                if "[INSERT_URL_HERE]" in summary_content:
                    summary_content = summary_content.replace("[INSERT_URL_HERE]", first_url)  # type: ignore
                else:
                    summary_content = summary_content + f"\n{first_url}"  # type: ignore

                logger.debug(f"Post processed SMS summary to {summary_content}")

                # Resolve broker from SIP provider
                try:
                    broker = Broker(sip_provider) if sip_provider else Broker.TWILIO
                except ValueError:
                    broker = Broker.TWILIO

                # Resolve outbound TN — for brokers like PizzaCloud, the
                # internal routing TN may differ from the real SMS-authorized
                # store TN.
                outbound_sender = resolve_outbound_tn(recipient_identifier, broker)

                # Create a Message object and send it via relay service
                relay_message = Message(
                    author_type=AuthorType.AGENT,
                    sender_identifier=outbound_sender,
                    recipient_identifier=sender_identifier,
                    channel=Channel.SMS,
                    broker=broker,
                    text=TextObject(body=summary_content),
                    metadata=Metadata(testing=False),
                )
                # Run send_message in thread pool to avoid blocking event loop
                # (boto3 stepfunctions.start_execution is blocking I/O)
                send_result = await asyncio.to_thread(send_message, relay_message)
                logger.debug(f"Relay service result: {send_result}")

                # Persist the outbound SMS message to the conversation
                # Create own session since this runs in a background task
                if send_result.get("status") == "scheduled" and call_id:
                    try:
                        # Create a new async session for background task
                        from db.session import AsyncSessionLocal

                        async with AsyncSessionLocal() as bg_session:
                            # Look up conversation by call_id
                            conv_repo = db.ConversationRepositoryAsync(bg_session)
                            conversation = await conv_repo.get_conversation_by_call_id(
                                call_id
                            )

                            if conversation:
                                # Store conversation_id before commit to avoid MissingGreenlet error
                                # After commit(), SQLAlchemy expires objects; accessing conversation.id
                                # would trigger a lazy load which fails in async context
                                conversation_id = conversation.id

                                message_repo = db.MessageRepositoryAsync(bg_session)
                                await message_repo.add_message_to_conversation(
                                    conversation_id=conversation_id,
                                    message_body=relay_message.to_dict(),
                                )
                                await bg_session.commit()
                                logger.debug(
                                    "Persisted outbound payment link SMS",
                                    extra={
                                        "call_id": call_id,
                                        "conversation_id": str(conversation_id),
                                    },
                                )
                            else:
                                logger.warning(
                                    f"No conversation found for call_id {call_id}, "
                                    "skipping message persistence"
                                )
                    except Exception as persist_err:
                        # Fail silently - SMS delivery takes priority over persistence
                        logger.error(
                            f"Failed to persist payment link SMS: {persist_err}",
                            extra={"call_id": call_id},
                        )
    except asyncio.CancelledError:
        # Task was cancelled, log and exit gracefully
        logger.debug(
            "SMS sending task cancelled (likely due to client disconnect)",
            extra={
                "sender_identifier": sender_identifier,
                "recipient_identifier": recipient_identifier,
            },
        )
    except Exception as e:
        # Catch all other errors to prevent background task from crashing
        logger.error(
            f"Unexpected error in _send_urls_via_sms: {e}",
            extra={
                "sender_identifier": sender_identifier,
                "recipient_identifier": recipient_identifier,
            },
        )


async def chat_completions_agno(
    request: ChatCompletionRequest,
    model: str,
    request_context: RequestContext,
    session: AsyncSession | None = None,
):
    # Guardrail: Ensure streaming mode is always used
    if not request.stream:
        logger.error("Non-streaming mode is not supported. Streaming mode is required.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="STREAMING_REQUIRED",
                error_message="This API only supports streaming mode. Please set 'stream': true in your request.",
            ).model_dump(),
        )

    try:
        # Extract content from request
        content = _extract_content_from_request(request)

        # Parse caller info from model
        (
            sender_identifier,
            recipient_identifier,
            call_id,
            room_name,
            participant_identity,
            sip_provider,
            language,
        ) = _parse_caller_info(model)

        # Create a Message object
        message = Message(
            author_type=AuthorType.USER,
            sender_identifier=sender_identifier,
            recipient_identifier=recipient_identifier,
            channel=Channel.VOICE,
            broker=None,
            text=TextObject(body=content),
            metadata=Metadata(testing=False),
        )

        fallback_content = "I apologize, but I'm unable to process your request at the moment. Please try again later."

        async def generate_stream() -> AsyncIterator[str]:
            async with _managed_session(session) as active_session:
                bridge_outcome_recorded = False
                bridge_had_content = False
                bridge_error_chunk_seen = False
                bridge_framework = "unknown"

                def record_bridge_outcome(outcome: str, reason: str) -> None:
                    nonlocal bridge_outcome_recorded
                    if bridge_outcome_recorded:
                        return
                    bridge_outcome_recorded = True
                    _record_chat_turn_bridge_outcome(
                        outcome,
                        reason,
                        request_context.request_time,
                        bridge_framework,
                    )

                try:
                    record_duration(
                        "chat.streaming.start.duration", request_context.request_time
                    )

                    sms_item_recap: str | None = None

                    def collect_stream_event(event: Dict[str, Any]) -> None:
                        nonlocal bridge_framework, sms_item_recap
                        if event.get("type") == "bridge_framework":
                            framework = event.get("framework")
                            if isinstance(framework, str) and framework:
                                bridge_framework = framework
                            return
                        if event.get("type") != "sms_followup" or sms_item_recap:
                            return
                        sms_item_recap = _extract_item_recap_from_sms_followup_event(
                            event
                        )

                    def collect_bridge_framework(framework: str) -> None:
                        nonlocal bridge_framework
                        if framework:
                            bridge_framework = framework

                    response_stream = await get_chat_response_stream(
                        session=active_session,
                        message=message,
                        request_context=request_context,
                        call_id=call_id,
                        room_name=room_name,
                        participant_identity=participant_identity,
                        sip_provider=sip_provider,
                        language=language,
                        event_collector=collect_stream_event,
                        framework_collector=collect_bridge_framework,
                    )

                    collected_content = []
                    if response_stream:
                        chunk_count = 0
                        url_filter = create_url_filter()
                        record_duration(
                            "chat.streaming.first_chunk.wait",
                            request_context.request_time,
                        )

                        # Stream chunks immediately as they arrive
                        async for chunk in response_stream:
                            chunk_count += 1
                            chunk_data = _convert_chunk_to_dict(chunk)

                            choices = chunk_data.get("choices", [])
                            content = (
                                choices[0].get("delta", {}).get("content", "")
                                if choices
                                else ""
                            )
                            finish_reason = (
                                choices[0].get("finish_reason") if choices else None
                            )
                            if finish_reason == "stop" and not content:
                                bridge_error_chunk_seen = True

                            # Collect content for URL extraction later
                            collected_content.append(content)

                            # Apply URL filtering to this chunk
                            filtered_content = url_filter.filter_content(content)

                            # Yield chunk immediately if content passes filter
                            if filtered_content is not None:
                                if filtered_content.strip():
                                    bridge_had_content = True
                                if (
                                    chunk_data.get("choices")
                                    and len(chunk_data["choices"]) > 0
                                ):
                                    if "delta" in chunk_data["choices"][0]:
                                        chunk_data["choices"][0]["delta"][
                                            "content"
                                        ] = filtered_content

                                # Track TTFT on first chunk
                                if chunk_count == 1:
                                    time_diff = (
                                        datetime.datetime.now(datetime.timezone.utc)
                                        - request_context.request_time
                                    ).total_seconds() * 1000
                                    logger.debug(
                                        f"[ChatCompletions] TTFT is {time_diff}",
                                        extra={
                                            "recipient_identifier": recipient_identifier,
                                            "sender_identifier": sender_identifier,
                                        },
                                    )
                                    record_duration(
                                        "chat.streaming.first_chunk.sent.duration",
                                        request_context.request_time,
                                    )

                                # Stream chunk to client immediately
                                yield f"data: {json.dumps(chunk_data)}\n\n"

                        # Log completion of stream
                        logger.info(
                            f"Completed streaming response after {chunk_count} chunks."
                        )

                        # Send URLs via SMS if any are found in the collected content
                        # Note: _send_urls_via_sms creates its own DB session for persistence
                        await _send_urls_via_sms(
                            collected_content,
                            sender_identifier,
                            recipient_identifier,
                            call_id=call_id,
                            sip_provider=sip_provider,
                            item_recap=sms_item_recap,
                        )

                        if bridge_error_chunk_seen:
                            if bridge_had_content:
                                record_bridge_outcome(
                                    "failure", "response_persist_failed"
                                )
                            else:
                                record_bridge_outcome(
                                    "failure", "request_persist_failed"
                                )
                        elif bridge_had_content:
                            record_bridge_outcome("success", "completed")
                        else:
                            record_bridge_outcome("failure", "empty_output")
                        yield "data: [DONE]\n\n"
                    else:
                        record_bridge_outcome("failure", "empty_output")

                except asyncio.CancelledError:
                    logger.debug(
                        "[ChatCompletions] Stream cancelled (client disconnect)"
                    )
                    record_bridge_outcome("failure", "client_cancelled")
                    return

                except Exception as e:
                    logger.error(f"Error in streaming response: {str(e)}")
                    fallback_chunk = _create_fallback_chunk(model, fallback_content)
                    yield f"data: {json.dumps(fallback_chunk)}\n\n"
                    record_bridge_outcome("failure", "fallback_response")
                    yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # For nginx
            },
        )

    except ValueError as ve:
        logger.error(f"Error validating agno chat completion request: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        logger.error(f"Error processing agno chat completion request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the request",
            ).model_dump(),
        )
