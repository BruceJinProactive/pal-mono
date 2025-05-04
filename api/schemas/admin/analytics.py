from enum import Enum

from pydantic import BaseModel


class Event(str, Enum):
    """Analytics Event"""

    AGENT_MESSAGE = "Agent Message"
    USER_MESSAGE = "User Message"
    CRITICAL_ACTION = "Critical Action"


class GetReportResponse(BaseModel):
    """Get Report Response"""

    report_data: dict


class PerformanceReport(BaseModel):
    name: str
    data: dict


class GetAllReportsResponse(BaseModel):
    """Get All Reports Response"""

    reports: list[PerformanceReport]
