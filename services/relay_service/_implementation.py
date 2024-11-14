import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from api.schemas.chat.message import Message
from utils.dttm import current_utc
from utils.log import logger

# Initialize AWS client
stepfunctions = boto3.client("stepfunctions")

# Get Step Functions state machine ARN from environment variable
AWS_RELAY_STATE_MACHINE_ARN = os.getenv("AWS_RELAY_STATE_MACHINE_ARN")


def send_message(message: Message, delivery_time: datetime = current_utc()) -> dict:
    logger.info(f"Schedule to send message: {message}")
    try:
        # Ensure delivery_time is a datetime object
        if isinstance(delivery_time, str):
            delivery_time = datetime.fromisoformat(delivery_time)

        # Convert to UTC if it's not already
        delivery_time_utc = delivery_time.astimezone(timezone.utc)

        # Format as ISO-8601 with timezone information
        formatted_time = delivery_time_utc.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )

        # Prepare the input for the Step Functions execution
        input_data = {
            "message": {
                "rawPath": "/send",
                "body": message.to_dict(),
            },
            "delivery_time": formatted_time,
        }

        # Ensure AWS_RELAY_STATE_MACHINE_ARN is not None
        if AWS_RELAY_STATE_MACHINE_ARN is None:
            raise ValueError("STATE_MACHINE_ARN environment variable is not set")

        # Start the Step Functions execution
        response = stepfunctions.start_execution(
            stateMachineArn=AWS_RELAY_STATE_MACHINE_ARN, input=json.dumps(input_data)
        )

        return {
            "status": "scheduled",
            "execution_arn": response["executionArn"],
            "scheduled_time": formatted_time,
        }

    except ClientError as e:
        # Handle AWS-specific errors
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]
        return {
            "status": "error",
            "error_code": error_code,
            "error_message": error_message,
        }

    except Exception as e:
        # Handle any other unexpected errors
        return {"status": "error", "error_message": str(e)}


def send_messages(
    messages: list[Message], delivery_time: datetime = current_utc()
) -> list[dict]:
    responses = []

    for message in messages:
        responses.append(send_message(message, delivery_time))

    return responses
