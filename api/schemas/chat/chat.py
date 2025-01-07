from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.chat.message import Message


class ChatRequest(BaseModel):
    message: Message
    # TODO async_response field deprecated, use relay_response instead
    async_response: bool = False
    relay_response: bool = False
    stream: bool = False


class ChatResponse(BaseModel):
    messages: Optional[list[Message]] = None
    status: str = Field(default="success")
