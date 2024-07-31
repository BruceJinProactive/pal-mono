from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from api.routes.endpoints import endpoints
from db.session import get_db
from services.chat_service import get_chat_response
from api.models.message import Message, TextObject

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

        # Get the response from the chat service
        response_content = get_chat_response(
            db=db,
            channel=request.message.messaging_product,
            sender=request.message.sender,
            recipient=request.message.recipient,
            content=request.message.text.body,
        )

        # Create response message
        response_message = Message(
            sender=request.message.recipient,  # swap sender and recipient
            recipient=request.message.sender,
            text=TextObject(body=response_content),
            messaging_product=request.message.messaging_product,
            messaging_broker=request.message.messaging_broker,
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
