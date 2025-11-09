import json
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils.log import logger

# Default EventBridge bus name from environment variable
DEFAULT_EVENT_BUS_NAME = os.getenv("MAIN_EVENT_BUS_NAME", "pal-main-event-bus")

# Reusable EventBridge client (boto3 clients are thread-safe)
# Initialized lazily to avoid breaking tests and non-production environments
_eventbridge_client = None


def _get_eventbridge_client():
    """Get or create the EventBridge client (lazy initialization)."""
    global _eventbridge_client
    if _eventbridge_client is None:
        _eventbridge_client = boto3.client("events")
    return _eventbridge_client


def publish_event(
    source: str,
    detail_type: str,
    detail: Dict[str, Any],
) -> bool:
    """
    Publish a single event to AWS EventBridge.

    Args:
        source: The source of the event (e.g., 'pal-mono')
        detail_type: The type of event (e.g., 'catering.RequestCreated')
        detail: The event payload containing all event data

    Returns:
        bool: True if event was published successfully, False otherwise
    """
    try:
        bus_name = DEFAULT_EVENT_BUS_NAME

        # Build the event entry
        entry: Dict[str, Any] = {
            "Source": source,
            "DetailType": detail_type,
            "Detail": json.dumps(
                detail, default=str
            ),  # default=str handles UUID, datetime
            "EventBusName": bus_name,
        }

        response = _get_eventbridge_client().put_events(Entries=[entry])

        # Check if the event was successfully published
        if response["FailedEntryCount"] == 0:
            entries = response.get("Entries", [])
            event_id = entries[0].get("EventId") if entries else "unknown"
            logger.info(
                "Successfully published event to EventBridge",
                extra={
                    "source": source,
                    "detail_type": detail_type,
                    "event_bus": bus_name,
                    "event_id": event_id,
                },
            )
            return True
        else:
            # Handle failures
            entries = response.get("Entries", [])
            for i, entry in enumerate(entries):
                if "ErrorCode" in entry:
                    logger.error(
                        "Failed to publish event to EventBridge",
                        extra={
                            "source": source,
                            "detail_type": detail_type,
                            "event_bus": bus_name,
                            "entry_index": i,
                            "error_code": entry.get("ErrorCode"),
                            "error_message": entry.get("ErrorMessage"),
                        },
                    )
            return False

    except ClientError as e:
        logger.error(
            "AWS ClientError publishing event to EventBridge",
            extra={
                "source": source,
                "detail_type": detail_type,
                "error": str(e),
                "error_code": e.response.get("Error", {}).get("Code"),
            },
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error publishing event to EventBridge",
            extra={
                "source": source,
                "detail_type": detail_type,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return False
