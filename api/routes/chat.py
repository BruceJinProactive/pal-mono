from datetime import datetime
from enum import Enum
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.routes.endpoints import endpoints
from db.session import get_db
from services.chat_service import get_chat_response

chat_router = APIRouter(prefix=endpoints.CHAT, tags=["Chat"])


class MessageChannel(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class MessageRequest(BaseModel):
    channel: MessageChannel
    sender: str
    recipient: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    content: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


@chat_router.post("/", response_model=MessageResponse)
async def chat(message: MessageRequest, db: Session = Depends(get_db)):
    try:
        # Process the message
        print(
            f"Received {message.channel} message from {message.sender} to {message.recipient}: {message.content}"
        )
        print(f"Additional metadata: {message.metadata}")

        # Get the response from the chat service
        response_content = get_chat_response(
            db=db,
            channel=message.channel,
            sender=message.sender,
            recipient=message.recipient,
            content=message.content,
        )
        # Create and return the MessageResponse
        return MessageResponse(content=response_content)

    except Exception as e:
        # Log the error
        print(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing message")
