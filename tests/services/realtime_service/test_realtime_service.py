# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for OpenAI Realtime Voice service implementation.

Tests cover:
- RealtimeSession initialization, connection, audio streaming, and cleanup
- create_realtime_session factory function with database lookups
- Error handling and resource cleanup
- Logging and counter functionality
"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.realtime_service._config import RealtimeConfig
from services.realtime_service._implementation import (
    RealtimeSession,
    _build_demo_tools,
    create_realtime_session,
)

# ---------------------------------------------------------------------------
# RealtimeConfig Tests
# ---------------------------------------------------------------------------


class TestRealtimeConfigTurnDetection:
    """Test RealtimeConfig._build_turn_detection() and to_session_config()."""

    def test_default_is_semantic_vad_with_low_eagerness(self) -> None:
        config = RealtimeConfig(system_prompt="Test", voice_id="alloy")
        td = config._build_turn_detection()
        assert td["type"] == "semantic_vad"
        assert td["eagerness"] == "low"
        assert td["interrupt_response"] is False
        assert "threshold" not in td
        assert "silence_duration_ms" not in td

    def test_server_vad_includes_threshold_and_timing_params(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            turn_detection_type="server_vad",
        )
        td = config._build_turn_detection()
        assert td["type"] == "server_vad"
        assert td["threshold"] == 0.7
        assert td["silence_duration_ms"] == 500
        assert td["prefix_padding_ms"] == 300
        assert td["interrupt_response"] is False
        assert "eagerness" not in td

    def test_semantic_vad_includes_eagerness(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            turn_detection_type="semantic_vad",
            eagerness="high",
        )
        td = config._build_turn_detection()
        assert td["type"] == "semantic_vad"
        assert td["eagerness"] == "high"
        assert "threshold" not in td
        assert "silence_duration_ms" not in td
        assert "prefix_padding_ms" not in td

    def test_custom_vad_threshold(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            turn_detection_type="server_vad",
            vad_threshold=0.9,
        )
        td = config._build_turn_detection()
        assert td["threshold"] == 0.9

    def test_noise_reduction_far_field_in_session_config(self) -> None:
        config = RealtimeConfig(system_prompt="Test", voice_id="alloy")
        session = config.to_session_config()
        audio_input = session["audio"]["input"]
        assert audio_input["noise_reduction"] == {"type": "far_field"}

    def test_noise_reduction_disabled_omits_key(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test", voice_id="alloy", noise_reduction_type=None
        )
        session = config.to_session_config()
        audio_input = session["audio"]["input"]
        assert "noise_reduction" not in audio_input

    def test_noise_reduction_near_field(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            noise_reduction_type="near_field",
        )
        session = config.to_session_config()
        audio_input = session["audio"]["input"]
        assert audio_input["noise_reduction"] == {"type": "near_field"}

    def test_session_config_uses_build_turn_detection(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            turn_detection_type="server_vad",
            vad_threshold=0.8,
            silence_duration_ms=700,
        )
        session = config.to_session_config()
        td = session["audio"]["input"]["turn_detection"]
        assert td["threshold"] == 0.8
        assert td["silence_duration_ms"] == 700


# ---------------------------------------------------------------------------
# RealtimeSession Tests
# ---------------------------------------------------------------------------


class TestRealtimeSessionInit:
    """Test RealtimeSession initialization."""

    def test_init_sets_attributes(self) -> None:
        """RealtimeSession.__init__ sets api_key, config, and initializes counters."""
        api_key = "test-api-key"
        config = RealtimeConfig(system_prompt="Test prompt", voice_id="alloy")

        session = RealtimeSession(api_key=api_key, config=config)

        assert session.api_key == api_key
        assert session.config == config
        assert session.client is None
        assert session.connection is None
        assert session.audio_chunks_sent_to_openai == 0
        assert session.audio_chunks_received == 0


