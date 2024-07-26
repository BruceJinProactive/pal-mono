from datetime import datetime
from enum import Enum
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.routes.endpoints import endpoints

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
async def chat(message: MessageRequest):
    try:
        # Process the message
        # Here you would typically:
        # - Validate the message
        # - Store the message in a database
        # - Trigger any necessary workflows
        # - Forward the message to other systems if needed

        print(
            f"Received {message.channel} message from {message.sender} to {message.recipient}: {message.content}"
        )
        print(f"Additional metadata: {message.metadata}")

        # TODO: Create and return the response

        response = MessageResponse()
        return response

    except Exception as e:
        # Log the error
        print(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing message")
