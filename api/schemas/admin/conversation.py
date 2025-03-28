import datetime
import uuid

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Message Model"""

    id: uuid.UUID
    body: dict
    conversation_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime | None


class ConversationPreview(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    last_message_text: str
    num_messages: int
    channel: str
    sender_identifier: str
    recipient_identifier: str
    broker: str | None
    created_at: datetime.datetime
    is_escalated: bool


class InboxResponse(BaseModel):
    total_pages: int
    total_conversations: int
    inbox: list[ConversationPreview]


class ListConversationsResponse(BaseModel):
    conversations: list[ConversationPreview]
    total_pages: int
    total_conversations: int


class ListConversationMessagesResponse(BaseModel):
    messages: list[Message]
    total_pages: int
    total_messages: int
