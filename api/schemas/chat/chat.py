from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.chat.message import Message


class ChatRequest(BaseModel):
    message: Message
    async_response: bool = False


class ChatResponse(BaseModel):
    # TODO message field deprecated - remove after multi-message support added
    message: Optional[Message] = None

    messages: Optional[list[Message]] = None
    status: str = Field(default="success")


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    error_code: str
    error_message: str
    details: Optional[dict] = None