class TestRealtimeSessionConnect:
    """Test RealtimeSession.connect() method."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """connect() successfully establishes connection and configures session."""
        api_key = "test-api-key"
        config = RealtimeConfig(system_prompt="Test prompt", voice_id="alloy")
        session = RealtimeSession(api_key=api_key, config=config)

        mock_connection = MagicMock()
        mock_connection.session.update = AsyncMock()
        mock_client = MagicMock()
        mock_realtime = MagicMock()
        mock_realtime.connect.return_value.enter = AsyncMock(
            return_value=mock_connection
        )
        mock_client.realtime = mock_realtime

        with patch("services.realtime_service._implementation.AsyncOpenAI") as mock_ai:
            mock_ai.return_value = mock_client
            with patch.dict(os.environ, {"OPENAI_REALTIME_MODEL": "gpt-realtime-1.5"}):
                await session.connect()

        assert session.client == mock_client
        assert session.connection == mock_connection
        mock_realtime.connect.assert_called_once_with(model="gpt-realtime-1.5")
        mock_connection.session.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_uses_default_model(self) -> None:
        """connect() uses default model when env var not set."""
        api_key = "test-api-key"
        config = RealtimeConfig(system_prompt="Test prompt", voice_id="alloy")
        session = RealtimeSession(api_key=api_key, config=config)

        mock_connection = MagicMock()
        mock_connection.session.update = AsyncMock()
        mock_client = MagicMock()
        mock_realtime = MagicMock()
        mock_realtime.connect.return_value.enter = AsyncMock(
            return_value=mock_connection
        )
        mock_client.realtime = mock_realtime

        with patch("services.realtime_service._implementation.AsyncOpenAI") as mock_ai:
            mock_ai.return_value = mock_client
            with patch.dict(os.environ, {}, clear=True):
                await session.connect()

        mock_realtime.connect.assert_called_once_with(model="gpt-realtime-1.5")

    @pytest.mark.asyncio
    async def test_connect_failure_cleans_up_resources(self) -> None:
        """connect() cleans up partial resources when connection fails."""
        api_key = "test-api-key"
        config = RealtimeConfig(system_prompt="Test prompt", voice_id="alloy")
        session = RealtimeSession(api_key=api_key, config=config)

        mock_connection = MagicMock()
        mock_connection.close = AsyncMock()
        mock_connection.session.update = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_realtime = MagicMock()
        mock_realtime.connect.return_value.enter = AsyncMock(
            return_value=mock_connection
        )
        mock_client.realtime = mock_realtime

        with patch("services.realtime_service._implementation.AsyncOpenAI") as mock_ai:
            mock_ai.return_value = mock_client
            with pytest.raises(Exception, match="Connection failed"):
                await session.connect()

        # Verify cleanup was attempted
        mock_connection.close.assert_called_once()
        mock_client.close.assert_called_once()
        # Verify resources were reset
        assert session.connection is None
        assert session.client is None


class TestRealtimeSessionSendAudioChunk:
    """Test RealtimeSession.send_audio_chunk() method."""

    @pytest.mark.asyncio
    async def test_send_audio_chunk_success(self) -> None:
        """send_audio_chunk() successfully sends audio and increments counter."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )
        mock_connection = MagicMock()
        mock_connection.input_audio_buffer.append = AsyncMock()
        session.connection = mock_connection

        audio_data = "base64audiodata"
        await session.send_audio_chunk(audio_data)

        assert session.audio_chunks_sent_to_openai == 1
        mock_connection.input_audio_buffer.append.assert_called_once_with(
            audio=audio_data
        )

    @pytest.mark.asyncio
    async def test_send_audio_chunk_logs_every_100(self, caplog) -> None:
        """send_audio_chunk() logs every 100 chunks."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )
        mock_connection = MagicMock()
        mock_connection.input_audio_buffer.append = AsyncMock()
        session.connection = mock_connection

        # Send 99 chunks - should not log
        for _ in range(99):
            await session.send_audio_chunk("audio")

        assert "[REALTIME] Audio chunks sent to OpenAI" not in caplog.text

        # Send 100th chunk - should log
        await session.send_audio_chunk("audio")
        assert session.audio_chunks_sent_to_openai == 100

    @pytest.mark.asyncio
    async def test_send_audio_chunk_without_connection_raises_error(self) -> None:
        """send_audio_chunk() raises RuntimeError if connection not established."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        with pytest.raises(RuntimeError, match="Connection not established"):
            await session.send_audio_chunk("audio")

    @pytest.mark.asyncio
    async def test_send_audio_chunk_error_propagates(self) -> None:
        """send_audio_chunk() propagates errors from connection."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )
        mock_connection = MagicMock()
        mock_connection.input_audio_buffer.append = AsyncMock(
            side_effect=Exception("Send failed")
        )
        session.connection = mock_connection

        with pytest.raises(Exception, match="Send failed"):
            await session.send_audio_chunk("audio")


class TestRealtimeSessionReceiveAudioStream:
    """Test RealtimeSession.receive_audio_stream() method."""

    @pytest.mark.asyncio
    async def test_receive_audio_stream_yields_audio_deltas(self) -> None:
        """receive_audio_stream() yields audio chunks from response.output_audio.delta events."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        # Mock events
        audio_event_1 = MagicMock()
        audio_event_1.type = "response.output_audio.delta"
        audio_event_1.delta = "audio_chunk_1"

        audio_event_2 = MagicMock()
        audio_event_2.type = "response.output_audio.delta"
        audio_event_2.delta = "audio_chunk_2"

        async def mock_event_stream():
            yield audio_event_1
            yield audio_event_2

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        assert chunks == ["audio_chunk_1", "audio_chunk_2"]
        assert session.audio_chunks_received == 2

    @pytest.mark.asyncio
    async def test_receive_audio_stream_logs_every_100_chunks(self) -> None:
        """receive_audio_stream() logs every 100 audio chunks received."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        async def mock_event_stream():
            for i in range(101):
                event = MagicMock()
                event.type = "response.output_audio.delta"
                event.delta = f"chunk_{i}"
                yield event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        count = 0
        async for _ in session.receive_audio_stream():
            count += 1

        assert count == 101
        assert session.audio_chunks_received == 101

    @pytest.mark.asyncio
    async def test_receive_audio_stream_handles_missing_delta(self) -> None:
        """receive_audio_stream() skips events with missing delta attribute."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        audio_event = MagicMock()
        audio_event.type = "response.output_audio.delta"
        # Explicitly set delta to None to simulate missing attribute
        # (MagicMock would otherwise auto-create a MagicMock for delta)
        audio_event.delta = None

        async def mock_event_stream():
            yield audio_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        assert chunks == []

    @pytest.mark.asyncio
    async def test_receive_audio_stream_handles_transcript_events(self) -> None:
        """receive_audio_stream() processes transcript events without yielding."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        transcript_event = MagicMock()
        transcript_event.type = "conversation.item.input_audio_transcription.completed"
        transcript_event.transcript = "User said hello"
        transcript_event.item_id = "item-123"

        audio_event = MagicMock()
        audio_event.type = "response.output_audio.delta"
        audio_event.delta = "audio_chunk"

        async def mock_event_stream():
            yield transcript_event
            yield audio_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        # Only audio chunk should be yielded
        assert chunks == ["audio_chunk"]

    @pytest.mark.asyncio
    async def test_interruption_fires_after_delay(self) -> None:
        """on_interruption fires after interruption_delay_ms if speech persists."""
        on_interruption = AsyncMock()
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=50,
            ),
            on_interruption=on_interruption,
        )

        speech_started_event = MagicMock()
        speech_started_event.type = "input_audio_buffer.speech_started"

        audio_event = MagicMock()
        audio_event.type = "response.output_audio.delta"
        audio_event.delta = "audio_chunk"

        async def mock_event_stream():
            yield speech_started_event
            yield audio_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        # Wait for the delayed task to complete
        await asyncio.sleep(0.1)

        on_interruption.assert_awaited_once()
        assert chunks == ["audio_chunk"]

    @pytest.mark.asyncio
    async def test_interruption_cancelled_by_quick_speech_stop(self) -> None:
        """on_interruption does NOT fire if speech_stopped arrives before delay."""
        on_interruption = AsyncMock()
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=200,
            ),
            on_interruption=on_interruption,
        )

        speech_started_event = MagicMock()
        speech_started_event.type = "input_audio_buffer.speech_started"

        speech_stopped_event = MagicMock()
        speech_stopped_event.type = "input_audio_buffer.speech_stopped"

        async def mock_event_stream():
            yield speech_started_event
            yield speech_stopped_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        await asyncio.sleep(0.3)

        on_interruption.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_interruption_skipped_when_no_callback(self) -> None:
        """speech_started without callback does not error."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        speech_started_event = MagicMock()
        speech_started_event.type = "input_audio_buffer.speech_started"

        async def mock_event_stream():
            yield speech_started_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        assert chunks == []

    @pytest.mark.asyncio
    async def test_delayed_interruption_handles_timeout(self) -> None:
        """_delayed_interruption logs warning when callback times out."""
        on_interruption = AsyncMock(side_effect=asyncio.TimeoutError)
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=10,
            ),
            on_interruption=on_interruption,
        )

        with patch(
            "services.realtime_service._implementation.asyncio.wait_for"
        ) as mock_wf:
            mock_wf.side_effect = asyncio.TimeoutError
            await session._delayed_interruption()

    @pytest.mark.asyncio
    async def test_delayed_interruption_handles_callback_exception(self) -> None:
        """_delayed_interruption logs error when callback raises."""
        on_interruption = AsyncMock(side_effect=RuntimeError("boom"))
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=10,
            ),
            on_interruption=on_interruption,
        )

        with patch(
            "services.realtime_service._implementation.asyncio.wait_for"
        ) as mock_wf:
            mock_wf.side_effect = RuntimeError("boom")
            await session._delayed_interruption()

    @pytest.mark.asyncio
    async def test_delayed_interruption_returns_on_cancel(self) -> None:
        """_delayed_interruption returns early when cancelled during sleep."""
        on_interruption = AsyncMock()
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=5000,
            ),
            on_interruption=on_interruption,
        )

        task = asyncio.create_task(session._delayed_interruption())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        on_interruption.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delayed_interruption_skips_when_no_callback(self) -> None:
        """_delayed_interruption returns early if on_interruption is None."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=10,
            ),
        )
        await session._delayed_interruption()

    @pytest.mark.asyncio
    async def test_speech_stopped_without_pending_interruption(self) -> None:
        """speech_stopped logs normally when no pending interruption exists."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        speech_stopped_event = MagicMock()
        speech_stopped_event.type = "input_audio_buffer.speech_stopped"

        async def mock_event_stream():
            yield speech_stopped_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        async for _ in session.receive_audio_stream():
            pass

    @pytest.mark.asyncio
    async def test_receive_audio_stream_handles_error_events(self) -> None:
        """receive_audio_stream() logs error events without raising."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        error_event = MagicMock()
        error_event.type = "error"
        error_event.error = "API error occurred"

        audio_event = MagicMock()
        audio_event.type = "response.output_audio.delta"
        audio_event.delta = "audio_chunk"

        async def mock_event_stream():
            yield error_event
            yield audio_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        session.connection = mock_connection

        chunks = []
        async for chunk in session.receive_audio_stream():
            chunks.append(chunk)

        # Stream should continue after error event
        assert chunks == ["audio_chunk"]

    @pytest.mark.asyncio
    async def test_receive_audio_stream_without_connection_raises_error(self) -> None:
        """receive_audio_stream() raises RuntimeError if connection not established."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        with pytest.raises(RuntimeError, match="Connection not established"):
            async for _ in session.receive_audio_stream():
                pass


