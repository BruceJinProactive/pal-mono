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

import db
from api.routes.chat.chat import chat_router
from api.schemas.chat.message import AuthorType, Channel, Message, Metadata, TextObject
from api.schemas.error.error import ErrorResponse
from services.message_service import get_chat_response_async, get_chat_response_stream
from utils.log import logger


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

    # If request.model is "default", use gpt-4o, otherwise just print the model
    if request.model == "default":
        model = "gpt-4o"
        logger.info(f"Using default model: {model}")
        return await chat_completions_oai(request, session)
    else:
        logger.info(f"Requested model: {request.model}")
        model = request.model
        return await chat_completions_agno(request, model, session)


async def chat_completions_agno(
    request: ChatCompletionRequest,
    model: str,
    session: AsyncSession = Depends(db.get_db_async),
):
    # Log the request
    logger.info(f"Agno chat completions request: {json.dumps(request.model_dump())}")

    try:
        # Convert request format to a Message object
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

        # Convert model to a JSON structure for caller identification
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
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Handle case where model isn't valid JSON
            raise Exception(f"Error parsing model as JSON: {e}. Using defaults.")

        # Create a Message object
        message = Message(
            author_type=AuthorType.USER,
            sender_identifier=sender_identifier,
            recipient_identifier=recipient_identifier,
            channel=Channel.VOICE,
            broker=None,
            text=TextObject(body=content),
            metadata=Metadata(
                testing=False,
                # Add any other metadata needed
            ),
        )

        if request.stream:
            # Use streaming response
            async def generate_stream():
                try:
                    try:
                        # Log stream start
                        logger.info(f"Starting streaming response for model={model}")

                        response_stream = await get_chat_response_stream(
                            session=session, message=message
                        )
                    except Exception as es:
                        # Log the error and create a fallback response
                        logger.error(
                            f"Error getting streaming response from agent: {str(es)}"
                        )
                        # Create a fallback error message that follows ChatCompletionChunk format
                        fallback_id = f"chatcmpl-{uuid.uuid4().hex}"
                        fallback_content = "I apologize, but I'm unable to process your request at the moment. Please try again later."

                        # Create a fallback stream chunk
                        fallback_chunk = {
                            "id": fallback_id,
                            "object": "chat.completion.chunk",
                            "created": int(
                                datetime.datetime.now(datetime.timezone.utc).timestamp()
                            ),
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "role": "assistant",
                                        "content": fallback_content,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                        yield f"data: {json.dumps(fallback_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    if response_stream:
                        chunk_count = 0
                        async for chunk in response_stream:
                            chunk_count += 1

                            # Only log first chunk to avoid excessive logging
                            if chunk_count == 1:
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
                                                        if hasattr(
                                                            choice.delta, "content"
                                                        )
                                                        else None
                                                    ),
                                                },
                                                "finish_reason": choice.finish_reason,
                                            }
                                            for choice in chunk.choices
                                        ],
                                    }
                                logger.info(
                                    f"First stream chunk: {json.dumps(chunk_data)}"
                                )

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

                            yield f"data: {json.dumps(chunk_data)}\n\n"

                        # Log completion of stream
                        logger.info(
                            f"Completed streaming response after {chunk_count} chunks."
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

        # Define fallback content up front to ensure it's always defined
        fallback_content = "I apologize, but I'm unable to process your request at the moment. Please try again later."

        try:
            # Non-streaming response
            response_messages = await get_chat_response_async(
                session=session, message=message
            )

            if not response_messages:
                # Fall back to a default response if no messages are returned
                logger.warning(
                    f"No response messages from agent for model {model}, using fallback"
                )
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
        response_data = {
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
    request: ChatCompletionRequest, session: AsyncSession = Depends(db.get_db_async)
):
    # Log the complete request as JSON
    logger.info(f"Chat completions request: {json.dumps(request.model_dump())}")

    try:
        # Get OpenAI API key from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not found")
            raise ValueError("OPENAI_API_KEY environment variable is required")

        openai_client = openai.OpenAI(api_key=api_key)

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
                    # Call OpenAI API with streaming
                    # Use type: ignore to bypass type checking issues with OpenAI SDK
                    stream = openai_client.chat.completions.create(  # type: ignore
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

                    # Stream the results
                    chunk_count = 0
                    for chunk in stream:
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
                            logger.info(f"First stream chunk: {json.dumps(chunk_data)}")

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
        response = openai_client.chat.completions.create(  # type: ignore
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
