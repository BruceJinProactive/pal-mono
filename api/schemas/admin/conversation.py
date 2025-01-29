import uuid

from pydantic import BaseModel, Field


class ConversationPreview(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    last_message_text: str
    num_messages: int
    channel: str
    sender_identifier: str
    recipient_identifier: str
    broker: str | None