class TestRealtimeSessionClose:
    """Test RealtimeSession.close() method."""

    @pytest.mark.asyncio
    async def test_close_cleans_up_connection_and_client(self) -> None:
        """close() closes both connection and client."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        mock_connection = MagicMock()
        mock_connection.close = AsyncMock()
        mock_client = MagicMock()
        mock_client.close = AsyncMock()

        session.connection = mock_connection
        session.client = mock_client

        await session.close()

        mock_connection.close.assert_called_once()
        mock_client.close.assert_called_once()
        assert session.connection is None
        assert session.client is None

    @pytest.mark.asyncio
    async def test_close_handles_connection_close_error(self) -> None:
        """close() handles errors when closing connection gracefully."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        mock_connection = MagicMock()
        mock_connection.close = AsyncMock(side_effect=Exception("Close failed"))
        mock_client = MagicMock()
        mock_client.close = AsyncMock()

        session.connection = mock_connection
        session.client = mock_client

        # Should not raise exception
        await session.close()

        # Client should still be closed
        mock_client.close.assert_called_once()
        assert session.connection is None
        assert session.client is None

    @pytest.mark.asyncio
    async def test_close_with_no_resources(self) -> None:
        """close() handles case where no resources exist."""
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        # Should not raise exception
        await session.close()

        assert session.connection is None
        assert session.client is None


