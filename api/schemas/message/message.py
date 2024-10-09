import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class TextObject(BaseModel):
    body: str = Field(..., max_length=4096)


class AuthorType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChannelPlatform(str, Enum):
    ADMIN_CONSOLE = "admin_console"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    WEBSITE = "website"
    INSTAGRAM = "instagram"


class MessagingBroker(str, Enum):
    SENDBLUE = "sendblue"
    TWILIO = "twilio"
    WEB = "web"


class Extras(BaseModel):
    escalated: bool = Field(default=False)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_type: AuthorType
    sender_channel_identifier: str
    recipient_channel_identifier: str
    channel_platform: ChannelPlatform
    messaging_broker: MessagingBroker
    type: str = Field(default="text")
    text: TextObject
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    extras: Optional[Extras] = None

    @field_validator("type")
    def validate_type(cls, v):
        if v != "text":
            raise ValueError("Currently, only 'text' type is supported")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "author_type": self.author_type.value,
            "sender_channel_identifier": self.sender_channel_identifier,
            "recipient_channel_identifier": self.recipient_channel_identifier,
            "channel_platform": self.channel_platform.value,
            "messaging_broker": self.messaging_broker.value,
            "type": self.type,
            "text": self.text.dict(),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "extras": self.extras.dict() if self.extras is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        # Convert string to datetime
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        # Convert text dict to TextObject
        if isinstance(data.get("text"), dict):
            data["text"] = TextObject(**data["text"])

        # Convert extras dict to Extras
        if isinstance(data.get("extras"), dict):
            data["extras"] = Extras(**data["extras"])

        return cls(**data)
