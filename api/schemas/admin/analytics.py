from decimal import Decimal
from enum import Enum
from typing import Union

from pydantic import BaseModel

# Valid channel names used across the analytics system
VALID_CHANNELS = ["api", "instagram", "internal_app", "sms", "voice", "whatsapp"]


class AnalyticsResponse(BaseModel):
    """Analytics Response with project breakdowns"""

    analytics_data: dict[
        str, dict[str, dict[str, Union[Decimal, int]]]
    ]  # {date: {project: {channel: value}}}


class Event(str, Enum):
    """Analytics Event"""

    AGENT_MESSAGE = "Agent Message"
    USER_MESSAGE = "User Message"
    CRITICAL_ACTION = "Critical Action"


class AnalyticsReportType(str, Enum):
    """Analytics Report Types"""

    DAU = "DAU"
    MESSAGE_TURNS = "Message Turns"
    ORDER_TOTAL = "Order Total"
    ORDER_COUNT = "Order Count"


class PerformanceReport(BaseModel):
    name: str
    data: AnalyticsResponse


class GetAllReportsResponse(BaseModel):
    """Get All Reports Response"""

    reports: list[PerformanceReport]


class ChannelData(BaseModel):
    """Daily Active Users data for a specific channel"""

    api: int
    instagram: int
    internal_app: int
    sms: int
    voice: int
    whatsapp: int
    total: int
