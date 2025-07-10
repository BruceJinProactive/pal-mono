import asyncio
import datetime
import json
import os
import uuid
from typing import Any, Dict, List, Literal, Optional

import openai
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from urlextract import URLExtract

import db
from api.routes.chat._utils import create_url_filter
from api.routes.chat.chat import chat_router
from api.routes.chat.smart_filler import get_smart_filler_stream
from api.schemas.chat.message import AuthorType, Broker, Message, Metadata, TextObject
from api.schemas.error.error import ErrorResponse
from db.tables.types import Channel
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
    # If request.model is "default", use gpt-4o, otherwise just print the model
    if request.model == "default":
        model = "gpt-4o"
        logger.info(f"Using default model: {model}")
        return await chat_completions_oai(request, request_context, session)
    else:
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


def _create_openai_client() -> openai.AsyncOpenAI:
    """Create and return an OpenAI client with API key validation."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not found")
        raise ValueError("OPENAI_API_KEY environment variable is required")

    return openai.AsyncOpenAI(api_key=api_key)


def _create_response_data(model: str, content: str) -> dict:
    """Create a standard response data object."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,  # We don't track these
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


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
            logger.error(
                f"Multiple URLs found in content: {urls}. Only using the first URL: {urls[0]}"
            )

        first_url = urls[0]

        try:
            # Use OpenAI to generate a short summary with URLs
            openai_client = _create_openai_client()

            # Create a prompt for summarization
            prompt = f"""
Please create a short, SMS-friendly summary of the following content. DO NOT write out or paraphrase the full URL. Instead, insert the placeholder [INSERT_URL_HERE] where the link should go.

Content:
{full_content}

Instructions:
- If the content is about a pending-payment order:
  - Start with a sentence stating the order status (e.g., "Your order is pending")
  - Include the title: "Order Summary:"
  - List each ordered item on a new line, prefixed with a dash (-) and using the exact item name
  - Include a breakdown: Subtotal, Sales Tax, Discount, and Order Total, each on its own line
  - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Pay here: [INSERT_URL_HERE]")
- If the content is not about a pending-payment order:
  - Provide a clear, short summary of the main point
  - End with a call to action including the placeholder [INSERT_URL_HERE] (e.g., "Order here: [INSERT_URL_HERE]")
- Do not write the actual URL
- Use line breaks for clarity
"""

            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
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
            summary_content = summary_content.replace(
                "[INSERT_URL_HERE]", str(first_url)
            )
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
            # Use streaming response
            async def generate_stream():
                try:
                    try:
                        # Log stream start
                        logger.info(f"Starting streaming response for model={model}")
                        send_dd_histogram_metrics(
                            "chat_completions.start_streaming",
                            request_context.request_time,
                            ["path:agno", "streaming:true"],
                        )

                        # Create unified stream that combines filler and response
                        async def create_unified_stream():
                            # Helper function to get first filler chunk
                            async def get_first_filler_chunk():
                                filler_stream = get_smart_filler_stream(content)
                                try:
                                    return (
                                        await filler_stream.__anext__(),
                                        filler_stream,
                                    )
                                except StopAsyncIteration:
                                    return None, None

                            # Helper function to get first response chunk
                            async def get_first_response_chunk():
                                response_stream = await get_chat_response_stream(
                                    session=session,
                                    message=message,
                                    request_context=request_context,
                                )
                                if response_stream:
                                    try:
                                        return (
                                            await response_stream.__anext__(),
                                            response_stream,
                                        )
                                    except StopAsyncIteration:
                                        return None, None
                                return None, None

                            # Start both tasks in parallel - race for first chunks
                            filler_task = asyncio.create_task(get_first_filler_chunk())
                            response_task = asyncio.create_task(
                                get_first_response_chunk()
                            )

                            # Race condition: wait for either first chunk to arrive
                            done, _ = await asyncio.wait(
                                [filler_task, response_task],
                                return_when=asyncio.FIRST_COMPLETED,
                            )

                            if filler_task in done:
                                # Filler first chunk won the race
                                try:
                                    first_filler_chunk, filler_stream = (
                                        await filler_task
                                    )
                                    if first_filler_chunk and filler_stream:
                                        # Yield first filler chunk
                                        yield first_filler_chunk
                                        logger.debug(
                                            "Smart filler won: sent first chunk"
                                        )

                                        # Continue yielding remaining filler chunks
                                        async for filler_chunk in filler_stream:
                                            yield filler_chunk

                                        logger.debug("Completed smart filler streaming")
                                except Exception as e:
                                    logger.warning(f"Error in smart filler stream: {e}")

                                # Now wait for response stream and yield its chunks
                                first_response_chunk, response_stream = (
                                    await response_task
                                )
                                if first_response_chunk:
                                    yield first_response_chunk
                                if response_stream:
                                    async for chunk in response_stream:
                                        yield chunk
                            else:
                                # Response first chunk won the race - cancel filler
                                filler_task.cancel()
                                logger.debug("Main response won: skipping filler")

                                first_response_chunk, response_stream = (
                                    await response_task
                                )
                                if first_response_chunk:
                                    yield first_response_chunk
                                if response_stream:
                                    async for chunk in response_stream:
                                        yield chunk

                        response_stream = create_unified_stream()
                    except Exception as es:
                        # Log the error and create a fallback response
                        logger.error(
                            f"Error getting streaming response from agent: {str(es)}"
                        )
                        fallback_chunk = _create_fallback_chunk(model, fallback_content)
                        yield f"data: {json.dumps(fallback_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    collected_content = []
                    if response_stream:
                        chunk_count = 0
                        url_filter = create_url_filter()
                        send_dd_histogram_metrics(
                            "chat_completions.waiting_first_chunk",
                            request_context.request_time,
                            [
                                "path:agno",
                                "streaming:true",
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
                            # Only log first chunk to avoid excessive logging
                            if chunk_count == 1:
                                logger.debug(
                                    f"First stream chunk: {json.dumps(chunk_data)}"
                                )
                                send_dd_histogram_metrics(
                                    "chat_completions.received_first_chunk",
                                    request_context.request_time,
                                    [
                                        "path:agno",
                                        "streaming:true",
                                        f"sender_identifier:{sender_identifier}",
                                        f"recipient_identifier:{recipient_identifier}",
                                    ],
                                )
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
                                            "path:agno",
                                            "streaming:true",
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
                    error_data = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "code": 500,
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
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


async def chat_completions_oai(
    request: ChatCompletionRequest,
    request_context: RequestContext,
    session: AsyncSession = Depends(db.get_db_async),
):
    # Log the complete request as JSON
    logger.info(f"Chat completions request: {json.dumps(request.model_dump())}")

    try:
        openai_client = _create_openai_client()

        # Convert request format to proper OpenAI format using structured types
        if request.messages:
            # Convert dictionaries to proper message objects
            openai_messages = []
            for msg in request.messages:
                role = msg.get("role", "user")
                # Ensure role is one of the allowed values
                if role not in ["system", "user", "assistant", "function", "tool"]:
                    role = "user"  # Default to user if invalid role

                content = msg.get("content", "")
                if not content:
                    content = " "  # Ensure content is never empty

                openai_messages.append({"role": role, "content": content})
        elif request.message:
            openai_messages = [{"role": "user", "content": request.message}]
        else:
            raise ValueError("Either 'message' or 'messages' must be provided")

        # Always use GPT-4o regardless of what's in the request
        model = "gpt-4o"  # Ignore request.model and always use GPT-4o

        if request.stream:

            async def generate_stream():
                try:
                    send_dd_histogram_metrics(
                        "chat_completions.start_streaming",
                        request_context.request_time,
                        ["path:oai", "streaming:true"],
                    )

                    # Call OpenAI API with streaming
                    # Use type: ignore to bypass type checking issues with OpenAI SDK
                    stream = await openai_client.chat.completions.create(  # type: ignore
                        model=model,
                        messages=openai_messages,  # type: ignore
                        temperature=request.temperature,
                        top_p=request.top_p,
                        n=request.n,
                        max_tokens=request.max_tokens,
                        presence_penalty=request.presence_penalty,
                        frequency_penalty=request.frequency_penalty,
                        stream=True,
                    )

                    # Log stream start
                    logger.info(f"Starting streaming response for model={model}")
                    send_dd_histogram_metrics(
                        "chat_completions.waiting_first_chunk",
                        request_context.request_time,
                        ["path:oai", "streaming:true"],
                    )

                    # Stream the results
                    chunk_count = 0
                    async for chunk in stream:
                        chunk_count += 1
                        if hasattr(chunk, "model_dump"):
                            chunk_data = chunk.model_dump()
                        else:
                            # Fall back to dict representation
                            chunk_data = {
                                "id": chunk.id,
                                "object": chunk.object,
                                "created": chunk.created,
                                "model": chunk.model,
                                "choices": [
                                    {
                                        "index": choice.index,
                                        "delta": {
                                            "role": (
                                                choice.delta.role
                                                if hasattr(choice.delta, "role")
                                                else None
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

                        # Only log first chunk to avoid excessive logging
                        if chunk_count == 1:
                            logger.debug(
                                f"First stream chunk: {json.dumps(chunk_data)}"
                            )
                            send_dd_histogram_metrics(
                                "chat_completions.received_first_chunk",
                                request_context.request_time,
                                ["path:oai", "streaming:true"],
                            )
                        yield f"data: {json.dumps(chunk_data)}\n\n"

                    # Log completion of stream
                    logger.info(
                        f"Completed streaming response after {chunk_count} chunks"
                    )
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    logger.error(f"Error in streaming response: {str(e)}")
                    error_data = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                            "code": 500,
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
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

        # Non-streaming response
        # Use type: ignore to bypass type checking issues with OpenAI SDK
        response = await openai_client.chat.completions.create(  # type: ignore
            model=model,
            messages=openai_messages,  # type: ignore
            temperature=request.temperature,
            top_p=request.top_p,
            n=request.n,
            max_tokens=request.max_tokens,
            presence_penalty=request.presence_penalty,
            frequency_penalty=request.frequency_penalty,
        )

        # Convert response to dict
        if hasattr(response, "model_dump"):
            response_data = response.model_dump()
        else:
            # Fall back to manual conversion
            response_data = {
                "id": response.id,
                "object": response.object,
                "created": response.created,
                "model": response.model,
                "choices": [
                    {
                        "index": choice.index,
                        "message": {
                            "role": choice.message.role,
                            "content": choice.message.content,
                        },
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in response.choices
                ],
                "usage": (
                    {
                        "prompt_tokens": (
                            response.usage.prompt_tokens if response.usage else 0
                        ),
                        "completion_tokens": (
                            response.usage.completion_tokens if response.usage else 0
                        ),
                        "total_tokens": (
                            response.usage.total_tokens if response.usage else 0
                        ),
                    }
                    if hasattr(response, "usage")
                    else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                ),
            }

        # Log the complete response as JSON
        logger.info(f"Chat completions response: {json.dumps(response_data)}")
        return response_data

    except ValueError as ve:
        logger.error(f"Error validating chat completion request: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).model_dump(),
        )
    except Exception as e:
        logger.error(f"Error processing chat completion request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the request",
            ).model_dump(),
        )
