from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from phi.run.response import RunResponse
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.endpoints import endpoints
from api.schemas.chat.chat import ChatRequest, ChatResponse, ErrorResponse
from api.schemas.chat.message import Message, TextObject
from services.message_service import get_chat_response_async, get_chat_response_stream
from services.relay_service import send_messages
from utils.log import logger

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])


@chat_router.post(
    "/",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest, session: AsyncSession = Depends(db.get_db_async)):
    try:
        # Process the message
        logger.info(f"Received message: {request.message}")

        if request.stream:

            async def generate() -> AsyncIterator[str]:
                try:
                    response_stream = await get_chat_response_stream(
                        session=session, message=request.message
                    )

                    if response_stream:
                        async for chunk in response_stream:
                            if isinstance(chunk, RunResponse):
                                content = chunk.get_content_as_string()
                                if content:
                                    yield f"data: {content}\n\n"
                            elif isinstance(chunk, tuple):
                                yield f"data: {chunk[0]}\n\n"
                            elif chunk:
                                if not isinstance(chunk, (str, int, float, bool)):
                                    logger.warning(
                                        f"Unexpected chunk type: {type(chunk)}"
                                    )
                                    continue
                                content = str(chunk)
                                logger.debug(f"Sending chunk: {content}")
                                yield f"data: {content}\n\n"

                        # Send completion signal
                        yield "data: [DONE]\n\n"
                except Exception as e:
                    logger.error(f"Error in generate(): {str(e)}")
                    yield "data: [ERROR] An error occurred while streaming the response.\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # For nginx
                },
            )

        # Get the response message from message service
        response_messages = await get_chat_response_async(
            session=session,
            message=request.message,
        )

        legacy_support_message = Message(
            author_type=response_messages[0].author_type,
            sender_identifier=response_messages[0].sender_identifier,
            recipient_identifier=response_messages[0].recipient_identifier,
            channel=response_messages[0].channel,
            broker=response_messages[0].broker,
            metadata=response_messages[0].metadata,
            extras=response_messages[0].extras,
            text=TextObject(
                body="[WARNING] `message` field is deprecated. Please use `messages` field instead."
            ),
        )

        if request.async_response:
            # Return a successful response immediately
            logger.info(f"Schedule to send messages: {response_messages}")
            send_messages(response_messages)
            return ChatResponse(status="success")
        else:
            # Create and return the ChatResponse with the messages
            return ChatResponse(
                message=legacy_support_message,
                messages=response_messages,
                status="success",
            )
    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating message: {ve}")
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).dict(),
        )
    except Exception as e:
        # Log the error
        print(f"Error processing message: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the message",
            ).dict(),
        )
