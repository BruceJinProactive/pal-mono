import json
from datetime import datetime, timedelta, timezone

import boto3
from utils.dttm import current_utc
from botocore.exceptions import ClientError
from services.messages import Message, TextObject, MessagingProduct, MessagingBroker

# Initialize AWS client
stepfunctions = boto3.client("stepfunctions")

# Constants
STATE_MACHINE_ARN = (
    "arn:aws:states:us-west-1:767398151610:stateMachine:pal-mono-send-message-sm"
)


def send_message(message: Message, delivery_time: datetime = current_utc()):
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

        # Start the Step Functions execution
        response = stepfunctions.start_execution(
            stateMachineArn=STATE_MACHINE_ARN, input=json.dumps(input_data)
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
