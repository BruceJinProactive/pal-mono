import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class TextObject:
    def __init__(self, body: str):
        if len(body) > 4096:
            raise ValueError("Text body cannot exceed 4096 characters")
        self.body: str = body

    def to_dict(self) -> Dict[str, Any]:
        return {"body": self.body}


class MessagingProduct(Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"


class MessagingBroker(Enum):
    TWILIO = "twilio"
    SENDBLUE = "sendblue"


class Message:
    def __init__(
        self,
        sender: str,
        recipient: str,
        text: TextObject,
        messaging_product: MessagingProduct,  # Updated to use enum
        messaging_broker: MessagingBroker,  # Updated to use enum
        type: str = "text",
    ):
        self.id: str = str(uuid.uuid4())
        self.sender: str = sender
        self.recipient: str = recipient
        self.messaging_product: MessagingProduct = messaging_product
        self.messaging_broker: MessagingBroker = messaging_broker
        self.type: str = type
        self.text: TextObject = text
        self.timestamp: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "messaging_product": self.messaging_product.value,  # Convert enum to value
            "messaging_broker": self.messaging_broker.value,  # Convert enum to value
            "type": self.type,
            "text": self.text.to_dict(),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        text_obj = TextObject(**data["text"])
        message = cls(
            sender=data["sender"],
            recipient=data["recipient"],
            text=text_obj,
            messaging_product=MessagingProduct(
                data["messaging_product"]
            ),  # Convert value to enum
            messaging_broker=MessagingBroker(
                data["messaging_broker"]
            ),  # Convert value to enum
            type=data.get("type", "text"),
        )
        message.timestamp = datetime.fromisoformat(data["timestamp"])
        return message
