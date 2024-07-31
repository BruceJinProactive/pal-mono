import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field, validator


class TextObject(BaseModel):
    body: str = Field(..., max_length=4096)


class MessagingProduct(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"


class MessagingBroker(str, Enum):
    TWILIO = "twilio"
    SENDBLUE = "sendblue"


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    recipient: str
    messaging_product: MessagingProduct
    messaging_broker: MessagingBroker
    type: str = Field(default="text")
    text: TextObject
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("type")
    def validate_type(cls, v):
        if v != "text":
            raise ValueError("Currently, only 'text' type is supported")
        return v

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "messaging_product": self.messaging_product.value,
            "messaging_broker": self.messaging_broker.value,
            "type": self.type,
            "text": self.text.dict(),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        # Convert string to datetime
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        # Convert text dict to TextObject
        if isinstance(data.get("text"), dict):
            data["text"] = TextObject(**data["text"])

        return cls(**data)
