from typing import Optional

from pydantic import BaseModel, Field

from api.schemas.chat.message import Message


class ChatRequest(BaseModel):
    message: Message
    relay_response: bool = False
    stream: bool = False


class ChatResponse(BaseModel):
    messages: Optional[list[Message]] = None
    status: str = Field(default="success")


class ChatInfo(BaseModel):
    project_name: str
    project_display_name: str | None = None
    account_display_name: str | None = None
    account_icon_url: str | None = None
    default_user_icon_url: str | None = None