# ---------------------------------------------------------------------------
# create_realtime_session Tests
# ---------------------------------------------------------------------------


class TestCreateRealtimeSession:
    """Test create_realtime_session factory function."""

    @pytest.mark.asyncio
    async def test_create_realtime_session_success(self) -> None:
        """create_realtime_session successfully creates and connects session."""
        # Mock database objects
        mock_agent = MagicMock()
        mock_agent.id = uuid.uuid4()
        mock_agent.raw_config = {}
        mock_agent.memory_enabled = False
        mock_agent.filler_words = {}

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "Test Project"
        mock_project.timezone = "America/New_York"
        mock_project.agent = mock_agent
        mock_project.raw_config = {}

        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "Test Account"

        mock_project.account = mock_account

        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock RawConfig._build_agent_prompt
        mock_prompt = "Test system prompt"

        with patch(
            "services.realtime_service._implementation.RawConfig"
        ) as mock_raw_config_cls:
            mock_raw_config_instance = AsyncMock()
            mock_raw_config_instance._build_agent_prompt = AsyncMock(
                return_value=mock_prompt
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}):
                with patch(
                    "services.realtime_service._implementation.RealtimeSession"
                ) as mock_session_cls:
                    mock_realtime_session = AsyncMock()
                    mock_realtime_session.connect = AsyncMock()
                    mock_session_cls.return_value = mock_realtime_session

                    result = await create_realtime_session(
                        mock_session, recipient_id="+15551234567"
                    )

        assert result == mock_realtime_session
        mock_realtime_session.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_realtime_session_project_not_found(self) -> None:
        """create_realtime_session raises ValueError when project not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(
            ValueError, match="Project not found for channel identifier"
        ):
            await create_realtime_session(mock_session, recipient_id="+15551234567")

    @pytest.mark.asyncio
    async def test_create_realtime_session_agent_not_found(self) -> None:
        """create_realtime_session raises ValueError when agent not found."""
        mock_project = MagicMock()
        mock_project.name = "Test Project"
        mock_project.agent = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Agent not found for project"):
            await create_realtime_session(mock_session, recipient_id="+15551234567")

    @pytest.mark.asyncio
    async def test_create_realtime_session_empty_prompt(self) -> None:
        """create_realtime_session raises ValueError when system prompt is empty."""
        mock_agent = MagicMock()
        mock_agent.id = uuid.uuid4()
        mock_agent.raw_config = {}
        mock_agent.memory_enabled = False
        mock_agent.filler_words = {}

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "Test Project"
        mock_project.timezone = "America/New_York"
        mock_project.agent = mock_agent
        mock_project.raw_config = {}

        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_project.account = mock_account

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "services.realtime_service._implementation.RawConfig"
        ) as mock_raw_config_cls:
            mock_raw_config_instance = AsyncMock()
            # Return empty prompt
            mock_raw_config_instance._build_agent_prompt = AsyncMock(return_value="")
            mock_raw_config_cls.return_value = mock_raw_config_instance

            with pytest.raises(ValueError, match="Agent prompt is empty"):
                await create_realtime_session(mock_session, recipient_id="+15551234567")

    @pytest.mark.asyncio
    async def test_create_realtime_session_missing_api_key(self) -> None:
        """create_realtime_session raises ValueError when OPENAI_API_KEY not set."""
        mock_agent = MagicMock()
        mock_agent.id = uuid.uuid4()
        mock_agent.raw_config = {}
        mock_agent.memory_enabled = False
        mock_agent.filler_words = {}

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "Test Project"
        mock_project.timezone = "America/New_York"
        mock_project.agent = mock_agent
        mock_project.raw_config = {}

        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_project.account = mock_account

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "services.realtime_service._implementation.RawConfig"
        ) as mock_raw_config_cls:
            mock_raw_config_instance = AsyncMock()
            mock_raw_config_instance._build_agent_prompt = AsyncMock(
                return_value="Test prompt"
            )
            mock_raw_config_cls.return_value = mock_raw_config_instance

            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(
                    ValueError, match="OPENAI_API_KEY environment variable not set"
                ):
                    await create_realtime_session(
                        mock_session, recipient_id="+15551234567"
                    )

    @pytest.mark.asyncio
    async def test_create_realtime_session_builds_correct_channel_identifier(
        self,
    ) -> None:
        """create_realtime_session builds correct voice channel identifier."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError):
            await create_realtime_session(mock_session, recipient_id="+15551234567")

        # Verify the query was executed
        # The channel identifier should be "voice:+15551234567"
        assert mock_session.execute.called


