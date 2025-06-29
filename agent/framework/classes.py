from typing import List, Literal, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single chat message."""

    role: Literal["system", "user", "assistant", "function", "tool"]
    content: str
    name: Optional[str] = None


class ChatRequest(BaseModel):
    """Input model for chat requests."""

    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    """Output model for chat responses."""

    id: str
    message: str = "chat.completion"
