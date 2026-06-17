from decimal import Decimal
from enum import Enum
from typing import Union

from pydantic import BaseModel

from db.tables.types import CallLanguage, CallPurpose

# Valid channel names used across the analytics system
VALID_CHANNELS = [
    "api",
    "email",
    "instagram",
    "internal_app",
    "sms",
    "voice",
    "whatsapp",
]


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


class ReportConfig(BaseModel):
    """Report configuration with name and metrics config"""

    name: str
    metrics_config: dict


class AnalyticsReportType:
    """Analytics Report Types with configurations"""

    ACTIVE_USERS = ReportConfig(
        name="Active Users",
        metrics_config={
            "active_users": {"source": "row_index", "index": -2},
        },
    )

    MESSAGE_TURNS = ReportConfig(
        name="Message Turn Distribution",
        metrics_config={
            "low_turns": {"source": "row_index", "index": -4},
            "high_turns": {"source": "row_index", "index": -3},
            "total_conversations": {"source": "row_index", "index": -2},
            "total_turns": {"source": "row_index", "index": -1},
            "avg_turns": {
                "source": "calculated",
                "formula": lambda row: (
                    round(row[-1] / row[-2], 2) if row[-2] > 0 else 0.0
                ),
            },
        },
    )

    CALL_METRICS = ReportConfig(
        name="Call Time Metrics",
        metrics_config={
            "total_calls": {"source": "row_index", "index": -10},
            "avg_duration": {
                "source": "calculated",
                "formula": lambda row: (
                    round(float(row[-9]), 2) if row[-9] is not None else 0.0
                ),
            },
            "avg_turn_latency": {
                "source": "calculated",
                "formula": lambda row: (
                    round(float(row[-8]), 2) if row[-8] is not None else 0.0
                ),
            },
            "short_calls": {"source": "row_index", "index": -7},
            "long_calls": {"source": "row_index", "index": -6},
            "transfer_calls": {"source": "row_index", "index": -5},
            "transfer_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    round(float(row[-4]), 2) if row[-4] is not None else 0.0
                ),
            },
            "positive_calls": {"source": "row_index", "index": -3},
            "neutral_calls": {"source": "row_index", "index": -2},
            "negative_calls": {"source": "row_index", "index": -1},
        },
    )

    # Build separate call purpose and language metrics configs
    _call_purpose_metrics = {}
    _call_language_metrics = {}

    # Add all purpose metrics (14 purposes: indices -18 to -5)
    for i, purpose in enumerate(CallPurpose):
        _call_purpose_metrics[purpose.value] = {
            "source": "row_index",
            "index": -(len(CallPurpose) + len(CallLanguage) - i),
        }

    # Add all language metrics (4 languages: indices -4 to -1)
    for i, language in enumerate(CallLanguage):
        _call_language_metrics[language.value] = {
            "source": "row_index",
            "index": -(len(CallLanguage) - i),
        }

    # Create separate report configs
    CALL_PURPOSE_DISTRIBUTION = ReportConfig(
        name="Call Purpose Distribution",
        metrics_config=_call_purpose_metrics,
    )

    CALL_LANGUAGE_DISTRIBUTION = ReportConfig(
        name="Call Language Distribution",
        metrics_config=_call_language_metrics,
    )

    # Keep combined config for backward compatibility
    CALL_INFO_DISTRIBUTION = ReportConfig(
        name="Call Info Distribution",
        metrics_config={**_call_purpose_metrics, **_call_language_metrics},
    )

    CONVERSION_METRICS = ReportConfig(
        name="Conversion Metrics",
        metrics_config={
            # Order metrics (indices -7 to -3)
            "total_conversations": {"source": "row_index", "index": -7},
            "conversations_with_orders": {"source": "row_index", "index": -6},
            "paid_orders": {"source": "row_index", "index": -5},
            "total_subtotal": {
                "source": "calculated",
                "formula": lambda row: float(row[-4]) if row[-4] is not None else 0.0,
            },
            "paid_total": {
                "source": "calculated",
                "formula": lambda row: float(row[-3]) if row[-3] is not None else 0.0,
            },
            "conversion_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # conversion_rate = conversations_with_orders / total_conversations * 100
                    round(float(row[-6]) / float(row[-7]) * 100, 2)
                    if len(row) >= 7
                    and isinstance(row[-7], (int, float))
                    and row[-7] > 0
                    else 0.0
                ),
            },
            "paid_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # paid_rate = paid_orders / total_conversations * 100
                    round(float(row[-5]) / float(row[-7]) * 100, 2)
                    if len(row) >= 7
                    and isinstance(row[-7], (int, float))
                    and row[-7] > 0
                    else 0.0
                ),
            },
            # Reservation metrics (indices -2 to -1)
            "total_reservations": {"source": "row_index", "index": -2},
            "total_waitlists": {"source": "row_index", "index": -1},
            "reservation_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # reservation_rate = total_reservations / total_conversations * 100
                    round(float(row[-2]) / float(row[-7]) * 100, 2)
                    if len(row) >= 7
                    and isinstance(row[-7], (int, float))
                    and row[-7] > 0
                    else 0.0
                ),
            },
            "waitlist_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # waitlist_rate = total_waitlists / total_conversations * 100
                    round(float(row[-1]) / float(row[-7]) * 100, 2)
                    if len(row) >= 7
                    and isinstance(row[-7], (int, float))
                    and row[-7] > 0
                    else 0.0
                ),
            },
        },
    )

    TRANSFER_REASON_DISTRIBUTION = ReportConfig(
        name="Transfer Reason Distribution",
        metrics_config={},
    )


class PerformanceReport(BaseModel):
    name: str
    data: dict


class GetAllReportsResponse(BaseModel):
    """Get All Reports Response"""

    reports: list[PerformanceReport]


class ChannelData(BaseModel):
    """Active Users data for a specific channel"""

    api: int
    email: int
    instagram: int
    internal_app: int
    sms: int
    voice: int
    whatsapp: int
    total: int
