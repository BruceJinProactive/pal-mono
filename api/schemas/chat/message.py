import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from db.tables.types import Channel


class TextObject(BaseModel):
    body: str = Field(..., max_length=4096)


class MediaObject(BaseModel):
    url: str = Field(...)
    media_type: str = Field(...)
    caption: str = Field(default="", max_length=1024)


class AuthorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Broker(str, Enum):
    META = "meta"
    SENDBLUE = "sendblue"
    TWILIO = "twilio"


class Type(str, Enum):
    TEXT = "text"
    MEDIA = "media"


class Extras(BaseModel):
    escalated: bool = Field(default=False)
    closing_conversation: bool = Field(default=False)


class Metadata(BaseModel):
    account_name: str = Field(default="")
    project_name: str = Field(default="")
    agent_id: str = Field(default="")
    user_id: str = Field(default="")
    session_id: str = Field(default="")
    parent_message_id: str = Field(default="")
    testing: bool = Field(default=False)


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_type: AuthorType
    # Channel
    sender_identifier: str
    recipient_identifier: str
    channel: Channel = Channel.API
    broker: Optional[Broker] = None
    channel_info: Dict[str, Any] = Field(default_factory=dict)
    # Content
    type: Type = Type.TEXT
    text: Optional[TextObject] = None
    media: Optional[MediaObject] = None
    context: str = Field(default="", max_length=4096)
    # Extras
    extras: Optional[Extras] = None
    # Metadata
    metadata: Optional[Metadata] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_model(self):
        if self.type not in ("text", "media"):
            raise ValueError("Currently, only 'text', 'media' types are supported")
        if self.type == "text" and self.text is None:
            raise ValueError("TextObject is required for 'text' type")
        elif self.type == "media" and self.media is None:
            raise ValueError("MediaObject is required for 'media' type")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "author_type": self.author_type.value,
            "sender_identifier": self.sender_identifier,
            "recipient_identifier": self.recipient_identifier,
            "channel": self.channel.value,
            "broker": self.broker.value if self.broker is not None else None,
            "channel_info": self.channel_info,
            "type": self.type.value,
            "text": self.text.dict() if self.text is not None else None,
            "media": self.media.dict() if self.media is not None else None,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata.dict() if self.metadata is not None else None,
            "extras": self.extras.dict() if self.extras is not None else None,
        }

    def get_content(self) -> str:
        if self.channel in [Channel.SMS, Channel.VOICE]:
            phone_number = f"My phone number is: {self.sender_identifier}"
            self.context = (
                f"{self.context}|{phone_number}" if self.context else phone_number
            )

        if self.text:
            content = (
                f"<message_channel>{self.channel.value}</message_channel>\n\n"
                + f"<user_context>{self.context}</user_context>\n\n"
                + f"<user_message>{self.text.body}</user_message>"
            )
        elif self.media:
            content = (
                f"<message_channel>{self.channel.value}</message_channel>\n\n"
                + f"<user_context>{self.context}</user_context>\n\n"
                + f"<media_url>{self.media.url}</media_url>\n\n"
                + f"<media_caption>{self.media.caption}</media_caption>\n\n"
                + f"<media_type>{self.media.media_type}</media_type>"
            )
        else:
            raise ValueError("Message object not set")

        return content

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        # Convert string to datetime
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        # Convert text dict to TextObject
        if isinstance(data.get("text"), dict):
            data["text"] = TextObject(**data["text"])

        # Convert media dict to MediaObject
        if isinstance(data.get("media"), dict):
            data["media"] = MediaObject(**data["media"])

        # Convert extras dict to Extras
        if isinstance(data.get("extras"), dict):
            data["extras"] = Extras(**data["extras"])

        # Convert metadata dict to Metadata
        if isinstance(data.get("metadata"), dict):
            data["metadata"] = Metadata(**data["metadata"])

        return cls(**data)
