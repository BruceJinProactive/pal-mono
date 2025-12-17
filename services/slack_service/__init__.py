"""
Slack Service

Generic Slack integration service that provides bot management, event handling,
and message routing capabilities. This service is designed to be reusable across
different domain-specific integrations (analytics, notifications, alerts, etc.).
"""

from ._implementation import get_channel_info, handle_slack_events, send_message
from .handlers.analytics import send_report_to_slack as send_analytics_report

__all__ = [
    "handle_slack_events",
    "send_message",
    "get_channel_info",
    "send_analytics_report",
]
