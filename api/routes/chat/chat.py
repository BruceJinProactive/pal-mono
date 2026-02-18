import asyncio
from typing import AsyncIterator

from agno.run.response import RunResponse
from ddtrace.trace import tracer
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.endpoints import endpoints
from api.schemas.chat.chat import ChatInfo, ChatRequest, ChatResponse
from api.schemas.error.error import ErrorResponse
from db.session import AsyncSessionLocal
from db.tables.types import Channel
from services import project_service
from services.asset_service import map_uri_to_s3_url
from services.message_service import (
    get_chat_response_async,
    get_chat_response_stream,
    get_filler_message,
)
from services.relay_service import send_messages
from utils.dd import set_testing_mode
from utils.log import logger
from utils.request_context import RequestContext

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])
DEFAULT_ACCOUNT_ICON = "images/accounts/palona_icon.png"
DEFAULT_USER_ICON = "images/agents/default_user_icon.png"


def categorize_chat_request(request: ChatRequest) -> str:
    """
    Check the type of chat request based on the Request object
    """
    if request.stream:
        return "STREAM"
    if request.relay_response:
        return "RELAY"
    return "REGULAR"


@chat_router.post(
    "/",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest, session: AsyncSession = Depends(db.get_db_async)):
    try:

        request_context = RequestContext()

        # Extract testing flag from message metadata and set context
        testing = (
            getattr(request.message.metadata, "testing", False)
            if request.message.metadata
            else False
        )
        set_testing_mode(testing)

        # If testing, drop the APM trace to prevent DD logging
        current_span = tracer.current_span()
        if testing and current_span:
            current_span.context.sampling_priority = -1  # USER_REJECT

        # Process the message
        logger.info(
            f"Received message: {request.message}",
            extra={
                "relay_response": request.relay_response,
                "stream": request.stream,
            },
        )

        # Override the DD Trace to add request type facet (only for non-testing requests)
        if not testing and current_span:
            current_span.set_tag(
                "http.params.chat_type", categorize_chat_request(request)
            )

        if request.stream:

            async def generate() -> AsyncIterator[str]:
                try:
                    response_stream = await get_chat_response_stream(
                        session=session,
                        message=request.message,
                        request_context=request_context,
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
                except asyncio.CancelledError:
                    logger.debug("[Chat] Stream cancelled (client disconnect)")
                    raise
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

        if request.relay_response:

            async def generate_and_send():
                async def send_filler_message():
                    await asyncio.sleep(
                        7.0
                    )  # Send filler message if it takes longer than 2 seconds go get the response
                    filler_message = get_filler_message(request.message)
                    send_messages([filler_message])
                    logger.info(f"Sending filler message: {filler_message}")

                async with AsyncSessionLocal() as new_session:
                    # Start the filler message task only if the message channel is VOICE
                    if request.message.channel == Channel.VOICE:
                        filler_message_task = asyncio.create_task(send_filler_message())
                    else:
                        filler_message_task = None

                    try:
                        # Get the actual response
                        response_messages = await get_chat_response_async(
                            session=new_session,
                            message=request.message,
                            request_context=request_context,
                        )

                        result = send_messages(response_messages)
                        logger.info(
                            f"Chat API, schedule to send messages: {response_messages}, result: {result}"
                        )
                        await new_session.commit()
                    except asyncio.CancelledError:
                        logger.debug(
                            "[Chat] generate_and_send cancelled (client disconnect)"
                        )
                        raise
                    except Exception as e:
                        await new_session.rollback()
                        logger.error(f"Database error in generate_and_send: {str(e)}")
                        raise
                    finally:
                        # Cancel filler message task on all exit paths
                        if filler_message_task and not filler_message_task.done():
                            filler_message_task.cancel()
                            try:
                                await filler_message_task
                            except asyncio.CancelledError:
                                pass

            asyncio.create_task(generate_and_send())

            # Return a successful response immediately
            return ChatResponse(status="success")

        # Get the response message from message service
        response_messages = await get_chat_response_async(
            session=session,
            message=request.message,
            request_context=request_context,
        )

        # Create and return the ChatResponse with the messages
        return ChatResponse(
            messages=response_messages,
            status="success",
        )
    except ValueError as ve:
        # Log and handle validation errors
        logger.error(f"Error validating message: {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error_code="VALIDATION_ERROR", error_message=str(ve)
            ).dict(),
        )
    except Exception as e:
        # Log the error
        logger.error(
            f"Error processing message: {str(e)}",
            extra={
                "relay_response": request.relay_response,
                "stream": request.stream,
                "sender_identifier": request.message.sender_identifier,
                "recipient_identifier": request.message.recipient_identifier,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred while processing the message",
            ).dict(),
        )


@chat_router.get("/info/{project_name}")
def get_project_info(
    request: Request,
    project_name: str,
    session: Session = Depends(db.get_db),
) -> ChatInfo:
    """
    Returns public info for a specific project.
    """
    project = project_service.get_project_by_name(session, project_name)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project name does not exist",
            headers={"Content-Type": "application/json"},
        )
    account_icon = project.account.icon_uri
    user_icon = project.agent.raw_config.get("default_user_icon_uri")
    return ChatInfo(
        project_name=project.name,
        project_display_name=project.display_name,
        account_display_name=project.account.display_name,
        account_icon_url=map_uri_to_s3_url(account_icon)
        or map_uri_to_s3_url(DEFAULT_ACCOUNT_ICON),
        default_user_icon_url=map_uri_to_s3_url(user_icon)
        or map_uri_to_s3_url(DEFAULT_USER_ICON),
    )
