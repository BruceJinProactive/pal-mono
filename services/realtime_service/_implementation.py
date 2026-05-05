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
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from agno.tools.function import Function

    from agent.tool import ToolConfig

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.tables import Project, ProjectIntegration
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
        on_tool_call: Callable[[str, str], Awaitable[str]] | None = None,
    ):
        self.api_key = api_key
        self.config = config
        self.client: AsyncOpenAI | None = None
        self.connection = None
        self.on_interruption = on_interruption
        self.on_tool_call = on_tool_call
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

    async def _send_filler_response(self) -> None:
        """Send an out-of-band filler response to fill silence during tool execution.

        Uses conversation="none" so it doesn't block the default conversation
        and doesn't need to be cancelled before the real response.
        """
        if not self.connection:
            return
        try:
            await self.connection.response.create(
                response={
                    "conversation": "none",
                    "instructions": (
                        "Say a very brief natural acknowledgment to fill silence "
                        "while looking something up. Examples: 'One moment...', "
                        "'Let me check that...', 'Sure, looking into it...'. "
                        "Keep it under 5 words. Do NOT answer the question yet."
                    ),
                    "max_output_tokens": 50,
                }
            )
            logger.info("[REALTIME] Filler response triggered (out-of-band)")
        except Exception as e:
            logger.warning(
                "[REALTIME] Failed to send filler response",
                extra={"error": str(e)},
            )

    async def _handle_tool_call(self, event: object) -> None:
        call_id = getattr(event, "call_id", "")
        name = getattr(event, "name", "")
        arguments = self._filter_tool_args(name, getattr(event, "arguments", "{}"))

        start = time.monotonic()

        logger.info(
            f"[REALTIME.{name}] Tool call received",
            extra={"call_id": call_id, "tool_name": name},
        )

        # Send filler audio while tool executes (out-of-band, won't block real response)
        await self._send_filler_response()

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


def _build_demo_tools() -> tuple[list[dict], dict[str, Callable[..., str]]]:
    """Build demo tools for live testing. No credentials required."""
    import json as _json

    def get_store_hours() -> str:
        return _json.dumps(
            {
                "monday": "10:00 AM - 9:00 PM",
                "tuesday": "10:00 AM - 9:00 PM",
                "wednesday": "10:00 AM - 9:00 PM",
                "thursday": "10:00 AM - 9:00 PM",
                "friday": "10:00 AM - 10:00 PM",
                "saturday": "11:00 AM - 10:00 PM",
                "sunday": "11:00 AM - 8:00 PM",
            }
        )

    def get_daily_specials() -> str:
        return _json.dumps(
            {
                "appetizer": "Bruschetta - $8.99",
                "entree": "Grilled Salmon with lemon butter sauce - $18.99",
                "dessert": "Tiramisu - $7.99",
                "drink": "House Red Wine - $6.99",
            }
        )

    tools = [
        {
            "type": "function",
            "name": "get_store_hours",
            "description": "Get the store's opening and closing hours for each day of the week.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "type": "function",
            "name": "get_daily_specials",
            "description": "Get today's daily specials including appetizer, entree, dessert, and drink.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]

    executors: dict[str, Callable[..., str]] = {
        "get_store_hours": get_store_hours,
        "get_daily_specials": get_daily_specials,
    }

    return tools, executors


def _build_realtime_tools(
    tool_config: "ToolConfig",
) -> tuple[list[dict], dict[str, "Function"]]:
    from tools.registry import tool_registry

    tools: list[dict] = []
    executors: dict[str, "Function"] = {}

    for identifier in tool_config.identifiers:
        try:
            toolkit = tool_registry.get_tool(identifier, tool_config.metadata)
        except Exception as e:
            logger.error(
                f"[REALTIME] Failed to instantiate tool: {identifier.tool_name}",
                extra={"error": str(e)},
                exc_info=True,
            )
            continue
        if not toolkit:
            logger.warning(
                f"[REALTIME] Tool not found in registry: {identifier.tool_name}"
            )
            continue

        for func_name, func in toolkit.functions.items():
            if not func.entrypoint:
                logger.warning(
                    "[REALTIME] Skipping tool without entrypoint: %s", func_name
                )
                continue
            func.process_entrypoint()
            tools.append(
                {
                    "type": "function",
                    "name": func_name,
                    "description": func.description or "",
                    "parameters": func.parameters,
                }
            )
            executors[func_name] = func

    logger.info(
        "[REALTIME] Loaded %d tool function(s): %s",
        len(tools),
        [t["name"] for t in tools],
    )
    return tools, executors


def _make_tool_executor(
    executors: dict,
) -> Callable[[str, str], Awaitable[str]]:
    import inspect

    async def execute_tool(name: str, arguments: str) -> str:
        executor = executors.get(name)
        if not executor:
            return json.dumps({"error": f"Unknown tool: {name}"})
        args = json.loads(arguments) if arguments else {}
        if inspect.iscoroutinefunction(executor):
            result = await executor(**args)
        else:
            result = await asyncio.to_thread(executor, **args)
        return json.dumps(result) if not isinstance(result, str) else result

    return execute_tool


async def create_realtime_session(
    session: AsyncSession,
    recipient_id: str,
    caller_id: str | None = None,
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
        user_id=uuid.uuid4(),  # No user context for voice calls
        conversation_id=uuid.uuid4(),  # Generate new conversation ID
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

    # Load tools for this agent
    tool_config = await raw_config._get_agent_tools(session)
    logger.info(
        "[REALTIME] Agent tool config: %d identifier(s): %s",
        len(tool_config.identifiers),
        [t.tool_name for t in tool_config.identifiers],
    )
    tools, tool_executors = _build_realtime_tools(tool_config)

    # Add demo tools (no credentials required)
    demo_tools, demo_executors = _build_demo_tools()
    tools.extend(demo_tools)

    logger.info(
        "[REALTIME] Total tools registered: %d (%s)",
        len(tools),
        [t["name"] for t in tools],
    )

    # Append tool usage instructions to system prompt
    # Build RealtimeConfig from agent settings
    config = RealtimeConfig(
        system_prompt=system_prompt,
        voice_id="alloy",  # TODO: Get from voice_config
        tools=tools,
    )

    # Get OpenAI API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    all_executors = {**demo_executors}

    # Merge Agno tool executors (entrypoint-based)
    for func_name, func in tool_executors.items():
        if func.entrypoint:
            all_executors[func_name] = func.entrypoint

    # Create session
    realtime_session = RealtimeSession(
        api_key=api_key,
        config=config,
        on_tool_call=(_make_tool_executor(all_executors) if all_executors else None),
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