# ---------------------------------------------------------------------------
# _build_demo_tools Tests
# ---------------------------------------------------------------------------


class TestBuildRealtimeTools:
    """Test _build_realtime_tools() function."""

    def test_builds_tools_from_registry(self) -> None:
        from services.realtime_service._implementation import _build_realtime_tools

        mock_func = MagicMock()
        mock_func.entrypoint = lambda: "ok"
        mock_func.description = "Test tool"
        mock_func.parameters = {"type": "object", "properties": {}}

        mock_toolkit = MagicMock()
        mock_toolkit.functions = {"test_func": mock_func}

        mock_identifier = MagicMock()
        mock_identifier.tool_name = "test_tool"

        mock_tool_config = MagicMock()
        mock_tool_config.identifiers = [mock_identifier]
        mock_tool_config.metadata = MagicMock()

        with patch("tools.registry.tool_registry") as mock_registry:
            mock_registry.get_tool.return_value = mock_toolkit
            tools, executors = _build_realtime_tools(mock_tool_config)

        assert len(tools) == 1
        assert tools[0]["name"] == "test_func"
        assert "test_func" in executors

    def test_skips_tool_not_in_registry(self) -> None:
        from services.realtime_service._implementation import _build_realtime_tools

        mock_identifier = MagicMock()
        mock_identifier.tool_name = "missing_tool"

        mock_tool_config = MagicMock()
        mock_tool_config.identifiers = [mock_identifier]
        mock_tool_config.metadata = MagicMock()

        with patch("tools.registry.tool_registry") as mock_registry:
            mock_registry.get_tool.return_value = None
            tools, executors = _build_realtime_tools(mock_tool_config)

        assert len(tools) == 0
        assert len(executors) == 0

    def test_skips_function_without_entrypoint(self) -> None:
        from services.realtime_service._implementation import _build_realtime_tools

        mock_func = MagicMock()
        mock_func.entrypoint = None
        mock_func.description = "No entrypoint"

        mock_toolkit = MagicMock()
        mock_toolkit.functions = {"broken_func": mock_func}

        mock_identifier = MagicMock()
        mock_identifier.tool_name = "test_tool"

        mock_tool_config = MagicMock()
        mock_tool_config.identifiers = [mock_identifier]
        mock_tool_config.metadata = MagicMock()

        with patch("tools.registry.tool_registry") as mock_registry:
            mock_registry.get_tool.return_value = mock_toolkit
            tools, executors = _build_realtime_tools(mock_tool_config)

        assert len(tools) == 0
        assert len(executors) == 0

    def test_handles_tool_instantiation_error(self) -> None:
        from services.realtime_service._implementation import _build_realtime_tools

        mock_identifier = MagicMock()
        mock_identifier.tool_name = "broken_tool"

        mock_tool_config = MagicMock()
        mock_tool_config.identifiers = [mock_identifier]
        mock_tool_config.metadata = MagicMock()

        with patch("tools.registry.tool_registry") as mock_registry:
            mock_registry.get_tool.side_effect = RuntimeError("init failed")
            tools, executors = _build_realtime_tools(mock_tool_config)

        assert len(tools) == 0
        assert len(executors) == 0


