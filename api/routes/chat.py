from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.models.message import Message
from api.routes.endpoints import endpoints
from db.session import get_db
from services.message_service import get_chat_response

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])


class ChatRequest(BaseModel):
    message: Message


class ChatResponse(BaseModel):
    message: Message
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

        # Get the response message from message service
        response_message = get_chat_response(
            db=db,
            message=request.message,
        )

        # Create and return the ChatResponse
        return ChatResponse(message=response_message)
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
