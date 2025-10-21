import json
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from utils.log import logger


def publish_catering_event(
    catering_request_id: str,
    event_type: str,
    idempotency_key: str,
    event_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Publish a catering event to AWS EventBridge.

    Args:
        catering_request_id: ID of the catering request
        event_type: Type of event (e.g., 'catering_request_created')
        idempotency_key: Idempotency key for the catering request
        event_data: Additional event data (optional)

    Returns:
        bool: True if event was published successfully, False otherwise
    """
    try:
        eventbridge = boto3.client("events")

        detail: Dict[str, Any] = {
            "catering_request_id": catering_request_id,
            "idempotency_key": idempotency_key,
        }

        if event_data:
            detail["event_data"] = event_data

        # Map event_type to DetailType for EventBridge
        detail_type_mapping = {
            "catering_request_created": "CateringRequestCreated",
        }

        detail_type = detail_type_mapping.get(event_type, event_type)

        response = eventbridge.put_events(
            Entries=[
                {
                    "Source": "pal.catering",
                    "DetailType": detail_type,
                    "Detail": json.dumps(detail),
                    "EventBusName": "default",
                }
            ]
        )

        # Check if the event was successfully published
        if response["FailedEntryCount"] == 0:
            # Successfully published - get event ID from first (and only) entry
            entries = response.get("Entries", [])
            if entries and "EventId" in entries[0]:
                event_id = entries[0]["EventId"]
                logger.info(
                    f"Successfully published catering event {detail_type} for request {catering_request_id}, "
                    f"event_id: {event_id}"
                )
            else:
                logger.info(
                    f"Successfully published catering event {detail_type} for request {catering_request_id}"
                )
            return True
        else:
            # Handle failures - iterate through entries to find failed ones
            entries = response.get("Entries", [])
            for i, entry in enumerate(entries):
                if "ErrorCode" in entry:
                    logger.error(
                        f"Failed to publish catering event {detail_type} (entry {i}): "
                        f"{entry.get('ErrorCode')} - {entry.get('ErrorMessage')}"
                    )

            # If no specific error found, log general failure
            if not any("ErrorCode" in entry for entry in entries):
                logger.error(
                    f"Failed to publish catering event {detail_type}: Unknown error"
                )

            return False

    except ClientError as e:
        logger.error(f"Failed to publish catering event to EventBridge: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing catering event: {e}")
        return False
