import base64
import hashlib
import hmac

from fastapi import HTTPException, Request, status

from utils import secret
from utils.log import logger

from ._util import decrypt_account_name


def get_square_webhook_credentials() -> tuple[str, str]:
    """
    Get Square webhook signature key and webhook URL from secrets manager.

    Returns:
        tuple[str, str]: A tuple containing (signature_key, webhook_url)

    Raises:
        ValueError: If the signature key or webhook URL is not found in secrets
    """
    app_secrets = secret._get_client_secrets()
    signature_key = app_secrets.get("SQUARE_WEBHOOK_SIGNATURE_KEY")
    webhook_url = app_secrets.get("SQUARE_WEBHOOK_URL")

    if not signature_key:
        raise ValueError("SQUARE_WEBHOOK_SIGNATURE_KEY not found in secrets manager")

    if not webhook_url:
        raise ValueError("SQUARE_WEBHOOK_URL not found in secrets manager")

    return signature_key, webhook_url


def is_test_request(request: Request) -> bool:
    """
    Check if the request should bypass signature verification for development or testing.

    This function checks for common development/testing headers that indicate
    the request should skip production security validation.

    Args:
        request: The FastAPI request object

    Returns:
        bool: True if request should bypass verification, False otherwise
    """
    # Check for test headers (both underscore and hyphen variants)
    test_header = "test_mode"

    if request.headers.get(test_header):
        logger.debug(
            f"[Square Webhook] Development/test request detected via '{test_header}' header - bypassing signature verification"
        )
        return True

    return False


def validate_oauth_request(request: Request, is_callback=False):
    if is_callback:
        state = request.query_params.get("state")
        if not state:
            logger.error(f"[Square OAuth] Invalid or missing state parameter: {state}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or missing state parameter",
            )

        # Decrypt the state to get the account name
        try:
            account_name = decrypt_account_name(state)
            return account_name
        except ValueError as e:
            logger.error(f"[Square OAuth] Failed to decrypt state: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return True


def validate_square_webhook_request(request: Request, body: bytes) -> bool:
    """
    Validate Square webhook request with proper HMAC-SHA256 signature verification.

    This function follows Square's actual implementation:
    - Uses only x-square-hmacsha256-signature header (no timestamp needed)
    - Creates signature from: HMAC-SHA256(notification_url + payload, signature_key)
    - Base64 encodes the result for comparison
    - Skips verification if is_test header is present

    Args:
        request: The FastAPI request object
        body: The raw request body as bytes

    Returns:
        bool: True if webhook signature is valid, False otherwise
    """
    try:
        # Check if this is a development or test request that should bypass verification
        is_test = is_test_request(request)
        if is_test:
            return True

        # Get signature from headers (Square's actual header format)
        signature = request.headers.get("x-square-hmacsha256-signature")

        if not signature:
            logger.warning(
                "[Square Webhook] Missing required header: x-square-hmacsha256-signature"
            )
            return False

        # Get Square webhook signature key and URL from secrets manager
        try:
            signature_key, webhook_url = get_square_webhook_credentials()
        except ValueError as e:
            logger.error(f"[Square Webhook] {e}")
            return False  # Reject requests without signature key in production

        # Decode the request body
        raw_body = body.decode("utf-8")

        # Construct the message using fixed webhook URL from configuration
        message = webhook_url + raw_body

        # Compute HMAC-SHA256 signature using fixed webhook URL
        computed_signature = base64.b64encode(
            hmac.new(
                signature_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
            ).digest()
        ).decode("utf-8")

        # Secure comparison to prevent timing attacks
        is_valid = hmac.compare_digest(signature, computed_signature)

        if not is_valid:
            logger.warning(
                "[Square Webhook] Invalid signature",
                extra={
                    "webhook_url": webhook_url,
                    "expected_signature": computed_signature[:10] + "...",
                    "received_signature": signature[:10] + "...",
                },
            )

        return is_valid

    except Exception as e:
        logger.error(f"[Square Webhook] Error validating signature: {e}")
        return False
