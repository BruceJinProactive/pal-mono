import os

from fastapi import Request

from utils.log import logger

# VAPI Headers for request validation
VAPI_SECRET_HEADER = "X-VAPI-SIGNATURE"
VAPI_TIMESTAMP_HEADER = "X-VAPI-TIMESTAMP"


def validate_vapi_request(request: Request) -> bool:
    """
    Validate that the request is coming from VAPI by checking its signature.

    Args:
        request: The FastAPI request object

    Returns:
        bool: True if the request is valid, False otherwise

    Note:
        This is a placeholder implementation. You'll need to implement the
        actual validation logic based on VAPI's authentication requirements.
    """
    # Get VAPI secret from environment variables
    vapi_secret = os.environ.get("VAPI_SECRET")

    if not vapi_secret:
        logger.warning("VAPI_SECRET environment variable not set")
        return True  # Allow requests without validation in development

    # Get signature and timestamp from headers
    signature = request.headers.get(VAPI_SECRET_HEADER)
    timestamp = request.headers.get(VAPI_TIMESTAMP_HEADER)

    if not signature or not timestamp:
        logger.warning(
            f"Missing required headers: {VAPI_SECRET_HEADER} or {VAPI_TIMESTAMP_HEADER}"
        )
        return False

    # TODO: Implement signature verification logic here
    # This would typically involve:
    # 1. Creating a signature from the request body and the timestamp
    # 2. Comparing it with the provided signature

    return True
