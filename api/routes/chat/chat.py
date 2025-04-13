import asyncio
from typing import AsyncIterator

from agno.run.response import RunResponse
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.routes.chat.completion_util import (
    ChatCompletionStreamer,
    CompletionRequest,
    MemoryCache,
)
from api.routes.endpoints import endpoints
from api.routes.utils import map_uri_to_s3_url
from api.schemas.chat.chat import ChatInfo, ChatRequest, ChatResponse
from api.schemas.chat.message import Channel
from api.schemas.error.error import ErrorResponse
from services import project_service
from services.message_service import (
    get_chat_response_async,
    get_chat_response_stream,
    get_filler_message,
)
from services.relay_service import send_messages
from utils.log import logger

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])
_cache = MemoryCache()
DEFAULT_ACCOUNT_ICON = "images/accounts/palona_icon.png"
DEFAULT_USER_ICON = "images/agents/default_user_icon.png"


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

        if request.relay_response:

            async def generate_and_send():
                async def send_filler_message():
                    await asyncio.sleep(
                        7.0
                    )  # Send filler message if it takes longer than 2 seconds go get the response
                    filler_message = get_filler_message(request.message)
                    send_messages([filler_message])
                    logger.info(f"Sending filler message: {filler_message}")

                async for new_session in db.get_db_async():
                    # Start the filler message task only if the message channel is VOICE
                    if request.message.channel == Channel.VOICE:
                        filler_message_task = asyncio.create_task(send_filler_message())
                    else:
                        filler_message_task = None
                    # Get the actual response
                    response_messages = await get_chat_response_async(
                        session=new_session, message=request.message
                    )
                    # Cancel the filler message task if it hasn't triggered yet
                    if filler_message_task:
                        filler_message_task.cancel()

                    result = send_messages(response_messages)
                    logger.info(
                        f"Chat API, schedule to send messages: {response_messages}, result: {result}"
                    )

            asyncio.create_task(generate_and_send())

            # Return a successful response immediately
            return ChatResponse(status="success")

        # Get the response message from message service
        response_messages = await get_chat_response_async(
            session=session,
            message=request.message,
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
        logger.error(f"Error processing message: {str(e)}")
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


completion_chat_engine = ChatCompletionStreamer()


@chat_router.post("/completions")
async def chat_completions(
    request: CompletionRequest,
    raw_request: Request,
    session: AsyncSession = Depends(db.get_db_async),
):
    if request.stream:

        body = await raw_request.json()
        try:
            caller_number = body.get("call", {}).get("customer", {}).get("number")
            if caller_number is None or caller_number == "":
                logger.error("Empty caller number")
                caller_number = "empty_number"
        except Exception as e:
            logger.error(f"Error extracting caller number: {e}")
            caller_number = "empty_number"

        # async for new_session in db.get_db_async():
        return StreamingResponse(
            completion_chat_engine.stream_chat(
                request.messages,
                request.model,
                session,
                sender_identifier=caller_number,
                memory_cache=_cache,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # For nginx
            },
        )
    else:
        result = await completion_chat_engine.full_response(
            request.messages, request.model, session
        )
        return JSONResponse(content=result.model_dump())


@chat_router.websocket("/ws/completions")
async def ws_chat_completions(
    websocket: WebSocket, session: AsyncSession = Depends(db.get_db_async)
):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            model = data.get("model", "palona-default")
            messages = data.get("messages", [])
            if not messages:
                continue
            async for chunk_bytes in completion_chat_engine.stream_chat(
                messages, model, session
            ):
                await websocket.send_text(chunk_bytes.decode("utf-8"))

    except WebSocketDisconnect:
        logger.info("WebSocket: Client disconnected")
