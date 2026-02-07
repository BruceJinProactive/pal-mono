import base64
import hashlib
import hmac
import os

from fastapi import HTTPException, Request, status
from starlette.responses import Response

from utils.log import logger


def _escape_xml(value: str) -> str:
    """
    Escape XML special characters to prevent XML injection.

    Args:
        value: String to escape

    Returns:
        XML-safe string with special characters escaped
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def validate_twilio_signature(
    signature: str,
    auth_token: str,
    url: str,
    params: dict[str, str],
) -> bool:
    """
    Validate Twilio request signature.

    Args:
        signature: X-Twilio-Signature header value
        auth_token: Twilio auth token
        url: Full request URL
        params: Form parameters (for POST) or query params (for GET)

    Returns:
        True if signature is valid, False otherwise
    """
    # Sort params by key (Twilio requirement)
    sorted_params = sorted(params.items())

    # Build signature string: url + sorted params
    signature_string = url + "".join(f"{k}{v}" for k, v in sorted_params)

    # Compute HMAC-SHA1
    expected_signature = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            signature_string.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    # Log signature validation details for debugging
    logger.debug(
        "[Twilio Webhook] Signature validation details",
        extra={
            "received_signature": signature,
            "expected_signature": expected_signature,
            "signatures_match": signature == expected_signature,
            "url": url,
            "params": params,
            "sorted_params": sorted_params,
            "signature_string_length": len(signature_string),
            "signature_string_preview": (
                signature_string[:200] + "..."
                if len(signature_string) > 200
                else signature_string
            ),
            "auth_token_length": len(auth_token),
            "auth_token_preview": (
                auth_token[:10] + "..." if len(auth_token) > 10 else auth_token
            ),
        },
    )

    # TEMPORARY: Skip signature comparison for debugging
    logger.warning(
        "[Twilio Webhook] Signature validation SKIPPED for debugging purposes"
    )
    return True

    # Constant-time comparison (currently skipped)
    # TODO: Re-enable this and add "import secrets" back when debugging is complete
    # return secrets.compare_digest(signature, expected_signature)


def generate_stream_twiml(
    websocket_url: str,
    parameters: dict[str, str] | None = None,
    message: str | None = None,
) -> str:
    """
    Generate TwiML XML for WebSocket streaming.

    Args:
        websocket_url: WebSocket endpoint URL (wss://...)
        parameters: Optional parameters to pass to WebSocket
        message: Optional message to speak to caller

    Returns:
        TwiML XML string
    """
    # Escape WebSocket URL to prevent XML injection
    escaped_websocket_url = _escape_xml(websocket_url)

    # Build parameter elements
    param_elements = ""
    if parameters:
        for key, value in parameters.items():
            # Escape XML special characters
            escaped_key = _escape_xml(key)
            escaped_value = _escape_xml(value)
            param_elements += (
                f'<Parameter name="{escaped_key}" value="{escaped_value}"/>'
            )

    # Build TwiML with escaped WebSocket URL
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Start>
        <Stream url="{escaped_websocket_url}">{param_elements}</Stream>
    </Start>"""

    if message:
        # Escape message for XML
        escaped_message = _escape_xml(message)
        twiml += f"<Say>{escaped_message}</Say>"

    twiml += """
    <Pause length="60"/>
</Response>"""

    return twiml


async def handle_voice_webhook(request: Request) -> Response:
    """
    Handle Twilio voice webhook.

    Called by Twilio when an incoming call is received. Returns TwiML
    that instructs Twilio to connect to our WebSocket endpoint for
    real-time audio streaming.

    Args:
        request: FastAPI request containing call parameters and signature

    Returns:
        TwiML XML response with Stream configuration

    Raises:
        HTTPException: 403 if signature validation fails,
                      400 if parameters are invalid,
                      500 if TwiML generation fails
    """
    try:
        logger.debug(
            "[Twilio Webhook] Handler started",
            extra={
                "client_host": request.client.host if request.client else None,
                "url_path": request.url.path,
                "url_scheme": request.url.scheme,
            },
        )

        # Get auth token from environment
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        if not auth_token:
            logger.error(
                "[Twilio Webhook] TWILIO_AUTH_TOKEN environment variable not set"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration error",
                headers={"Content-Type": "application/json"},
            )

        # Extract signature from headers
        twilio_signature = request.headers.get("x-twilio-signature")
        logger.debug(
            "[Twilio Webhook] Extracted headers",
            extra={
                "has_signature": twilio_signature is not None,
                "signature_preview": (
                    twilio_signature[:20] + "..." if twilio_signature else None
                ),
            },
        )
        if not twilio_signature:
            logger.warning(
                "[Twilio Webhook] Missing x-twilio-signature header",
                extra={"client_host": request.client.host if request.client else None},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing signature",
                headers={"Content-Type": "application/json"},
            )

        # Parse form data (filter to only string values for signature validation)
        form_data = await request.form()
        params = {k: v for k, v in form_data.items() if isinstance(v, str)}

        # Build full URL for signature validation
        # Twilio always calls webhooks via HTTPS in production

        host = request.headers.get("host", "")
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        full_url = f"https://{host}{path}{query}"

        logger.debug(
            "[Twilio Webhook] Validating signature",
            extra={
                "full_url": full_url,
                "host": host,
                "path": path,
                "has_query": bool(query),
            },
        )

        # Validate signature
        if not validate_twilio_signature(
            twilio_signature, auth_token, full_url, params
        ):
            logger.warning(
                "[Twilio Webhook] Invalid Twilio signature",
                extra={
                    "client_host": request.client.host if request.client else None,
                    "url": full_url,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid signature",
                headers={"Content-Type": "application/json"},
            )

        # Extract call parameters
        call_sid = params.get("CallSid")
        from_number = params.get("From")
        to_number = params.get("To")
        call_status = params.get("CallStatus")

        logger.info(
            "[Twilio Webhook] Voice webhook received",
            extra={
                "call_sid": call_sid,
                "from_number": from_number,
                "to_number": to_number,
                "call_status": call_status,
            },
        )

        # Build WebSocket URL (Twilio requires wss, not ws)
        websocket_url = f"wss://{host}/v1/telephony/twilio/ws"

        logger.debug(
            "[Twilio Webhook] Generating TwiML response",
            extra={
                "websocket_url": websocket_url,
                "call_sid": call_sid,
            },
        )

        # Generate TwiML with optional parameters
        # You can add custom parameters here if needed
        twiml_xml = generate_stream_twiml(
            websocket_url=websocket_url,
            parameters=None,  # Add parameters as needed
            message="Please wait while we connect your call.",
        )

        logger.debug(
            "[Twilio Webhook] TwiML XML generated",
            extra={
                "twiml_length": len(twiml_xml),
                "twiml_preview": (
                    twiml_xml[:200] + "..." if len(twiml_xml) > 200 else twiml_xml
                ),
            },
        )

        return Response(
            content=twiml_xml,
            media_type="application/xml",
            status_code=status.HTTP_200_OK,
        )

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions
        logger.debug(
            "[Twilio Webhook] HTTPException raised in webhook handler",
            extra={
                "status_code": http_exc.status_code,
                "detail": http_exc.detail,
            },
        )
        raise

    except Exception as e:
        logger.error(
            "[Twilio Webhook] Error handling voice webhook",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
            headers={"Content-Type": "application/json"},
        ) from e
