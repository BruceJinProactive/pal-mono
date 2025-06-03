from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    ORDER_SUMMARY = "order_summary"
    CONVERSATION_SUMMARY = "conversation_summary"


class Message(BaseModel):
    """
    Represents a message to be sent via SMS.
    """

    type: MessageType = Field(description="Type of message to be sent")
    content: str = Field(description="Content of the message")
    phone_number: str = Field(description="Recipient's phone number")
    metadata: Optional[dict] = Field(
        default=None, description="Additional metadata for the message"
    )


class ConversationSummary(BaseModel):
    """
    Represents a summary of a conversation.
    """

    summary: str = Field(description="Summary of the conversation")
    key_points: List[str] = Field(description="Key points from the conversation")
    action_items: List[str] = Field(description="Action items or decisions made")


class OrderSummary(BaseModel):
    """
    Represents a summary of an order.
    """

    order_id: str = Field(description="Unique identifier for the order")
    items: List[str] = Field(description="List of ordered items")
    total_amount: float = Field(description="Total amount of the order")
    delivery_address: Optional[str] = Field(
        default=None, description="Delivery address if applicable"
    )
    special_instructions: Optional[str] = Field(
        default=None, description="Special instructions for the order"
    )
