"""
OpenAI Realtime Voice service implementation.

Provides RealtimeSession class for managing OpenAI Realtime API connections
with callback support and factory function for creating sessions.
"""

import asyncio
import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import db
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    Message,
    Metadata,
    TextObject,
    Type,
)
from db.session import AsyncSessionLocal
from db.tables import Project, ProjectIntegration, VoiceConfig
from db.tables.types import Channel, SpeechRate
from services import message_service, user_service
from services.agent_service._raw_config import RawConfig
from utils.log import logger

from ._audio_mixer import BackgroundAudioMixer
from ._config import RealtimeConfig
from ._tool_handler import (
    build_agno_tools,
    build_pal_agent_provider_tools,
    make_tool_executor,
)

_ASSETS_DIR = Path(__file__).parent / "assets"

_SPEECH_RATE_TO_SPEED: dict[SpeechRate, float] = {
    SpeechRate.slowest: 0.6,
    SpeechRate.slower: 0.8,
    SpeechRate.normal: 1.0,
    SpeechRate.faster: 1.25,
    SpeechRate.fastest: 1.5,
}


def _append_realtime_call_context(system_prompt: str, caller_id: str | None) -> str:
    """Append caller metadata that is known outside the realtime transcript."""
    if not caller_id:
        return system_prompt

    return (
        f"{system_prompt}\n\n"
        "# Realtime Call Context\n"
        f"- Customer Phone: {caller_id}\n"
        "- The customer phone comes from the active realtime call context.\n"
        "- Do not ask the customer for their phone number when this value is present.\n"
        "- For tools that require digits-only US phone numbers, strip a leading +1 "
        "before passing the phone."
    )


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
        on_tool_call: Callable[[str, str], Awaitable[str]] | None = None,
        on_transcript: Callable[[str, str], Awaitable[None]] | None = None,
        user_id: uuid.UUID | None = None,
        call_id: str | None = None,
        project_id: uuid.UUID | None = None,
        mixer: "BackgroundAudioMixer | None" = None,
    ):
        self.api_key = api_key
        self.config = config
        self.client: AsyncOpenAI | None = None
        self.connection = None
        self.on_interruption = on_interruption
        self.on_tool_call = on_tool_call
        self.on_transcript = on_transcript
        self.user_id = user_id
        self.call_id = call_id
        self.project_id = project_id
        self.mixer = mixer

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

    async def send_first_message(self, text: str) -> None:
        """
        Trigger the model to speak a greeting by calling response.create
        with per-response instructions.

        Args:
            text: The greeting text the model should speak
        """
        if not self.connection:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            await asyncio.wait_for(
                self.connection.response.create(
                    response={"instructions": f"Say exactly: {text}"}
                ),
                timeout=5.0,
            )
            logger.info(
                "[REALTIME] First message triggered",
                extra={"text": text},
            )
        except asyncio.TimeoutError:
            logger.warning("[REALTIME] First message timed out")
        except Exception as e:
            logger.error(
                "[REALTIME] Failed to trigger first message",
                extra={"error": str(e)},
                exc_info=True,
            )

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

    async def _handle_interruption(self) -> None:
        """Flush Twilio playback buffer immediately on speech_started."""
        if not self.on_interruption:
            return
        try:
            await asyncio.wait_for(self.on_interruption(), timeout=0.5)
            logger.info("[REALTIME] Twilio clear sent")
        except asyncio.TimeoutError:
            logger.warning("[REALTIME] Interruption callback timed out")
        except Exception as cb_err:
            logger.error(
                "[REALTIME] Interruption callback failed",
                extra={"error": str(cb_err)},
                exc_info=True,
            )

    async def _dispatch_transcript(self, role: str, text: str) -> None:
        """Fire-and-forget transcript persistence. Does not block the stream loop."""
        if not self.on_transcript:
            return
        try:
            await self.on_transcript(role, text)
        except Exception as e:
            logger.error(
                "[REALTIME] on_transcript callback failed",
                extra={"role": role, "error": str(e)},
            )

    def _filter_tool_args(self, name: str, arguments: str) -> str:
        for t in self.config.tools:
            if t.get("name") == name:
                allowed = set(t.get("parameters", {}).get("properties", {}).keys())
                args = json.loads(arguments) if arguments else {}
                filtered = {k: v for k, v in args.items() if k in allowed}
                removed = set(args.keys()) - set(filtered.keys())
                if removed:
                    logger.info(
                        f"[REALTIME.{name}] Filtered out args: {removed}",
                        extra={"allowed": list(allowed), "removed": list(removed)},
                    )
                return json.dumps(filtered)
        return arguments

    async def _handle_tool_call(self, event: object) -> None:
        call_id = getattr(event, "call_id", "")
        name = getattr(event, "name", "")
        arguments = self._filter_tool_args(name, getattr(event, "arguments", "{}"))

        start = time.monotonic()

        logger.info(
            f"[REALTIME.{name}] Tool call received",
            extra={"call_id": call_id, "tool_name": name},
        )

        if not self.on_tool_call:
            logger.warning(f"[REALTIME.{name}] No handler configured")
            result = '{"error": "Tool execution not available"}'
        else:
            try:
                result = await asyncio.wait_for(
                    self.on_tool_call(name, arguments), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error(f"[REALTIME.{name}] Tool call timed out")
                result = '{"error": "Tool execution timed out"}'
            except Exception as e:
                logger.error(
                    f"[REALTIME.{name}] Tool call failed",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                result = f'{{"error": "{str(e)}"}}'

        exec_ms = (time.monotonic() - start) * 1000

        if not self.connection:
            return

        try:
            await self.connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                }
            )
            await self.connection.response.create()
            total_ms = (time.monotonic() - start) * 1000
            logger.info(
                f"[REALTIME.{name}] Tool result sent, response triggered",
                extra={
                    "call_id": call_id,
                    "exec_ms": round(exec_ms, 1),
                    "total_ms": round(total_ms, 1),
                },
            )
        except Exception as e:
            logger.error(
                f"[REALTIME.{name}] Failed to send tool result",
                extra={"call_id": call_id, "error": str(e)},
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

                    logger.info(
                        "[REALTIME] User transcript",
                        extra={
                            "transcript": transcript_text,
                            "item_id": item_id,
                        },
                    )

                    if self.on_transcript and transcript_text:
                        asyncio.create_task(
                            self._dispatch_transcript("user", transcript_text)
                        )

                # User started speaking — flush Twilio buffer immediately
                elif event_type == "input_audio_buffer.speech_started":
                    logger.info("[REALTIME] Speech started, flushing Twilio buffer")
                    await self._handle_interruption()

                elif event_type == "input_audio_buffer.speech_stopped":
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

                    if self.on_transcript and transcript:
                        asyncio.create_task(
                            self._dispatch_transcript("assistant", transcript)
                        )

                # Tool call completed — execute and send result
                elif event_type == "response.function_call_arguments.done":
                    await self._handle_tool_call(event)

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
    caller_id: str | None = None,
    call_id: str | None = None,
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

    # --- Resolve user + create conversation (same pattern as init_voice_call) ---
    user_id: uuid.UUID
    conversation_id = uuid.uuid4()

    if call_id and caller_id:
        message = Message(
            id=str(uuid.uuid4()),
            author_type=AuthorType.SYSTEM,
            sender_identifier=caller_id,
            recipient_identifier=recipient_id,
            channel=Channel.VOICE,
            broker=None,
            type=Type.TEXT,
            text=TextObject(body="[Call initiated]"),
            context="",
            extras=Extras(),
            metadata=Metadata(),
            timestamp=datetime.now(timezone.utc),
        )

        user, _ = await user_service.get_user_async(session, project, message)
        if not user:
            user = await user_service.create_user_async(session, project, message)
            await session.refresh(user, attribute_names=["id"])
            await session.refresh(project, attribute_names=["id"])

        user_id = user.id

        voice_message = await message_service.create_voice_call_conversation(
            session,
            user_id=user_id,
            project_id=project.id,
            message_body=message.to_dict(),
            call_id=call_id,
        )
        conversation_id = voice_message.conversation_id

        await session.refresh(project, attribute_names=["id", "account", "agent"])

        logger.info(
            "[REALTIME] User resolved and conversation created",
            extra={
                "user_id": str(user_id),
                "call_id": call_id,
                "conversation_id": str(conversation_id),
            },
        )
    else:
        user_id = uuid.uuid4()

    # Load project integrations for tool resolution
    pi_result = await session.execute(
        select(ProjectIntegration).filter(ProjectIntegration.project_id == project.id)
    )
    project_integrations = list(pi_result.scalars())

    logger.info(
        "[REALTIME] Project integrations: %d found for project %s (%s)",
        len(project_integrations),
        project.name,
        [pi.tool_name for pi in project_integrations],
    )

    # Build agent configuration using existing pattern
    raw_config = RawConfig(
        agent=agent,
        project=project,
        account=account,
        user_id=user_id,
        conversation_id=conversation_id,
        channel=Channel.VOICE,
        integration=None,
        sender_identifier=caller_id,
        receiver_identifier=recipient_id,
        project_integrations=project_integrations,
        faqs=[],
    )

    # Build agent prompt using the same method as other channels
    system_prompt = await raw_config._build_agent_prompt(Channel.VOICE, session)

    if not system_prompt:
        raise ValueError(f"Agent prompt is empty for agent: {agent.id}")

    system_prompt = _append_realtime_call_context(system_prompt, caller_id)

    # Load tools for this agent
    tool_config = await raw_config._get_agent_tools(session)
    logger.info(
        "[REALTIME] Agent tool config: %d identifier(s): %s",
        len(tool_config.identifiers),
        [t.tool_name for t in tool_config.identifiers],
    )
    tools, tool_executors = build_agno_tools(tool_config)

    # Add pal-agents provider tools (toast_v3, adora_v3) in dry-run mode
    pa_tools, pa_executors = await build_pal_agent_provider_tools(
        session=session,
        project_id=project.id,
        caller_id=caller_id,
        user_id=user_id,
        conversation_id=conversation_id,
        project_timezone=project.timezone,
    )
    tools.extend(pa_tools)

    logger.info(
        "[REALTIME] Total tools registered: %d (%s)",
        len(tools),
        [t["name"] for t in tools],
    )

    # Append tool-call preamble instruction.
    system_prompt += (
        "\n\n# Tools\n"
        "- Before any tool call, you MUST say one short preamble like "
        '"I\'m checking that now.", "Let me look that up.", '
        '"One moment.", "Sure, let me check.", or '
        '"I can check that for you." Then call the tool immediately. '
        "Do not silently call tools without a spoken preamble."
    )

    # Load voice configuration for this project
    vc_result = await session.execute(
        select(VoiceConfig).filter(VoiceConfig.project_id == project.id)
    )
    voice_config = vc_result.scalars().first()

    _VALID_OPENAI_VOICES = {
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "sage",
        "shimmer",
        "verse",
    }

    voice_id = "alloy"
    speed = 1.0
    if voice_config:
        raw_voice = (voice_config.raw_config or {}).get("openai_voice")
        if isinstance(raw_voice, str) and raw_voice in _VALID_OPENAI_VOICES:
            voice_id = raw_voice
        speed = _SPEECH_RATE_TO_SPEED.get(voice_config.speech_rate, 1.0)

    logger.info(
        "[REALTIME] Voice config: voice=%s, speed=%s",
        voice_id,
        speed,
    )

    # Build RealtimeConfig from agent settings
    config = RealtimeConfig(
        system_prompt=system_prompt,
        voice_id=voice_id,
        speed=speed,
        tools=tools,
    )

    # Get OpenAI API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    all_executors = {**pa_executors}

    # Merge Agno tool executors (entrypoint-based)
    for func_name, func in tool_executors.items():
        if func.entrypoint:
            all_executors[func_name] = func.entrypoint

    # Build transcript persistence callback
    on_transcript = None
    if call_id and caller_id:
        _tx_user_id = user_id
        _tx_call_id = call_id

        async def _persist_transcript(role: str, text: str) -> None:
            try:
                async with AsyncSessionLocal() as tx_session:
                    message_repo = db.MessageRepositoryAsync(tx_session)
                    await message_repo.add_message_to_voice_conversation(
                        user_id=_tx_user_id,
                        message_body={"role": role, "content": text},
                        call_id=_tx_call_id,
                    )
            except Exception as e:
                logger.error(
                    "[REALTIME] Failed to persist transcript",
                    extra={"role": role, "error": str(e)},
                )

        on_transcript = _persist_transcript

    # Load background audio mixer
    mixer: BackgroundAudioMixer | None = None
    background_sound = voice_config.background_sound if voice_config else None
    if background_sound and all(c.isalnum() or c == "-" for c in background_sound):
        asset_path = _ASSETS_DIR / f"{background_sound}.ulaw"
        try:
            if asset_path.exists():
                mixer = BackgroundAudioMixer(asset_path.read_bytes(), volume=0.8)
                logger.info(
                    "[REALTIME] Background audio mixer loaded: %s", background_sound
                )
            else:
                logger.warning(
                    "[REALTIME] Background audio asset not found: %s", asset_path
                )
        except OSError as e:
            logger.warning("[REALTIME] Failed to read background audio asset: %s", e)

    # Create session
    realtime_session = RealtimeSession(
        api_key=api_key,
        config=config,
        on_tool_call=(make_tool_executor(all_executors) if all_executors else None),
        on_transcript=on_transcript,
        user_id=user_id,
        call_id=call_id,
        project_id=project.id,
        mixer=mixer,
    )

    await realtime_session.connect()

    # Trigger first message / greeting
    first_message = (
        voice_config.first_message.strip()
        if voice_config and voice_config.first_message
        else ""
    )
    if not first_message:
        first_message = "Hi, how can I help you?"
    await realtime_session.send_first_message(first_message)

    logger.info(
        "[REALTIME] Created realtime session",
        extra={
            "project_name": project.name,
            "agent_id": str(agent.id),
            "first_message": first_message,
        },
    )

    return realtime_session
