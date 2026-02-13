"""
OpenAI Realtime Voice service implementation.

Provides RealtimeSession class for managing OpenAI Realtime API connections
with callback support and factory function for creating sessions.
"""

import os
import uuid
from typing import AsyncIterator, Callable, Optional

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
        # Callbacks (all optional)
        on_audio_delta: Optional[Callable[[str], None]] = None,
        on_audio_transcript: Optional[Callable[[dict], None]] = None,
        on_function_call: Optional[Callable[[str, dict], dict]] = None,
        on_error: Optional[Callable[[dict], None]] = None,
    ):
        """
        Initialize RealtimeSession.

        Args:
            api_key: OpenAI API key for authentication
            config: RealtimeConfig with session configuration
            on_audio_delta: Callback for audio chunks (base64 string)
            on_audio_transcript: Callback for transcript events (dict)
            on_function_call: Callback for function calls (name, args) -> result
            on_error: Callback for error events (dict)
        """
        self.api_key = api_key
        self.config = config
        self.client: AsyncOpenAI | None = None
        self.connection = None

        # Store callbacks
        self._on_audio_delta = on_audio_delta
        self._on_audio_transcript = on_audio_transcript
        self._on_function_call = on_function_call
        self._on_error = on_error

        # Counters for logging
        self.audio_chunks_sent_to_openai = 0

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

            # Connect to Realtime API (production endpoint)
            logger.debug("[REALTIME] Attempting to connect to OpenAI Realtime API")
            self.connection = await self.client.realtime.connect(
                model="gpt-realtime"
            ).enter()
            logger.debug("[REALTIME] Connection established successfully")

            # Use config to generate session configuration
            session_config = self.config.to_session_config()

            logger.debug(
                "[REALTIME] Sending session configuration",
                extra={
                    "audio_input_format": self.config.input_audio_format,
                    "audio_output_format": self.config.output_audio_format,
                    "voice": self.config.voice_id,
                },
            )
            await self.connection.session.update(session=session_config)  # type: ignore[arg-type]

            logger.debug(
                "[REALTIME] Successfully connected and configured OpenAI Realtime API",
                extra={
                    "model": "gpt-realtime",
                    "has_callbacks": any(
                        [
                            self._on_audio_delta,
                            self._on_audio_transcript,
                            self._on_function_call,
                            self._on_error,
                        ]
                    ),
                },
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

            if self.audio_chunks_sent_to_openai == 1:
                logger.debug(
                    "[REALTIME] First audio chunk sent to OpenAI",
                    extra={"payload_length": len(base64_audio)},
                )
            elif self.audio_chunks_sent_to_openai % 20 == 0:
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
            logger.debug("[REALTIME] Starting to listen for OpenAI events")
            async for event in self.connection:
                event_type = event.type

                logger.debug(
                    "[REALTIME] Event received",
                    extra={
                        "event_type": event_type,
                        "event_id": getattr(event, "event_id", None),
                    },
                )

                # Audio output delta
                if event_type == "response.output_audio.delta":
                    # Safely access delta attribute
                    audio_chunk = getattr(event, "delta", None)
                    if not audio_chunk:
                        logger.warning(
                            "[REALTIME] Audio delta event missing delta attribute"
                        )
                        continue

                    # Invoke callback if registered
                    if self._on_audio_delta:
                        try:
                            self._on_audio_delta(audio_chunk)
                        except Exception as e:
                            logger.error(
                                "[REALTIME] Error in audio delta callback",
                                extra={"error": str(e)},
                            )

                    # Yield for async generator consumers
                    logger.debug(
                        "[REALTIME] Yielding audio delta",
                        extra={
                            "delta_length": len(audio_chunk),
                            "has_delta": bool(audio_chunk),
                        },
                    )
                    yield audio_chunk

                # Transcript events
                elif (
                    event_type
                    == "conversation.item.input_audio_transcription.completed"
                ):
                    transcript_text = getattr(event, "transcript", "")
                    item_id = getattr(event, "item_id", "")

                    # Always log user transcripts for debugging
                    logger.info(
                        "[REALTIME] User transcript",
                        extra={
                            "transcript": transcript_text,
                            "item_id": item_id,
                        },
                    )

                    if self._on_audio_transcript:
                        try:
                            transcript_data = {
                                "role": "user",
                                "transcript": transcript_text,
                                "item_id": item_id,
                            }
                            self._on_audio_transcript(transcript_data)
                        except Exception as e:
                            logger.error(
                                "[REALTIME] Error in transcript callback",
                                extra={"error": str(e)},
                            )

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

                    if self._on_error:
                        try:
                            self._on_error(error_data)
                        except Exception as e:
                            logger.error(
                                "[REALTIME] Error in error callback",
                                extra={"error": str(e)},
                            )

                    logger.error("[REALTIME] API error", extra=error_data)

                # Other events (log for debugging)
                else:
                    logger.debug(
                        f"[REALTIME] Other event: {event_type}",
                        extra={"event_data": str(event)[:200]},
                    )

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
    # Optional callbacks
    on_audio_delta: Optional[Callable[[str], None]] = None,
    on_audio_transcript: Optional[Callable[[dict], None]] = None,
    on_function_call: Optional[Callable[[str, dict], dict]] = None,
    on_error: Optional[Callable[[dict], None]] = None,
) -> RealtimeSession:
    """
    Create and connect RealtimeSession for voice conversations.

    Looks up project by voice channel identifier, retrieves agent configuration,
    establishes OpenAI Realtime API connection, and optionally registers callbacks.

    Args:
        session: Database session for lookups
        recipient_id: Phone number or identifier (e.g., "+15551234567")
        on_audio_delta: Optional callback for audio chunks
        on_audio_transcript: Optional callback for transcript events
        on_function_call: Optional callback for function calls
        on_error: Optional callback for error events

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

    logger.debug(f"[REALTIME] fetched system prompt: {system_prompt}")
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

    # Create session with callbacks
    realtime_session = RealtimeSession(
        api_key=api_key,
        config=config,
        on_audio_delta=on_audio_delta,
        on_audio_transcript=on_audio_transcript,
        on_function_call=on_function_call,
        on_error=on_error,
    )

    await realtime_session.connect()

    logger.info(
        "[REALTIME] Created realtime session",
        extra={
            "project_name": project.name,
            "agent_id": str(agent.id),
            "has_callbacks": bool(
                on_audio_delta or on_audio_transcript or on_function_call or on_error
            ),
        },
    )

    return realtime_session