# ---------------------------------------------------------------------------
# Delayed interruption OpenAI cancel Tests
# ---------------------------------------------------------------------------


class TestDelayedInterruptionCancel:
    """Test _delayed_interruption OpenAI response.cancel() path."""

    @pytest.mark.asyncio
    async def test_delayed_interruption_cancels_openai_response(self) -> None:
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                interruption_delay_ms=10,
            ),
        )
        mock_connection = MagicMock()
        mock_connection.response.cancel = AsyncMock()
        session.connection = mock_connection

        await session._delayed_interruption()

        mock_connection.response.cancel.assert_awaited_once()


# ---------------------------------------------------------------------------
# _build_demo_tools Tests
# ---------------------------------------------------------------------------


class TestBuildDemoTools:
    """Test _build_demo_tools() function."""

    def test_returns_two_tools(self) -> None:
        tools, executors = _build_demo_tools()
        assert len(tools) == 2
        assert "get_store_hours" in executors
        assert "get_daily_specials" in executors

    def test_tool_definitions_have_required_fields(self) -> None:
        tools, _ = _build_demo_tools()
        for tool in tools:
            assert tool["type"] == "function"
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool

    def test_get_store_hours_returns_json(self) -> None:
        import json

        _, executors = _build_demo_tools()
        result = executors["get_store_hours"]()
        data = json.loads(result)
        assert "monday" in data
        assert "sunday" in data

    def test_get_daily_specials_returns_json(self) -> None:
        import json

        _, executors = _build_demo_tools()
        result = executors["get_daily_specials"]()
        data = json.loads(result)
        assert "appetizer" in data
        assert "entree" in data


