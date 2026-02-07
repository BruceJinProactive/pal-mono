import json
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from utils.log import logger


async def handle_twilio_media_stream(websocket: WebSocket):
    """
    Handle Twilio Media Stream WebSocket connection.

    Logs signature information for debugging. Logs all events for understanding
    the Twilio Media Streams protocol flow.

    Args:
        websocket: WebSocket connection from Twilio
    """
    # Log signature information for debugging
    twilio_signature = websocket.headers.get("x-twilio-signature")
    host = websocket.headers.get("host", "")
    path = websocket.url.path
    query = f"?{websocket.url.query}" if websocket.url.query else ""
    full_url = f"wss://{host}{path}{query}"

    logger.debug(
        "[TWILIO_WS] WebSocket connection attempt",
        extra={
            "client_host": websocket.client.host if websocket.client else None,
            "has_signature": twilio_signature is not None,
            "url": full_url,
        },
    )

    # Accept the WebSocket connection
    await websocket.accept()

    # Track connection state
    stream_sid: str | None = None
    call_sid: str | None = None
    start_time = datetime.now(timezone.utc)
    media_packet_count = 0

    logger.debug(
        "[TWILIO_WS] Twilio WebSocket connection established",
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
                    logger.debug(
                        "[TWILIO_WS] Twilio WebSocket 'connected' event received",
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

                    logger.debug(
                        "[TWILIO_WS] Twilio media stream started",
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
                        payload = media_data.get("payload", "")
                        logger.debug(
                            "[TWILIO_WS] Received media packets",
                            extra={
                                "stream_sid": message.get("streamSid"),
                                "packet_count": media_packet_count,
                                "last_sequence": message.get("sequenceNumber"),
                                "last_timestamp": media_data.get("timestamp"),
                                "payload_sample": payload[:50] if payload else "",
                                "payload_length": len(payload),
                            },
                        )

                elif event_type == "stop":
                    # Stream stopped
                    stop_data = message.get("stop", {})
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

                    logger.debug(
                        "[TWILIO_WS] Twilio media stream stopped",
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
                        "[TWILIO_WS] Unknown Twilio WebSocket event type",
                        extra={
                            "event_type": event_type,
                            "stream_sid": stream_sid,
                            "message_keys": list(message.keys()),
                        },
                    )

            except json.JSONDecodeError as e:
                logger.error(
                    "[TWILIO_WS] Failed to parse Twilio WebSocket message",
                    extra={
                        "stream_sid": stream_sid,
                        "error": str(e),
                        "raw_message_preview": raw_message[:200],
                    },
                )
                continue

            except Exception as e:
                logger.error(
                    "[TWILIO_WS] Error processing Twilio WebSocket message",
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
        logger.debug(
            "[TWILIO_WS] Twilio WebSocket disconnected",
            extra={
                "stream_sid": stream_sid,
                "call_sid": call_sid,
                "duration_seconds": duration,
                "total_media_packets": media_packet_count,
            },
        )

    except Exception as e:
        logger.error(
            "[TWILIO_WS] Unexpected error in Twilio WebSocket handler",
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
