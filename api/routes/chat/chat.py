from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.routes.endpoints import endpoints
from api.schemas.chat.chat import ChatRequest, ChatResponse, ErrorResponse
from db.session import get_db
from services.message_service import get_chat_response
from services.relay_service import send_message
from utils.log import logger

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])


@chat_router.post(
    "/",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        # Process the message
        logger.info(f"Received message: {request.message}")

        # Get the response message from message service
        response_message = await get_chat_response(
            db=db,
            message=request.message,
        )

        if request.async_response:
            # Return a successful response immediately
            logger.info(f"Schedule to send message: {response_message}")
            send_message(response_message)
            return ChatResponse(status="success")
        else:
            # Create and return the ChatResponse with the message
            return ChatResponse(message=response_message, status="success")
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
