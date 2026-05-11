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
import base64
import json
import time
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

        # Background tasks
        self.streaming_task: Optional[asyncio.Task] = None
        self._bg_audio_task: Optional[asyncio.Task] = None
        self._last_agent_audio_at: float = 0.0

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
        return

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

        # Start continuous background audio sender if mixer is configured
        if self.realtime_session.mixer:
            self._bg_audio_task = asyncio.create_task(self._send_background_audio())

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
            if self.media_packet_count % 100 == 0:
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

    async def _handle_barge_in(self) -> None:
        """Send Twilio clear message to flush queued audio on barge-in."""
        if not self.stream_sid:
            return

        try:
            clear_message = json.dumps(
                {
                    "event": "clear",
                    "streamSid": self.stream_sid,
                }
            )
            await self.twilio_ws.send_text(clear_message)
            logger.info(
                "[VOICE_HANDLER] Barge-in: sent Twilio clear",
                extra={"stream_sid": self.stream_sid},
            )
        except Exception as e:
            logger.error(
                "[VOICE_HANDLER] Error sending Twilio clear on barge-in",
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

        Forwards µ-law audio to Twilio, mixing in background audio if configured.
        """
        mixer = self.realtime_session.mixer
        try:
            async for (
                audio_chunk_mulaw_b64
            ) in self.realtime_session.receive_audio_stream():
                self._last_agent_audio_at = time.monotonic()
                self.audio_chunks_sent += 1

                try:
                    if mixer:
                        try:
                            raw_bytes = base64.b64decode(audio_chunk_mulaw_b64)
                            mixed_bytes = mixer.mix_chunk(raw_bytes)
                            payload = base64.b64encode(mixed_bytes).decode()
                        except Exception:
                            payload = audio_chunk_mulaw_b64
                    else:
                        payload = audio_chunk_mulaw_b64

                    media_message = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": payload,
                        },
                    }

                    await self.twilio_ws.send_text(json.dumps(media_message))

                    # Log periodically
                    if self.audio_chunks_sent % 100 == 0:
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
            pass

    async def _send_background_audio(self) -> None:
        """Send background audio frames during silence (when agent is not speaking)."""
        mixer = self.realtime_session.mixer
        if not mixer:
            return

        # 160 bytes = 20ms at 8kHz µ-law
        silence_frame = bytes([0xFF] * 160)

        try:
            while True:
                await asyncio.sleep(0.02)

                agent_recently_spoke = (
                    time.monotonic() - self._last_agent_audio_at < 0.1
                )
                if agent_recently_spoke or not self.stream_sid:
                    continue

                try:
                    mixed = mixer.mix_chunk(silence_frame)
                    payload = base64.b64encode(mixed).decode()
                    media_message = json.dumps(
                        {
                            "event": "media",
                            "streamSid": self.stream_sid,
                            "media": {"payload": payload},
                        }
                    )
                    await self.twilio_ws.send_text(media_message)
                except Exception as e:
                    logger.error(
                        "[VOICE_HANDLER] Background audio send failed",
                        extra={"stream_sid": self.stream_sid, "error": str(e)},
                    )

        except asyncio.CancelledError:
            pass

    async def _cleanup(self) -> None:
        """Clean up resources."""
        # Cancel background audio task
        if self._bg_audio_task and not self._bg_audio_task.done():
            self._bg_audio_task.cancel()
            try:
                await self._bg_audio_task
            except asyncio.CancelledError:
                pass

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

        return
