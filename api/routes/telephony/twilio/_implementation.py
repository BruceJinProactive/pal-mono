import asyncio
import json
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from db.session import AsyncSessionLocal
from services import realtime_service
from services.realtime_service import RealtimeSession
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
    realtime_session: RealtimeSession | None = None
    background_task = None

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
                    custom_params = start_data.get("customParameters", {})
                    recipient_id = custom_params.get("to_number")

                    tracks = start_data.get("tracks")
                    media_format = start_data.get("mediaFormat")

                    logger.debug(
                        "[TWILIO_WS] Twilio media stream started",
                        extra={
                            "stream_sid": stream_sid,
                            "call_sid": call_sid,
                            "account_sid": account_sid,
                            "tracks": tracks,
                            "media_format": media_format,
                            "custom_parameters": start_data.get("customParameters"),
                        },
                    )

                    # Check if outbound track is enabled
                    if tracks and "outbound" not in tracks:
                        logger.warning(
                            "[TWILIO_WS] Outbound track not enabled - audio won't be sent to caller",
                            extra={"tracks": tracks, "stream_sid": stream_sid},
                        )

                    # Check for required stream_sid
                    if not stream_sid:
                        logger.error("[TWILIO_WS] Missing streamSid in start event")
                        await websocket.close(code=1008, reason="Missing streamSid")
                        return

                    # Check for required recipient_id
                    if not recipient_id:
                        logger.error(
                            "[TWILIO_WS] Missing recipient_id in custom parameters"
                        )
                        await websocket.close(code=1008, reason="Missing recipient_id")
                        return

                    # Initialize realtime session
                    async with AsyncSessionLocal() as db_session:
                        try:
                            realtime_session = (
                                await realtime_service.create_realtime_session(
                                    db_session, recipient_id
                                )
                            )
                        except ValueError as e:
                            logger.error(f"[TWILIO_WS] Project lookup failed: {e}")
                            await websocket.close(code=1008, reason="Project not found")
                            return
                        except Exception as e:
                            logger.error(
                                "[TWILIO_WS] Failed to create realtime session",
                                extra={"error": str(e), "error_type": type(e).__name__},
                                exc_info=True,
                            )
                            await websocket.close(
                                code=1011, reason="Service unavailable"
                            )
                            return

                    # Type narrowing: at this point stream_sid is guaranteed to be str
                    assert stream_sid is not None

                    # Background task to stream OpenAI responses back to Twilio
                    # Bind current values to avoid closure issues (B023)
                    async def stream_openai_to_twilio(
                        session: RealtimeSession = realtime_session,
                        sid: str = stream_sid,
                    ):
                        chunk_count = 0
                        logger.debug(
                            "[TWILIO_WS] Background task started: streaming OpenAI → Twilio",
                            extra={"stream_sid": sid},
                        )
                        try:
                            async for audio_chunk in session.receive_audio_stream():
                                chunk_count += 1

                                # Log first chunk for debugging
                                if chunk_count == 1:
                                    logger.debug(
                                        "[TWILIO_WS] First audio chunk received from OpenAI",
                                        extra={
                                            "chunk_length": len(audio_chunk),
                                            "chunk_preview": (
                                                audio_chunk[:50] if audio_chunk else ""
                                            ),
                                            "stream_sid": sid,
                                        },
                                    )

                                # Send audio back to Twilio using media message format
                                media_message = {
                                    "event": "media",
                                    "streamSid": sid,
                                    "media": {"payload": audio_chunk},
                                }

                                # Log first message structure for debugging
                                if chunk_count == 1:
                                    logger.debug(
                                        "[TWILIO_WS] First media message structure",
                                        extra={
                                            "message_keys": list(media_message.keys()),
                                            "media_keys": list(
                                                media_message["media"].keys()
                                            ),
                                            "payload_type": type(audio_chunk).__name__,
                                            "payload_is_string": isinstance(
                                                audio_chunk, str
                                            ),
                                        },
                                    )

                                await websocket.send_text(json.dumps(media_message))

                                # Log periodically (every 50 chunks) to avoid log spam
                                if chunk_count % 50 == 0:
                                    logger.debug(
                                        "[TWILIO_WS] Sent audio chunk to Twilio",
                                        extra={
                                            "stream_sid": sid,
                                            "chunk_count": chunk_count,
                                            "payload_length": len(audio_chunk),
                                        },
                                    )
                        except Exception as e:
                            logger.error(
                                "[TWILIO_WS] Error streaming from OpenAI",
                                extra={"error": str(e), "error_type": type(e).__name__},
                                exc_info=True,
                            )
                        finally:
                            logger.debug(
                                "[TWILIO_WS] Background task completed: streaming OpenAI → Twilio",
                                extra={
                                    "stream_sid": sid,
                                    "total_chunks_sent": chunk_count,
                                },
                            )

                    # Start background task
                    background_task = asyncio.create_task(stream_openai_to_twilio())
                    logger.debug(
                        "[TWILIO_WS] Background task created for OpenAI → Twilio streaming",
                        extra={"stream_sid": stream_sid},
                    )

                elif event_type == "media":
                    # Audio data packet
                    media_packet_count += 1
                    media_data = message.get("media", {})
                    payload = media_data.get("payload", "")

                    # Forward to OpenAI
                    if realtime_session:
                        try:
                            await realtime_session.send_audio_chunk(payload)

                            # Log periodically (every 100 packets) to avoid log spam
                            if media_packet_count % 100 == 0:
                                logger.debug(
                                    "[TWILIO_WS] Forwarded audio chunk to OpenAI",
                                    extra={
                                        "stream_sid": message.get("streamSid"),
                                        "packet_count": media_packet_count,
                                        "sequence": message.get("sequenceNumber"),
                                        "payload_length": len(payload),
                                    },
                                )
                        except Exception as e:
                            logger.error(
                                "[TWILIO_WS] Error sending audio to OpenAI",
                                extra={"error": str(e), "error_type": type(e).__name__},
                            )

                    # Log periodically (every 100 packets) to avoid log spam
                    if media_packet_count % 100 == 0:
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

                    # Cleanup realtime session
                    if realtime_session:
                        await realtime_session.close()
                    if background_task:
                        background_task.cancel()

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
        # Cleanup realtime session if still active
        if "realtime_session" in locals() and realtime_session:
            await realtime_session.close()
        if "background_task" in locals() and background_task:
            background_task.cancel()

        # Ensure WebSocket is closed
        try:
            await websocket.close()
        except Exception:
            pass
