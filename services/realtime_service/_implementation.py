"""
OpenAI Realtime Voice service implementation.

Provides RealtimeSession class for managing OpenAI Realtime API connections
and factory function for creating sessions with proper configuration.
"""

import os
import uuid
from typing import AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.tables import Project
from db.tables.types import Channel
from services.agent_service._raw_config import RawConfig
from utils.log import logger


class RealtimeSession:
    """
    Manages OpenAI Realtime API connection for voice conversations.

    Handles bidirectional audio streaming between Twilio and OpenAI's
    Realtime API using WebSocket connections managed by AsyncOpenAI SDK.
    """

    def __init__(self, api_key: str, system_prompt: str):
        """
        Initialize RealtimeSession.

        Args:
            api_key: OpenAI API key for authentication
            system_prompt: System instructions for the AI assistant
        """
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.client: AsyncOpenAI | None = None
        self.connection = None

    async def connect(self) -> None:
        """
        Establish connection to OpenAI Realtime API and configure session.

        Configures audio format (g711_ulaw 8kHz) for Twilio compatibility
        and sets up server-side Voice Activity Detection (VAD).

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

            # Configure session with nested audio configuration
            session_config = {
                "type": "realtime",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcmu"},
                        "turn_detection": {"type": "server_vad"},
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": "alloy",
                    },
                },
                "instructions": self.system_prompt,
                "output_modalities": ["audio"],
                "model": "gpt-realtime",
            }
            logger.debug(
                "[REALTIME] Sending session configuration",
                extra={
                    "audio_format": "audio/pcmu",
                    "voice": "alloy",
                    "instructions_length": len(self.system_prompt),
                },
            )
            await self.connection.session.update(session=session_config)  # type: ignore[arg-type]

            logger.debug(
                "[REALTIME] Successfully connected and configured OpenAI Realtime API",
                extra={"model": "gpt-realtime"},
            )

        except Exception as e:
            logger.error(
                "[REALTIME] Failed to connect to OpenAI Realtime API",
                extra={"error": str(e), "error_type": type(e).__name__},
                exc_info=True,
            )

            # Clean up partial resources before re-raising
            # Close connection if it was established
            if self.connection is not None:
                try:
                    await self.connection.close()
                except Exception as close_error:
                    logger.error(
                        "[REALTIME] Error closing connection during cleanup",
                        extra={"error": str(close_error)},
                    )

            # Close AsyncOpenAI client if it was created
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
            base64_audio: Base64-encoded audio data in audio/pcmu format

        Raises:
            RuntimeError: If connection is not established
            Exception: If sending audio fails
        """
        if not self.connection:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            await self.connection.input_audio_buffer.append(audio=base64_audio)
            logger.debug(
                "[REALTIME] Sent audio chunk to OpenAI input buffer",
                extra={"payload_length": len(base64_audio)},
            )
        except Exception as e:
            logger.error(
                "[REALTIME] Error sending audio to OpenAI",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise

    async def receive_audio_stream(self) -> AsyncIterator[str]:
        """
        Async generator yielding audio chunks from OpenAI.

        Listens for response.output_audio.delta events and yields base64-encoded
        audio chunks for playback through Twilio.

        Yields:
            str: Base64-encoded audio data in audio/pcmu format

        Raises:
            RuntimeError: If connection is not established
        """
        if not self.connection:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            logger.debug("[REALTIME] Starting to listen for OpenAI events")
            async for event in self.connection:
                # Log all events for debugging
                logger.debug(
                    "[REALTIME] Received event from OpenAI",
                    extra={
                        "event_type": event.type,
                        "event_id": getattr(event, "event_id", None),
                    },
                )

                if event.type == "response.output_audio.delta":
                    # Yield audio chunk for playback
                    logger.debug(
                        "[REALTIME] Yielding audio delta",
                        extra={
                            "delta_length": len(event.delta),
                            "delta_preview": event.delta[:50] if event.delta else "",
                            "has_delta": bool(event.delta),
                        },
                    )
                    yield event.delta
                elif event.type == "response.output_audio.done":
                    # Audio response complete
                    logger.debug("[REALTIME] Audio response completed")
                elif event.type == "error":
                    # Handle API errors
                    logger.error(
                        "[REALTIME] OpenAI API error",
                        extra={
                            "error": (
                                event.error if hasattr(event, "error") else str(event)
                            )
                        },
                    )
                else:
                    # Log other events for visibility
                    logger.debug(
                        f"[REALTIME] Other event: {event.type}",
                        extra={"event_data": str(event)[:200]},
                    )
        except Exception as e:
            logger.error(
                "[REALTIME] Error receiving audio from OpenAI",
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
    session: AsyncSession, recipient_id: str
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
        ValueError: If project not found for recipient_id
        Exception: If connection to OpenAI fails
    """
    # Build channel identifier (e.g., "voice:+15551234567")
    channel_identifier = f"voice:{recipient_id}"

    # Look up project by channel identifier with eager loading of relationships
    # Using direct query to ensure agent and account are loaded before session closes
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
    # This includes brand info, store info, and feature flag checks
    system_prompt = await raw_config._build_agent_prompt(Channel.VOICE, session)

    if not system_prompt:
        raise ValueError(f"Agent prompt is empty for agent: {agent.id}")

    # Get OpenAI API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    # Create and connect session
    realtime_session = RealtimeSession(api_key=api_key, system_prompt=system_prompt)
    await realtime_session.connect()

    logger.info(
        "[REALTIME] Created realtime session",
        extra={
            "project_name": project.name,
            "agent_id": str(agent.id),
        },
    )

    return realtime_session
