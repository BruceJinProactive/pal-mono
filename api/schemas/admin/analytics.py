from enum import Enum

from pydantic import BaseModel


class Event(str, Enum):
    """Anslytics Event"""

    AGENT_MESSAGE = "Agent Message"
    USER_MESSAGE = "User Message"
    CRITICAL_ACTION = "Critical Action"


class GetReportRequest(BaseModel):
    """Get Report Request"""

    report_name: str


class GetReportResponse(BaseModel):
    """Get Report Response"""

    report_data: dict
