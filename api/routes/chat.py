from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.models.message import Message
from api.routes.endpoints import endpoints
from db.session import get_db
from services.message_service.message_service import get_chat_response
from services.relay_service.relay_service import send_message
from utils.log import logger

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])


class ChatRequest(BaseModel):
    message: Message
    async_response: bool = False


class ChatResponse(BaseModel):
    message: Optional[Message] = None
    status: str = Field(default="success")


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    error_code: str
    error_message: str
    details: Optional[dict] = None


@chat_router.post(
    "/",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        # Process the message
        print(f"Received message: {request.message}")

        if request.async_response:
            # Return a successful response immediately
            # TODO: make get_chat_response async
            response_message = get_chat_response(
                db=db,
                message=request.message,
            )
            logger.info(f"Schedule to send message: {response_message}")
            result = send_message(response_message)
            logger.info(f"Message scheduled for delivery result: {result}")
            return ChatResponse(status="success")
        else:
            # Get the response message from message service
            response_message = get_chat_response(
                db=db,
                message=request.message,
            )
            # Create and return the ChatResponse with the message
            return ChatResponse(message=response_message, status="success")
    except ValueError as ve:
        # Handle validation errors
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
