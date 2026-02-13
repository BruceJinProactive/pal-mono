"""
VoiceCallHandler: Orchestrates Twilio ↔ OpenAI Realtime bidirectional audio.

Responsibilities:
- Manage two WebSocket connections (Twilio and OpenAI)
- Route audio bidirectionally (no conversion - both use g711_ulaw)
- Handle Twilio Media Stream protocol events
- Integrate with message_service for transcript logging (future)
- Integrate with tool registry for function execution (future)
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from services.realtime_service import RealtimeSession
from utils.log import logger


class VoiceCallHandler:
    """Handles voice call orchestration between Twilio and OpenAI Realtime API."""

    def __init__(
        self,
        twilio_websocket: WebSocket,
        realtime_session: RealtimeSession,
    ):
        """
        Initialize VoiceCallHandler.

        Args:
            twilio_websocket: WebSocket connection from Twilio
            realtime_session: Connected RealtimeSession instance
        """
        self.twilio_ws = twilio_websocket
        self.realtime_session = realtime_session

        # Connection state
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None
        self.start_time = datetime.now(timezone.utc)
        self.media_packet_count = 0
        self.audio_chunks_sent = 0

        # Background task for OpenAI → Twilio streaming
        self.streaming_task: Optional[asyncio.Task] = None

    async def handle_call(self, start_event: Optional[dict] = None) -> None:
        """
        Main handler for voice call.

        Manages Twilio WebSocket events and coordinates with OpenAI.

        Args:
            start_event: Optional 'start' event to process before main loop
        """
        try:
            # Process start event if provided (before main loop)
            if start_event:
                await self._handle_start(start_event)

            # Main event loop for Twilio messages
            while True:
                raw_message = await self.twilio_ws.receive_text()

                try:
                    message = json.loads(raw_message)
                    event_type = message.get("event", "")

                    if event_type == "connected":
                        await self._handle_connected(message)

                    elif event_type == "start":
                        await self._handle_start(message)

                    elif event_type == "media":
                        await self._handle_media(message)

                    elif event_type == "stop":
                        await self._handle_stop(message)
                        break  # Exit loop on stop

                    else:
                        logger.warning(
                            "[VOICE_HANDLER] Unknown event type",
                            extra={"event_type": event_type},
                        )

                except json.JSONDecodeError as e:
                    logger.error(
                        "[VOICE_HANDLER] Failed to parse Twilio message",
                        extra={"error": str(e), "raw_message": raw_message[:200]},
                    )
                    continue

        except WebSocketDisconnect:
            logger.info("[VOICE_HANDLER] Twilio disconnected")

        except Exception as e:
            logger.error(
                "[VOICE_HANDLER] Unexpected error",
                extra={"error": str(e)},
                exc_info=True,
            )

        finally:
            await self._cleanup()

    async def _handle_connected(self, message: dict) -> None:
        """Handle Twilio 'connected' event."""
        logger.debug(
            "[VOICE_HANDLER] Twilio connected",
            extra={
                "protocol": message.get("protocol"),
                "version": message.get("version"),
            },
        )

    async def _handle_start(self, message: dict) -> None:
        """
        Handle Twilio 'start' event.

        Extracts stream metadata and starts OpenAI → Twilio streaming.
        """
        self.stream_sid = message.get("streamSid")
        start_data = message.get("start", {})
        self.call_sid = start_data.get("callSid")

        logger.info(
            "[VOICE_HANDLER] Stream started",
            extra={
                "stream_sid": self.stream_sid,
                "call_sid": self.call_sid,
                "tracks": start_data.get("tracks"),
                "media_format": start_data.get("mediaFormat"),
            },
        )

        # Start background task to stream OpenAI → Twilio
        self.streaming_task = asyncio.create_task(self._stream_openai_to_twilio())

    async def _handle_media(self, message: dict) -> None:
        """
        Handle Twilio 'media' event (audio from caller).

        Forwards µ-law audio directly to OpenAI (no conversion needed).
        Both Twilio and OpenAI support g711_ulaw format natively.
        """
        self.media_packet_count += 1

        media_data = message.get("media", {})
        payload_mulaw_b64 = media_data.get("payload", "")

        if not payload_mulaw_b64:
            return

        try:
            # Pass µ-law audio directly to OpenAI (no conversion)
            # Both Twilio and OpenAI use g711_ulaw format
            await self.realtime_session.send_audio_chunk(payload_mulaw_b64)

            # Log periodically
            if self.media_packet_count % 20 == 0:
                logger.debug(
                    "[VOICE_HANDLER] Audio Twilio→OpenAI",
                    extra={
                        "stream_sid": self.stream_sid,
                        "packet_count": self.media_packet_count,
                        "payload_length": len(payload_mulaw_b64),
                    },
                )

        except Exception as e:
            logger.error(
                "[VOICE_HANDLER] Error processing audio",
                extra={"error": str(e)},
                exc_info=True,
            )

    async def _handle_stop(self, message: dict) -> None:
        """Handle Twilio 'stop' event."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        logger.info(
            "[VOICE_HANDLER] Stream stopped",
            extra={
                "stream_sid": self.stream_sid,
                "call_sid": self.call_sid,
                "duration_seconds": duration,
                "media_packets": self.media_packet_count,
                "audio_chunks_sent": self.audio_chunks_sent,
            },
        )

    async def _stream_openai_to_twilio(self) -> None:
        """
        Background task: Stream audio from OpenAI → Twilio.

        Forwards µ-law audio directly to Twilio (no conversion needed).
        Both OpenAI and Twilio use g711_ulaw format natively.
        """
        try:
            logger.debug("[VOICE_HANDLER] Started OpenAI→Twilio streaming")

            async for (
                audio_chunk_mulaw_b64
            ) in self.realtime_session.receive_audio_stream():
                self.audio_chunks_sent += 1

                try:
                    # Pass µ-law audio directly to Twilio (no conversion)
                    # Both OpenAI and Twilio use g711_ulaw format
                    media_message = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": audio_chunk_mulaw_b64,
                        },
                    }

                    await self.twilio_ws.send_text(json.dumps(media_message))

                    # Log first chunk for debugging
                    if self.audio_chunks_sent == 1:
                        logger.debug(
                            "[VOICE_HANDLER] First audio chunk OpenAI→Twilio",
                            extra={
                                "payload_length": len(audio_chunk_mulaw_b64),
                                "stream_sid": self.stream_sid,
                            },
                        )

                    # Log periodically
                    if self.audio_chunks_sent % 10 == 0:
                        logger.debug(
                            "[VOICE_HANDLER] Audio OpenAI→Twilio",
                            extra={
                                "stream_sid": self.stream_sid,
                                "chunks_sent": self.audio_chunks_sent,
                            },
                        )

                except Exception as e:
                    logger.error(
                        "[VOICE_HANDLER] Error converting/sending audio",
                        extra={"error": str(e)},
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(
                "[VOICE_HANDLER] Streaming task error",
                extra={"error": str(e)},
                exc_info=True,
            )

        finally:
            logger.debug(
                "[VOICE_HANDLER] Stopped OpenAI→Twilio streaming",
                extra={"total_chunks": self.audio_chunks_sent},
            )

    async def _cleanup(self) -> None:
        """Clean up resources."""
        # Cancel streaming task
        if self.streaming_task and not self.streaming_task.done():
            self.streaming_task.cancel()
            try:
                await self.streaming_task
            except asyncio.CancelledError:
                pass

        # Close realtime session
        if self.realtime_session:
            await self.realtime_session.close()

        # Close Twilio WebSocket
        try:
            await self.twilio_ws.close()
        except Exception:
            pass

        logger.debug("[VOICE_HANDLER] Cleanup complete")
