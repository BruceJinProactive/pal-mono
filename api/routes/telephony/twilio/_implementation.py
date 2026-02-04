import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from utils.log import logger


async def handle_twilio_media_stream(websocket: WebSocket):
    """
    Handle Twilio Media Stream WebSocket connection.

    Validates Twilio's X-Twilio-Signature header before accepting the connection
    to ensure requests originate from Twilio. Logs all events for understanding
    the Twilio Media Streams protocol flow.

    Args:
        websocket: WebSocket connection from Twilio
    """
    # Validate Twilio signature before accepting connection
    twilio_signature = websocket.headers.get("x-twilio-signature")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

    if not auth_token:
        logger.error(
            "TWILIO_AUTH_TOKEN environment variable not set",
            extra={"client_host": websocket.client.host if websocket.client else None},
        )
        await websocket.close(code=1008)
        return

    if not twilio_signature:
        logger.warning(
            "Missing x-twilio-signature header",
            extra={"client_host": websocket.client.host if websocket.client else None},
        )
        await websocket.close(code=1008)
        return

    # Build the full URL for signature validation
    # For WebSocket connections, Twilio signs the upgrade request URL
    scheme = "wss" if websocket.url.scheme == "wss" else "ws"
    # Convert to https/http for signature validation (Twilio uses http(s) in signature)
    signature_scheme = "https" if scheme == "wss" else "http"
    host = websocket.headers.get("host", "")
    path = websocket.url.path
    query = f"?{websocket.url.query}" if websocket.url.query else ""
    full_url = f"{signature_scheme}://{host}{path}{query}"

    # Compute expected signature using HMAC-SHA1
    expected_signature = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"), full_url.encode("utf-8"), hashlib.sha1
        ).digest()
    ).decode("utf-8")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(twilio_signature, expected_signature):
        logger.warning(
            "Invalid Twilio signature",
            extra={
                "client_host": websocket.client.host if websocket.client else None,
                "url": full_url,
            },
        )
        await websocket.close(code=1008)
        return

    # Signature is valid, accept the WebSocket connection
    await websocket.accept()

    logger.info(
        "Twilio signature validated successfully",
        extra={
            "client_host": websocket.client.host if websocket.client else None,
        },
    )

    # Track connection state
    stream_sid: str | None = None
    call_sid: str | None = None
    start_time = datetime.now(timezone.utc)
    media_packet_count = 0

    logger.info(
        "Twilio WebSocket connection established",
        extra={
            "client_host": websocket.client.host if websocket.client else None,
            "client_port": websocket.client.port if websocket.client else None,
        },
    )

    try:
        while True:
            # Receive message from Twilio
            raw_message = await websocket.receive_text()
            event_type = ""

            try:
                # Parse JSON message
                message = json.loads(raw_message)
                event_type = message.get("event", "")

                if event_type == "connected":
                    # Initial connection event
                    logger.info(
                        "Twilio WebSocket 'connected' event received",
                        extra={
                            "protocol": message.get("protocol"),
                            "version": message.get("version"),
                        },
                    )

                elif event_type == "start":
                    # Stream start with metadata
                    stream_sid = message.get("streamSid")
                    start_data = message.get("start", {})
                    call_sid = start_data.get("callSid")
                    account_sid = start_data.get("accountSid")

                    logger.info(
                        "Twilio media stream started",
                        extra={
                            "stream_sid": stream_sid,
                            "call_sid": call_sid,
                            "account_sid": account_sid,
                            "tracks": start_data.get("tracks"),
                            "media_format": start_data.get("mediaFormat"),
                            "custom_parameters": start_data.get("customParameters"),
                        },
                    )

                elif event_type == "media":
                    # Audio data packet
                    media_packet_count += 1
                    media_data = message.get("media", {})

                    # Log periodically (every 100 packets) to avoid log spam
                    if media_packet_count % 100 == 0:
                        logger.debug(
                            "Received media packets",
                            extra={
                                "stream_sid": message.get("streamSid"),
                                "packet_count": media_packet_count,
                                "last_sequence": message.get("sequenceNumber"),
                                "last_timestamp": media_data.get("timestamp"),
                                "payload_size_bytes": len(
                                    media_data.get("payload", "")
                                ),
                            },
                        )

                elif event_type == "stop":
                    # Stream stopped
                    stop_data = message.get("stop", {})
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

                    logger.info(
                        "Twilio media stream stopped",
                        extra={
                            "stream_sid": message.get("streamSid"),
                            "call_sid": stop_data.get("callSid"),
                            "account_sid": stop_data.get("accountSid"),
                            "duration_seconds": duration,
                            "total_media_packets": media_packet_count,
                        },
                    )

                    # Clean disconnect
                    break

                else:
                    # Unknown event type
                    logger.warning(
                        "Unknown Twilio WebSocket event type",
                        extra={
                            "event_type": event_type,
                            "stream_sid": stream_sid,
                            "message_keys": list(message.keys()),
                        },
                    )

            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse Twilio WebSocket message",
                    extra={
                        "stream_sid": stream_sid,
                        "error": str(e),
                        "raw_message_preview": raw_message[:200],
                    },
                )
                continue

            except Exception as e:
                logger.error(
                    "Error processing Twilio WebSocket message",
                    extra={
                        "stream_sid": stream_sid,
                        "event_type": event_type,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                    exc_info=True,
                )
                continue

    except WebSocketDisconnect:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            "Twilio WebSocket disconnected",
            extra={
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "duration_seconds": duration,
                "total_media_packets": media_packet_count,
            },
        )

    except Exception as e:
        logger.error(
            "Unexpected error in Twilio WebSocket handler",
            extra={
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )

    finally:
        # Ensure WebSocket is closed
        try:
            await websocket.close()
        except Exception:
            pass
