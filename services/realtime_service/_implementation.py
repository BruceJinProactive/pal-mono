"""
OpenAI Realtime Voice service implementation.

Provides RealtimeSession class for managing OpenAI Realtime API connections
with callback support and factory function for creating sessions.
"""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.tables import Project
from db.tables.types import Channel
from services.agent_service._raw_config import RawConfig
from utils.log import logger

from ._config import RealtimeConfig


class RealtimeSession:
    """
    Manages OpenAI Realtime API connection for voice conversations.

    Handles bidirectional audio streaming between Twilio and OpenAI's
    Realtime API using WebSocket connections managed by AsyncOpenAI SDK.
    Supports callback-based event handling for extensibility.
    """

    def __init__(
        self,
        api_key: str,
        config: RealtimeConfig,
        on_interruption: Callable[[], Awaitable[None]] | None = None,
    ):
        self.api_key = api_key
        self.config = config
        self.client: AsyncOpenAI | None = None
        self.connection = None
        self.on_interruption = on_interruption
        self._pending_interruption: asyncio.Task[None] | None = None

        # Counters for logging
        self.audio_chunks_sent_to_openai = 0
        self.audio_chunks_received = 0

    async def connect(self) -> None:
        """
        Establish connection to OpenAI Realtime API and configure session.

        Uses RealtimeConfig to generate session configuration with proper
        audio format (audio/pcmu for Twilio compatibility) and VAD settings.

        Raises:
            Exception: If connection fails or API key is invalid
        """
        try:
            # Create AsyncOpenAI client
            self.client = AsyncOpenAI(api_key=self.api_key)

            model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-1.5")
            # Connect to Realtime API (production endpoint)
            self.connection = await self.client.realtime.connect(model=model).enter()

            # Use config to generate session configuration
            session_config = self.config.to_session_config()
            await self.connection.session.update(session=session_config)  # type: ignore[arg-type]

            logger.debug(
                "[REALTIME] Successfully connected and configured OpenAI Realtime API",
                extra={"model": model},
            )

        except Exception as e:
            logger.error(
                "[REALTIME] Failed to connect to OpenAI Realtime API",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )

            # Clean up partial resources before re-raising
            if self.connection is not None:
                try:
                    await self.connection.close()
                except Exception as close_error:
                    logger.error(
                        "[REALTIME] Error closing connection during cleanup",
                        extra={"error": str(close_error)},
                    )

            if self.client is not None:
                try:
                    await self.client.close()
                except Exception as close_error:
                    logger.error(
                        "[REALTIME] Error closing client during cleanup",
                        extra={"error": str(close_error)},
                    )

            # Reset to None after cleanup
            self.connection = None
            self.client = None

            # Re-raise original exception
            raise

    async def send_audio_chunk(self, base64_audio: str) -> None:
        """
        Send audio chunk to OpenAI for processing.

        Args:
            base64_audio: Base64-encoded audio data in configured format

        Raises:
            RuntimeError: If connection is not established
            Exception: If sending audio fails
        """
        if not self.connection:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            self.audio_chunks_sent_to_openai += 1
            await self.connection.input_audio_buffer.append(audio=base64_audio)

            if self.audio_chunks_sent_to_openai % 100 == 0:
                logger.debug(
                    "[REALTIME] Audio chunks sent to OpenAI",
                    extra={
                        "chunks_sent": self.audio_chunks_sent_to_openai,
                        "payload_length": len(base64_audio),
                    },
                )
        except Exception as e:
            logger.error(
                "[REALTIME] Error sending audio to OpenAI",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise

    def _cancel_pending_interruption(self) -> None:
        if self._pending_interruption and not self._pending_interruption.done():
            self._pending_interruption.cancel()
        self._pending_interruption = None

    async def _delayed_interruption(self) -> None:
        delay_s = self.config.interruption_delay_ms / 1000.0
        try:
            await asyncio.sleep(delay_s)
        except asyncio.CancelledError:
            return

        # Cancel OpenAI's in-progress response (server-side)
        if self.connection:
            try:
                await self.connection.response.cancel()
                logger.info("[REALTIME] Cancelled OpenAI response after delay")
            except Exception as e:
                logger.warning(
                    "[REALTIME] Failed to cancel OpenAI response",
                    extra={"error": str(e)},
                )

        # Flush Twilio playback buffer (client-side)
        if not self.on_interruption:
            return
        try:
            await asyncio.wait_for(self.on_interruption(), timeout=0.5)
            logger.info("[REALTIME] Twilio clear sent after delay")
        except asyncio.TimeoutError:
            logger.warning("[REALTIME] Interruption callback timed out")
        except Exception as cb_err:
            logger.error(
                "[REALTIME] Interruption callback failed",
                extra={"error": str(cb_err)},
                exc_info=True,
            )

    async def receive_audio_stream(self) -> AsyncIterator[str]:
        """
        Async generator yielding audio chunks and invoking callbacks.

        Listens for all event types from OpenAI Realtime API, dispatches
        to appropriate callbacks, and yields audio chunks for backward
        compatibility with async generator consumers.

        Yields:
            str: Base64-encoded audio data in configured format

        Raises:
            RuntimeError: If connection is not established
        """
        if not self.connection:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            async for event in self.connection:
                event_type = event.type

                # Audio output delta
                if event_type == "response.output_audio.delta":
                    # Safely access delta attribute
                    audio_chunk = getattr(event, "delta", None)
                    if not audio_chunk:
                        logger.warning(
                            "[REALTIME] Audio delta event missing delta attribute"
                        )
                        continue

                    # Increment counter and log periodically
                    self.audio_chunks_received += 1
                    if self.audio_chunks_received % 100 == 0:
                        logger.debug(
                            "[REALTIME] Audio chunks received from OpenAI",
                            extra={
                                "chunks_received": self.audio_chunks_received,
                                "delta_length": len(audio_chunk),
                            },
                        )

                    # Yield audio chunk for consumers
                    yield audio_chunk

                # Transcript events
                elif (
                    event_type
                    == "conversation.item.input_audio_transcription.completed"
                ):
                    transcript_text = getattr(event, "transcript", "")
                    item_id = getattr(event, "item_id", "")

                    # Log user transcripts
                    logger.info(
                        "[REALTIME] User transcript",
                        extra={
                            "transcript": transcript_text,
                            "item_id": item_id,
                        },
                    )

                # User started speaking — schedule interruption with delay
                elif event_type == "input_audio_buffer.speech_started":
                    logger.info("[REALTIME] Speech started, scheduling interruption")
                    self._cancel_pending_interruption()
                    self._pending_interruption = asyncio.create_task(
                        self._delayed_interruption()
                    )

                elif event_type == "input_audio_buffer.speech_stopped":
                    if (
                        self._pending_interruption
                        and not self._pending_interruption.done()
                    ):
                        self._cancel_pending_interruption()
                        logger.debug(
                            "[REALTIME] Speech stopped before delay — "
                            "interruption cancelled (likely cough/noise)"
                        )
                    else:
                        logger.debug("[REALTIME] Speech stopped")

                # Audio response complete
                elif event_type == "response.output_audio.done":
                    logger.debug("[REALTIME] Audio response completed")

                # Assistant transcript completed
                elif event_type == "response.audio_transcript.done":
                    transcript = getattr(event, "transcript", "")
                    logger.info(
                        "[REALTIME] Assistant transcript",
                        extra={"transcript": transcript},
                    )

                # Error events
                elif event_type == "error":
                    error_data = {
                        "type": event.type,
                        "error": getattr(event, "error", str(event)),
                    }
                    logger.error("[REALTIME] API error", extra=error_data)

        except Exception as e:
            logger.error(
                "[REALTIME] Error in event stream",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )
            raise

    async def close(self) -> None:
        """
        Close connection to OpenAI Realtime API.

        Should be called when call ends or on error to clean up resources.
        """
        self._cancel_pending_interruption()

        # Close connection if it exists
        if self.connection:
            try:
                await self.connection.close()
                logger.info("[REALTIME] Closed OpenAI Realtime API connection")
            except Exception as e:
                logger.error(
                    "[REALTIME] Error closing connection",
                    extra={"error": str(e)},
                )

        # Close client if it exists
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.error(
                    "[REALTIME] Error closing client",
                    extra={"error": str(e)},
                )

        # Reset to None
        self.connection = None
        self.client = None


async def create_realtime_session(
    session: AsyncSession,
    recipient_id: str,
) -> RealtimeSession:
    """
    Create and connect RealtimeSession for voice conversations.

    Looks up project by voice channel identifier, retrieves agent configuration,
    and establishes OpenAI Realtime API connection.

    Args:
        session: Database session for lookups
        recipient_id: Phone number or identifier (e.g., "+15551234567")

    Returns:
        RealtimeSession: Connected session ready for audio streaming

    Raises:
        ValueError: If project not found for recipient_id or configuration invalid
        Exception: If connection to OpenAI fails
    """
    # Build channel identifier (e.g., "voice:+15551234567")
    channel_identifier = f"voice:{recipient_id}"

    # Look up project by channel identifier with eager loading of relationships
    query = (
        select(Project)
        .options(selectinload(Project.account))
        .options(selectinload(Project.agent))
        .filter(Project.channel_identifiers.contains([channel_identifier]))
    )
    result = await session.execute(query)
    project = result.scalar_one_or_none()

    if not project:
        raise ValueError(
            f"Project not found for channel identifier: {channel_identifier}"
        )

    # Extract relationships (already loaded via selectinload)
    agent = project.agent
    account = project.account

    if not agent:
        raise ValueError(f"Agent not found for project: {project.name}")

    # Build agent configuration using existing pattern
    raw_config = RawConfig(
        agent=agent,
        project=project,
        account=account,
        user_id=uuid.uuid4(),  # No user context for voice calls
        conversation_id=uuid.uuid4(),  # Generate new conversation ID
        channel=Channel.VOICE,
        integration=None,
        project_integrations=[],
        faqs=[],
    )

    # Build agent prompt using the same method as other channels
    system_prompt = await raw_config._build_agent_prompt(Channel.VOICE, session)

    if not system_prompt:
        raise ValueError(f"Agent prompt is empty for agent: {agent.id}")

    # Build RealtimeConfig from agent settings
    config = RealtimeConfig(
        system_prompt=system_prompt,
        voice_id="alloy",  # TODO: Get from voice_config
    )

    # Get OpenAI API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    # Create session
    realtime_session = RealtimeSession(
        api_key=api_key,
        config=config,
    )

    await realtime_session.connect()

    logger.info(
        "[REALTIME] Created realtime session",
        extra={
            "project_name": project.name,
            "agent_id": str(agent.id),
        },
    )

    return realtime_session