# ---------------------------------------------------------------------------
# _handle_tool_call Tests
# ---------------------------------------------------------------------------


class TestHandleToolCall:
    """Test RealtimeSession._handle_tool_call() method."""

    @pytest.mark.asyncio
    async def test_handle_tool_call_executes_and_sends_result(self) -> None:
        on_tool_call = AsyncMock(return_value='{"hours": "9-5"}')
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
            on_tool_call=on_tool_call,
        )
        mock_connection = MagicMock()
        mock_connection.conversation.item.create = AsyncMock()
        mock_connection.response.create = AsyncMock()
        session.connection = mock_connection

        event = MagicMock()
        event.call_id = "call_123"
        event.name = "get_store_hours"
        event.arguments = "{}"

        await session._handle_tool_call(event)

        on_tool_call.assert_awaited_once_with("get_store_hours", "{}")
        mock_connection.conversation.item.create.assert_called_once()
        mock_connection.response.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_tool_call_without_handler(self) -> None:
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )
        mock_connection = MagicMock()
        mock_connection.conversation.item.create = AsyncMock()
        mock_connection.response.create = AsyncMock()
        session.connection = mock_connection

        event = MagicMock()
        event.call_id = "call_123"
        event.name = "get_store_hours"
        event.arguments = "{}"

        await session._handle_tool_call(event)

        call_args = mock_connection.conversation.item.create.call_args
        assert "error" in call_args[1]["item"]["output"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_timeout(self) -> None:
        on_tool_call = AsyncMock(side_effect=asyncio.TimeoutError)
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
            on_tool_call=on_tool_call,
        )
        mock_connection = MagicMock()
        mock_connection.conversation.item.create = AsyncMock()
        mock_connection.response.create = AsyncMock()
        session.connection = mock_connection

        with patch(
            "services.realtime_service._implementation.asyncio.wait_for"
        ) as mock_wf:
            mock_wf.side_effect = asyncio.TimeoutError
            event = MagicMock()
            event.call_id = "call_123"
            event.name = "slow_tool"
            event.arguments = "{}"

            await session._handle_tool_call(event)

        call_args = mock_connection.conversation.item.create.call_args
        assert "timed out" in call_args[1]["item"]["output"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_exception(self) -> None:
        on_tool_call = AsyncMock(side_effect=RuntimeError("boom"))
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
            on_tool_call=on_tool_call,
        )
        mock_connection = MagicMock()
        mock_connection.conversation.item.create = AsyncMock()
        mock_connection.response.create = AsyncMock()
        session.connection = mock_connection

        with patch(
            "services.realtime_service._implementation.asyncio.wait_for"
        ) as mock_wf:
            mock_wf.side_effect = RuntimeError("boom")
            event = MagicMock()
            event.call_id = "call_123"
            event.name = "bad_tool"
            event.arguments = "{}"

            await session._handle_tool_call(event)

        call_args = mock_connection.conversation.item.create.call_args
        assert "boom" in call_args[1]["item"]["output"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_no_connection(self) -> None:
        on_tool_call = AsyncMock(return_value='{"ok": true}')
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
            on_tool_call=on_tool_call,
        )
        session.connection = None

        event = MagicMock()
        event.call_id = "call_123"
        event.name = "tool"
        event.arguments = "{}"

        await session._handle_tool_call(event)

    @pytest.mark.asyncio
    async def test_handle_tool_call_send_result_failure(self) -> None:
        on_tool_call = AsyncMock(return_value='{"ok": true}')
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
            on_tool_call=on_tool_call,
        )
        mock_connection = MagicMock()
        mock_connection.conversation.item.create = AsyncMock(
            side_effect=RuntimeError("ws closed")
        )
        session.connection = mock_connection

        event = MagicMock()
        event.call_id = "call_123"
        event.name = "tool"
        event.arguments = "{}"

        await session._handle_tool_call(event)


