import datetime
import uuid

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Message Model"""

    id: uuid.UUID
    content: str | None
    type: str | None
    channel: str | None
    author_type: str | None
    metadata: dict | None
    channel_info: dict | None
    sender_identifier: str | None
    recipient_identifier: str | None
    escalated: bool
    sent_at: str | None
    created_at: datetime.datetime
    conversation_id: uuid.UUID
    media: dict | None = None


class UserSession(BaseModel):
    id: uuid.UUID
    status: str
    last_message: Message | None
    total_messages: int
    created_at: datetime.datetime


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


class UserSessionSearchFilters(BaseModel):
    channels: list[str]


class ListUserSessionsResponse(BaseModel):
    sessions: list[UserSession]
    filters: UserSessionSearchFilters
    total_sessions: int
    total_pages: int


class ListConversationMessagesResponse(BaseModel):
    messages: list[Message]
    total_pages: int
    total_messages: int
