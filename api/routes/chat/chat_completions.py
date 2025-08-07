import datetime
import json
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from urlextract import URLExtract

import db
from api.routes.chat._utils import create_url_filter
from api.routes.chat.chat import chat_router
from api.schemas.chat.message import AuthorType, Broker, Message, Metadata, TextObject
from api.schemas.error.error import ErrorResponse
from db.tables.types import Channel
from services.llm_service import call_llm_default
from services.llm_service.schema import ModelOptions
from services.message_service import get_chat_response_async, get_chat_response_stream
from services.relay_service import send_message
from utils.dd import send_dd_histogram_metrics
from utils.log import logger
from utils.request_context import RequestContext


# Define message types that match the OpenAI API
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "function", "tool"]
    content: str
    name: Optional[str] = None


# Request model with FastAPI validation
class ChatCompletionRequest(BaseModel):
    model: str
    message: Optional[str] = Field(default=None, description="The message to process")
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None


@chat_router.post(
    "/completions",
    response_model=Dict[str, Any],  # Use a generic dict response model
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat_completions(
    request: ChatCompletionRequest, session: AsyncSession = Depends(db.get_db_async)
):
    request_context = RequestContext()
    logger.info(f"Requested model: {request.model}")
    model = request.model
    return await chat_completions_agno(request, model, request_context, session)


def _extract_content_from_request(request: ChatCompletionRequest) -> str:
    """Extract content from the request object."""
    if request.messages:
        # Build a message from the messages array
        user_messages = [
            msg.get("content", "")
            for msg in request.messages
            if msg.get("role") == "user"
        ]
        if not user_messages:
            content = request.messages[-1].get("content", "")
        else:
            content = user_messages[-1]
        logger.debug(
            f"chat_completions_agno request has messages {user_messages}, and message:{request.message}"
        )
    elif request.message:
        content = request.message
    else:
        raise ValueError("Either 'message' or 'messages' must be provided")

    return content


def _parse_caller_info(model: str) -> tuple[str, str]:
    """Parse model string to extract sender and recipient identifiers."""
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

        return sender_identifier, recipient_identifier
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


def _create_response_data(model: str, content: str, is_chunk: bool = False) -> dict:
    """Create a standard response data object."""
    content_key = "delta" if is_chunk else "message"
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion" if not is_chunk else "chat.completion.chunk",
        "created": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                f"{content_key}": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop" if not is_chunk else None,
            }
        ],
    }
    if not is_chunk:
        response["usage"] = {
            "prompt_tokens": 0,  # We don't track these
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    return response


async def _send_urls_via_sms(
    collected_content: List[str],
    sender_identifier: str,
    recipient_identifier: str,
) -> None:
    """
    Extract URLs from collected content and send them via SMS if found.
    Uses OpenAI to generate a short summary that includes the URLs.

    Args:
        collected_content: List of content strings to search for URLs
        sender_identifier: The sender identifier for the relay message
        recipient_identifier: The recipient identifier for the relay message
    """
    if not sender_identifier or not recipient_identifier:
        logger.error("Invalid sender or recipient identifier provided")
        return

    # Check for URLs in the collected content
    full_content = "".join(collected_content)

    # Use URLExtract to find URLs
    extractor = URLExtract()
    urls = extractor.find_urls(full_content)

    if urls:
        logger.debug(f"Found URLs in response: {urls}")

        # Check for multiple URLs and log error if found
        if len(urls) > 1:
            logger.warning(
                f"Multiple URLs found in content: {urls}. Only using the first URL: {urls[0]}"
            )

        first_url = urls[0]

        try:
            # Create a prompt for summarization
            prompt = f"""
Please create a short, SMS-friendly summary of the following content. DO NOT write out or paraphrase the full URL. Instead, insert the EXACT placeholder [INSERT_URL_HERE] where we will insert the link manually ourselves.

Content:
{full_content}

CRITICAL INSTRUCTION: You MUST use the exact text [INSERT_URL_HERE] as the placeholder. Do NOT use variations like [here], [click here], [link], or any other text. Use EXACTLY: [INSERT_URL_HERE]

Instructions:
- If the content is about a pending-payment order:
  - **IMPORTANT: Only include a detailed "Order Summary" if ALL necessary order details (items, subtotal, sales tax, discount, order total) are explicitly available in the provided Content.**
    - If ALL necessary order details ARE available:
        - Start with a sentence stating the order status (e.g., "Your order is pending")
        - Include the title: "Order Summary:"
        - List each ordered item on a new line, prefixed with a dash (-) and using the exact item name
        - Include a breakdown: Subtotal, Sales Tax, Discount, and Order Total, each on its own line
        - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Pay here: [INSERT_URL_HERE]")
    - **If ANY necessary order detail (item names, subtotal, taxes, discount, or order total) is MISSING or incomplete in the Content:**
        - Start with a sentence stating the order status (e.g., "Your order is pending")
        - Provide a **general** call to action including the placeholder [INSERT_URL_HERE] (e.g., "Pay for your order here: [INSERT_URL_HERE]")
        - **DO NOT include a detailed "Order Summary:" section or list individual items/prices if details are missing.**
- If the content is not about a pending-payment order:
  - Provide a clear, short summary of the main point
  - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Order here: [INSERT_URL_HERE]")
- Do not write the actual URL
- Use line breaks for clarity

REMEMBER: Use the EXACT placeholder [INSERT_URL_HERE] - no variations!
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

            # Create a Message object and send it via relay service
            relay_message = Message(
                author_type=AuthorType.AGENT,
                sender_identifier=recipient_identifier,
                recipient_identifier=sender_identifier,
                channel=Channel.SMS,
                broker=Broker.TWILIO,
                text=TextObject(body=summary_content),
                metadata=Metadata(testing=False),
            )
            send_result = send_message(relay_message)
            logger.debug(f"Relay service result: {send_result}")


async def chat_completions_agno(
    request: ChatCompletionRequest,
    model: str,
    request_context: RequestContext,
    session: AsyncSession = Depends(db.get_db_async),
):
    # Log the request
    logger.info(f"Agno chat completions request: {json.dumps(request.model_dump())}")
    try:
        # Extract content from request
        content = _extract_content_from_request(request)

        # Parse caller info from model
        sender_identifier, recipient_identifier = _parse_caller_info(model)

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
        if request.stream:

            async def generate_stream():
                try:
                    # Log stream start
                    logger.info(f"Starting streaming response for model={model}")
                    send_dd_histogram_metrics(
                        "chat_completions.start_streaming", request_context.request_time
                    )

                    response_stream = await get_chat_response_stream(
                        session=session,
                        message=message,
                        request_context=request_context,
                    )

                    collected_content = []
                    if response_stream:
                        chunk_count = 0
                        url_filter = create_url_filter()
                        send_dd_histogram_metrics(
                            "chat_completions.waiting_first_chunk",
                            request_context.request_time,
                            [
                                f"sender_identifier:{sender_identifier}",
                                f"recipient_identifier:{recipient_identifier}",
                            ],
                        )

                        async for chunk in response_stream:
                            chunk_count += 1
                            chunk_data = _convert_chunk_to_dict(chunk)

                            content = (
                                chunk_data.get("choices", [])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            collected_content.append(content)
                            filtered_content = url_filter.filter_content(content)
                            if filtered_content is not None:
                                # Replace the original content in chunk_data with filtered_content
                                if (
                                    chunk_data.get("choices")
                                    and len(chunk_data["choices"]) > 0
                                ):
                                    if "delta" in chunk_data["choices"][0]:
                                        chunk_data["choices"][0]["delta"][
                                            "content"
                                        ] = filtered_content

                                yield f"data: {json.dumps(chunk_data)}\n\n"

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

                                    send_dd_histogram_metrics(
                                        "chat_completions.sent_first_chunk",
                                        request_context.request_time,
                                        [
                                            f"sender_identifier:{sender_identifier}",
                                            f"recipient_identifier:{recipient_identifier}",
                                        ],
                                    )

                        # Log completion of stream
                        logger.info(
                            f"Completed streaming response after {chunk_count} chunks."
                        )

                        # Send URLs via SMS if any are found in the collected content
                        await _send_urls_via_sms(
                            collected_content, sender_identifier, recipient_identifier
                        )

                        yield "data: [DONE]\n\n"

                except Exception as e:
                    logger.error(f"Error in streaming response: {str(e)}")
                    fallback_chunk = _create_fallback_chunk(model, fallback_content)
                    yield f"data: {json.dumps(fallback_chunk)}\n\n"
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

        try:
            # Non-streaming response
            response_messages = await get_chat_response_async(
                session=session, message=message, request_context=request_context
            )

            if not response_messages:
                # Fall back to a default response if no messages are returned
                logger.warning(
                    f"No response messages from agent for model {model}, using fallback"
                )
                response_messages = []
        except Exception as e:
            # Log the specific error and use a fallback response
            logger.error(f"Error getting response from agent: {str(e)}")
            response_messages = []

        # Extract content from the first message or use fallback
        if response_messages and response_messages[0].text:
            content = response_messages[0].text.body
        else:
            content = fallback_content

        # Create a response similar to OpenAI format
        response_data = _create_response_data(model, content)

        # Log the response
        logger.info(f"Agno chat completions response: {json.dumps(response_data)}")

        return response_data

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