# ---------------------------------------------------------------------------
# _filter_tool_args Tests
# ---------------------------------------------------------------------------


class TestFilterToolArgs:
    """Test RealtimeSession._filter_tool_args() method."""

    def test_filters_unknown_kwargs(self) -> None:
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(
                system_prompt="Test",
                voice_id="alloy",
                tools=[
                    {
                        "type": "function",
                        "name": "make_reservation",
                        "description": "Make a reservation",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "party_size": {"type": "integer"},
                            },
                        },
                    }
                ],
            ),
        )
        import json

        result = session._filter_tool_args(
            "make_reservation",
            json.dumps({"name": "Alice", "party_size": 2, "phone_number": "555-1234"}),
        )
        parsed = json.loads(result)
        assert "name" in parsed
        assert "party_size" in parsed
        assert "phone_number" not in parsed

    def test_passes_through_when_tool_not_in_config(self) -> None:
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )
        import json

        args = json.dumps({"foo": "bar"})
        result = session._filter_tool_args("unknown_tool", args)
        assert result == args


# ---------------------------------------------------------------------------
# _make_tool_executor Tests
# ---------------------------------------------------------------------------


class TestMakeToolExecutor:
    """Test _make_tool_executor() function."""

    @pytest.mark.asyncio
    async def test_executes_sync_tool(self) -> None:
        from services.realtime_service._implementation import _make_tool_executor

        def my_tool(x: int) -> dict:
            return {"result": x * 2}

        executor = _make_tool_executor({"my_tool": my_tool})
        result = await executor("my_tool", '{"x": 5}')
        assert '"result": 10' in result

    @pytest.mark.asyncio
    async def test_executes_async_tool(self) -> None:
        from services.realtime_service._implementation import _make_tool_executor

        async def my_async_tool(x: int) -> dict:
            return {"result": x + 1}

        executor = _make_tool_executor({"my_async_tool": my_async_tool})
        result = await executor("my_async_tool", '{"x": 3}')
        assert '"result": 4' in result

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_tool(self) -> None:
        from services.realtime_service._implementation import _make_tool_executor

        executor = _make_tool_executor({"real_tool": lambda: "ok"})
        result = await executor("fake_tool", "{}")
        assert "Unknown tool" in result


# ---------------------------------------------------------------------------
# Tool call event in receive_audio_stream Tests
# ---------------------------------------------------------------------------


class TestToolCallEventStream:
    """Test tool call event handling in receive_audio_stream."""

    @pytest.mark.asyncio
    async def test_tool_call_event_triggers_handle(self) -> None:
        session = RealtimeSession(
            api_key="test-key",
            config=RealtimeConfig(system_prompt="Test", voice_id="alloy"),
        )

        tool_event = MagicMock()
        tool_event.type = "response.function_call_arguments.done"
        tool_event.call_id = "call_1"
        tool_event.name = "test_tool"
        tool_event.arguments = "{}"

        async def mock_event_stream():
            yield tool_event

        mock_connection = MagicMock()
        mock_connection.__aiter__ = lambda self: mock_event_stream()
        mock_connection.conversation.item.create = AsyncMock()
        mock_connection.response.create = AsyncMock()
        session.connection = mock_connection

        async for _ in session.receive_audio_stream():
            pass


# ---------------------------------------------------------------------------
# Config tool fields Tests
# ---------------------------------------------------------------------------


class TestConfigToolFields:
    """Test RealtimeConfig tool-related fields."""

    def test_tools_in_session_config_when_present(self) -> None:
        config = RealtimeConfig(
            system_prompt="Test",
            voice_id="alloy",
            tools=[
                {
                    "type": "function",
                    "name": "test",
                    "description": "t",
                    "parameters": {},
                }
            ],
        )
        session = config.to_session_config()
        assert "tools" in session
        assert session["tool_choice"] == "auto"

    def test_tools_omitted_from_session_config_when_empty(self) -> None:
        config = RealtimeConfig(system_prompt="Test", voice_id="alloy")
        session = config.to_session_config()
        assert "tools" not in session
        assert "tool_choice" not in session
