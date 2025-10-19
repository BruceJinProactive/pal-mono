import json
import os
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
    Publish a catering event to SQS.

    Args:
        catering_request_id: ID of the catering request
        event_type: Type of event (e.g., 'catering_request_created', 'catering_request_updated')
        idempotency_key: Idempotency key for the catering request
        event_data: Additional event data (optional)

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    queue_url = os.getenv("CATERING_QUEUE_URL")
    if not queue_url:
        logger.warning("CATERING_QUEUE_URL not set, skipping SQS event publishing")
        return False

    try:
        sqs = boto3.client("sqs")

        message_body: Dict[str, Any] = {
            "event_type": event_type,
            "catering_request_id": catering_request_id,
            "idempotency_key": idempotency_key,
        }

        if event_data:
            message_body["event_data"] = event_data

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageAttributes={
                "event_type": {"StringValue": event_type, "DataType": "String"}
            },
        )

        logger.info(
            f"Successfully published catering event {event_type} for request {catering_request_id}, "
            f"message_id: {response['MessageId']}"
        )
        return True

    except ClientError as e:
        logger.error(f"Failed to publish catering event to SQS: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing catering event: {e}")
        return False
