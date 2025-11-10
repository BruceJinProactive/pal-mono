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
            "total_conversations": {"source": "row_index", "index": -5},
            "conversations_with_orders": {"source": "row_index", "index": -4},
            "paid_orders": {"source": "row_index", "index": -3},
            "total_subtotal": {
                "source": "calculated",
                "formula": lambda row: float(row[-2]) if row[-2] is not None else 0.0,
            },
            "paid_total": {
                "source": "calculated",
                "formula": lambda row: float(row[-1]) if row[-1] is not None else 0.0,
            },
            "conversion_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # Handle dynamic row structure: last 5 fields are always the metrics
                    # conversion_rate = conversations_with_orders / total_conversations * 100
                    round(float(row[-4]) / float(row[-5]) * 100, 2)
                    if len(row) >= 5
                    and isinstance(row[-5], (int, float))
                    and row[-5] > 0
                    else 0.0
                ),
            },
            "paid_rate": {
                "source": "calculated",
                "formula": lambda row: (
                    # Handle dynamic row structure: last 5 fields are always the metrics
                    # paid_rate = paid_orders / total_conversations * 100
                    round(float(row[-3]) / float(row[-5]) * 100, 2)
                    if len(row) >= 5
                    and isinstance(row[-5], (int, float))
                    and row[-5] > 0
                    else 0.0
                ),
            },
        },
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
