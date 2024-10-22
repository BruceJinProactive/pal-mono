import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class TextObject(BaseModel):
    body: str = Field(..., max_length=4096)


class AuthorType(str, Enum):
    USER = "user"
    AGENT = "agent"


class Channel(str, Enum):
    API = "api"
    INSTAGRAM = "instagram"
    INTERNAL_APP = "internal_app"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class Broker(str, Enum):
    META = "meta"
    SENDBLUE = "sendblue"
    TWILIO = "twilio"


class Type(str, Enum):
    TEXT = "text"


class Extras(BaseModel):
    escalated: bool = Field(default=False)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_type: AuthorType
    # Channel
    sender_identifier: str
    recipient_identifier: str
    channel: Channel = Channel.API
    broker: Optional[Broker] = None
    # Content
    type: Type = Type.TEXT
    text: TextObject
    # Extra information
    extras: Optional[Extras] = None
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("type")
    def validate_type(cls, v):
        if v != "text":
            raise ValueError("Currently, only 'text' type is supported")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "author_type": self.author_type.value,
            "sender_identifier": self.sender_identifier,
            "recipient_identifier": self.recipient_identifier,
            "channel": self.channel.value,
            "broker": self.broker.value if self.broker is not None else None,
            "type": self.type.value,
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
