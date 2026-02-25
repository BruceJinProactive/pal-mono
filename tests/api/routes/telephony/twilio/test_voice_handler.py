# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for VoiceCallHandler.

Tests cover:
- Handler initialization
- Event handling (connected, start, media, stop)
- Bidirectional audio streaming (Twilio ↔ OpenAI)
- Background task management
- Error handling and cleanup
- WebSocket disconnect scenarios
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from api.routes.telephony.twilio._voice_handler import VoiceCallHandler
from services.realtime_service import RealtimeSession

# ---------------------------------------------------------------------------
# VoiceCallHandler Initialization Tests
# ---------------------------------------------------------------------------


class TestVoiceCallHandlerInit:
    """Test VoiceCallHandler initialization."""

    def test_init_sets_attributes(self) -> None:
        """Handler initialization sets websocket, realtime session, and counters."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        assert handler.twilio_ws == mock_ws
        assert handler.realtime_session == mock_session
        assert handler.stream_sid is None
        assert handler.call_sid is None
        assert handler.media_packet_count == 0
        assert handler.audio_chunks_sent == 0
        assert handler.streaming_task is None
        assert isinstance(handler.start_time, datetime)

    def test_init_sets_utc_start_time(self) -> None:
        """Handler initialization sets start_time in UTC timezone."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        assert handler.start_time.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# handle_call() Tests
# ---------------------------------------------------------------------------


class TestHandleCall:
    """Test VoiceCallHandler.handle_call() main event loop."""

    @pytest.mark.asyncio
    async def test_handle_call_processes_start_event_parameter(self) -> None:
        """handle_call() processes start event provided as parameter."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        start_event = {
            "event": "start",
            "streamSid": "MZ123",
            "start": {
                "callSid": "CA123",
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw"},
            },
        }

        # Mock receive_text to raise WebSocketDisconnect immediately
        # so we exit the loop after processing start_event
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect)
        mock_session.close = AsyncMock()
        mock_ws.close = AsyncMock()

        await handler.handle_call(start_event=start_event)

        # Verify start event was processed
        assert handler.stream_sid == "MZ123"
        assert handler.call_sid == "CA123"
        assert handler.streaming_task is not None

    @pytest.mark.asyncio
    async def test_handle_call_processes_connected_event(self) -> None:
        """handle_call() processes 'connected' event from Twilio."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        connected_event = {"event": "connected", "protocol": "Call"}

        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps(connected_event),
                WebSocketDisconnect,
            ]
        )
        mock_session.close = AsyncMock()
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Connected event is a no-op, just verify no errors
        mock_ws.receive_text.assert_called()

    @pytest.mark.asyncio
    async def test_handle_call_processes_media_event(self) -> None:
        """handle_call() processes 'media' event and forwards to OpenAI."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        media_event = {
            "event": "media",
            "streamSid": "MZ123",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "timestamp": "123456",
                "payload": "base64_audio_data",
            },
        }

        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps(media_event),
                WebSocketDisconnect,
            ]
        )
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Verify audio was sent to OpenAI
        mock_session.send_audio_chunk.assert_called_once_with("base64_audio_data")
        assert handler.media_packet_count == 1

    @pytest.mark.asyncio
    async def test_handle_call_processes_stop_event_and_exits_loop(self) -> None:
        """handle_call() processes 'stop' event and exits main loop."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"
        handler.call_sid = "CA123"

        stop_event = {
            "event": "stop",
            "streamSid": "MZ123",
            "stop": {
                "accountSid": "AC123",
                "callSid": "CA123",
            },
        }

        mock_ws.receive_text = AsyncMock(return_value=json.dumps(stop_event))
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Verify stop was processed and loop exited
        mock_ws.receive_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_call_handles_unknown_event_type(self) -> None:
        """handle_call() logs warning for unknown event types."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        unknown_event = {"event": "unknown_type", "data": {}}

        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps(unknown_event),
                WebSocketDisconnect,
            ]
        )
        mock_ws.close = AsyncMock()

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler.handle_call()

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            assert "Unknown event type" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_handle_call_handles_json_decode_error(self) -> None:
        """handle_call() handles invalid JSON and continues processing."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Invalid JSON followed by valid disconnect
        mock_ws.receive_text = AsyncMock(
            side_effect=[
                "invalid json {{{",
                WebSocketDisconnect,
            ]
        )
        mock_ws.close = AsyncMock()

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler.handle_call()

            # Verify error was logged
            mock_logger.error.assert_called()
            assert "Failed to parse" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_handle_call_handles_websocket_disconnect(self) -> None:
        """handle_call() handles WebSocketDisconnect gracefully."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect)
        mock_ws.close = AsyncMock()

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler.handle_call()

            # Verify disconnect was logged
            mock_logger.info.assert_called()
            assert "disconnected" in str(mock_logger.info.call_args).lower()

    @pytest.mark.asyncio
    async def test_handle_call_handles_unexpected_error(self) -> None:
        """handle_call() logs unexpected errors with traceback."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        mock_ws.receive_text = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        mock_ws.close = AsyncMock()

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler.handle_call()

            # Verify error was logged with exc_info
            mock_logger.error.assert_called()
            call_kwargs = mock_logger.error.call_args[1]
            assert call_kwargs.get("exc_info") is True

    @pytest.mark.asyncio
    async def test_handle_call_calls_cleanup_in_finally_block(self) -> None:
        """handle_call() always calls cleanup in finally block."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect)
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Verify cleanup was called (session and websocket closed)
        mock_session.close.assert_called_once()
        mock_ws.close.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_start() Tests
# ---------------------------------------------------------------------------


class TestHandleStart:
    """Test VoiceCallHandler._handle_start() method."""

    @pytest.mark.asyncio
    async def test_handle_start_extracts_stream_metadata(self) -> None:
        """_handle_start() extracts streamSid and callSid from event."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        start_message = {
            "event": "start",
            "streamSid": "MZ123abc",
            "start": {
                "callSid": "CA456def",
                "tracks": ["inbound", "outbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000},
            },
        }

        await handler._handle_start(start_message)

        assert handler.stream_sid == "MZ123abc"
        assert handler.call_sid == "CA456def"

    @pytest.mark.asyncio
    async def test_handle_start_creates_streaming_task(self) -> None:
        """_handle_start() creates background task for OpenAI → Twilio streaming."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        start_message = {
            "event": "start",
            "streamSid": "MZ123",
            "start": {"callSid": "CA123"},
        }

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            await handler._handle_start(start_message)

            # Verify task was created
            mock_create_task.assert_called_once()
            assert handler.streaming_task == mock_task

    @pytest.mark.asyncio
    async def test_handle_start_logs_stream_info(self) -> None:
        """_handle_start() logs stream metadata."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        start_message = {
            "event": "start",
            "streamSid": "MZ123",
            "start": {
                "callSid": "CA123",
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw"},
            },
        }

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._handle_start(start_message)

            # Verify logging
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert "Stream started" in str(log_call)


# ---------------------------------------------------------------------------
# _handle_media() Tests
# ---------------------------------------------------------------------------


class TestHandleMedia:
    """Test VoiceCallHandler._handle_media() method."""

    @pytest.mark.asyncio
    async def test_handle_media_forwards_audio_to_openai(self) -> None:
        """_handle_media() forwards µ-law audio directly to OpenAI."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        media_message = {
            "event": "media",
            "streamSid": "MZ123",
            "media": {
                "track": "inbound",
                "chunk": "5",
                "timestamp": "789012",
                "payload": "g711_ulaw_base64_data",
            },
        }

        await handler._handle_media(media_message)

        # Verify audio was sent (no conversion - direct passthrough)
        mock_session.send_audio_chunk.assert_called_once_with("g711_ulaw_base64_data")
        assert handler.media_packet_count == 1

    @pytest.mark.asyncio
    async def test_handle_media_increments_packet_counter(self) -> None:
        """_handle_media() increments media_packet_count."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        media_message = {
            "event": "media",
            "media": {"payload": "audio1"},
        }

        # Send 3 media packets
        await handler._handle_media(media_message)
        await handler._handle_media(media_message)
        await handler._handle_media(media_message)

        assert handler.media_packet_count == 3

    @pytest.mark.asyncio
    async def test_handle_media_skips_empty_payload(self) -> None:
        """_handle_media() skips processing if payload is empty."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        media_message = {
            "event": "media",
            "media": {"payload": ""},  # Empty payload
        }

        await handler._handle_media(media_message)

        # Should not call send_audio_chunk
        mock_session.send_audio_chunk.assert_not_called()
        assert handler.media_packet_count == 1  # Counter still increments

    @pytest.mark.asyncio
    async def test_handle_media_logs_every_100_packets(self) -> None:
        """_handle_media() logs debug info every 100 packets."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"

        media_message = {"event": "media", "media": {"payload": "audio"}}

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            # Send 99 packets - should not log
            for _ in range(99):
                await handler._handle_media(media_message)

            mock_logger.debug.assert_not_called()

            # Send 100th packet - should log
            await handler._handle_media(media_message)

            mock_logger.debug.assert_called_once()
            log_call = mock_logger.debug.call_args
            assert "Audio Twilio→OpenAI" in str(log_call)

    @pytest.mark.asyncio
    async def test_handle_media_handles_send_error(self) -> None:
        """_handle_media() logs error if sending to OpenAI fails."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock(
            side_effect=RuntimeError("OpenAI connection lost")
        )

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        media_message = {"event": "media", "media": {"payload": "audio"}}

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._handle_media(media_message)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert "Error processing audio" in str(mock_logger.error.call_args)


# ---------------------------------------------------------------------------
# _handle_stop() Tests
# ---------------------------------------------------------------------------


class TestHandleStop:
    """Test VoiceCallHandler._handle_stop() method."""

    @pytest.mark.asyncio
    async def test_handle_stop_logs_statistics(self) -> None:
        """_handle_stop() logs call duration and statistics."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"
        handler.call_sid = "CA123"
        handler.media_packet_count = 500
        handler.audio_chunks_sent = 450

        stop_message = {"event": "stop", "streamSid": "MZ123"}

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._handle_stop(stop_message)

            # Verify statistics were logged
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert "Stream stopped" in str(log_call)
            # Check extra data contains statistics
            extra = log_call[1]["extra"]
            assert extra["stream_sid"] == "MZ123"
            assert extra["call_sid"] == "CA123"
            assert extra["media_packets"] == 500
            assert extra["audio_chunks_sent"] == 450
            assert "duration_seconds" in extra

    @pytest.mark.asyncio
    async def test_handle_stop_calculates_duration(self) -> None:
        """_handle_stop() calculates call duration correctly."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"
        handler.call_sid = "CA123"

        # Mock start_time to be 30 seconds ago
        with patch(
            "api.routes.telephony.twilio._voice_handler.datetime"
        ) as mock_datetime:
            mock_now = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
            handler.start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now

            stop_message = {"event": "stop"}

            with patch(
                "api.routes.telephony.twilio._voice_handler.logger"
            ) as mock_logger:
                await handler._handle_stop(stop_message)

                # Verify duration is 30 seconds
                extra = mock_logger.info.call_args[1]["extra"]
                assert extra["duration_seconds"] == 30.0


# ---------------------------------------------------------------------------
# _stream_openai_to_twilio() Tests
# ---------------------------------------------------------------------------


class TestStreamOpenAIToTwilio:
    """Test VoiceCallHandler._stream_openai_to_twilio() background task."""

    @pytest.mark.asyncio
    async def test_stream_openai_to_twilio_forwards_audio_chunks(self) -> None:
        """_stream_openai_to_twilio() forwards audio from OpenAI to Twilio."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"

        # Mock audio stream from OpenAI
        async def mock_audio_stream():
            yield "audio_chunk_1"
            yield "audio_chunk_2"
            yield "audio_chunk_3"

        mock_session.receive_audio_stream = mock_audio_stream

        await handler._stream_openai_to_twilio()

        # Verify 3 messages were sent to Twilio
        assert mock_ws.send_text.call_count == 3
        assert handler.audio_chunks_sent == 3

        # Verify message format
        first_call = mock_ws.send_text.call_args_list[0][0][0]
        message = json.loads(first_call)
        assert message["event"] == "media"
        assert message["streamSid"] == "MZ123"
        assert message["media"]["payload"] == "audio_chunk_1"

    @pytest.mark.asyncio
    async def test_stream_openai_to_twilio_increments_counter(self) -> None:
        """_stream_openai_to_twilio() increments audio_chunks_sent counter."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"

        async def mock_audio_stream():
            for i in range(10):
                yield f"chunk_{i}"

        mock_session.receive_audio_stream = mock_audio_stream

        await handler._stream_openai_to_twilio()

        assert handler.audio_chunks_sent == 10

    @pytest.mark.asyncio
    async def test_stream_openai_to_twilio_logs_every_100_chunks(self) -> None:
        """_stream_openai_to_twilio() logs debug info every 100 chunks."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"

        async def mock_audio_stream():
            for i in range(101):
                yield f"chunk_{i}"

        mock_session.receive_audio_stream = mock_audio_stream

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._stream_openai_to_twilio()

            # Should log once at chunk 100
            assert mock_logger.debug.call_count == 1
            log_call = mock_logger.debug.call_args
            assert "Audio OpenAI→Twilio" in str(log_call)

    @pytest.mark.asyncio
    async def test_stream_openai_to_twilio_handles_send_error(self) -> None:
        """_stream_openai_to_twilio() logs error if sending to Twilio fails."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.send_text = AsyncMock(side_effect=RuntimeError("WebSocket closed"))
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )
        handler.stream_sid = "MZ123"

        async def mock_audio_stream():
            yield "audio_chunk"

        mock_session.receive_audio_stream = mock_audio_stream

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._stream_openai_to_twilio()

            # Verify error was logged
            mock_logger.error.assert_called()
            assert "Error converting/sending audio" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_stream_openai_to_twilio_handles_stream_error(self) -> None:
        """_stream_openai_to_twilio() logs error if audio stream fails."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        async def mock_audio_stream():
            yield "chunk_1"
            raise RuntimeError("OpenAI stream error")

        mock_session.receive_audio_stream = mock_audio_stream

        with patch("api.routes.telephony.twilio._voice_handler.logger") as mock_logger:
            await handler._stream_openai_to_twilio()

            # Verify error was logged
            mock_logger.error.assert_called()
            assert "Streaming task error" in str(mock_logger.error.call_args)


# ---------------------------------------------------------------------------
# _cleanup() Tests
# ---------------------------------------------------------------------------


class TestCleanup:
    """Test VoiceCallHandler._cleanup() method."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_streaming_task(self) -> None:
        """_cleanup() cancels background streaming task."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Create mock task that raises CancelledError when awaited
        async def cancelled_coro():
            raise asyncio.CancelledError()

        mock_task = asyncio.create_task(cancelled_coro())
        mock_task.cancel()

        handler.streaming_task = mock_task

        # Should handle CancelledError gracefully
        await handler._cleanup()

        # Verify task is done/cancelled
        assert mock_task.done() or mock_task.cancelled()

    @pytest.mark.asyncio
    async def test_cleanup_closes_realtime_session(self) -> None:
        """_cleanup() closes realtime session."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        await handler._cleanup()

        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_closes_twilio_websocket(self) -> None:
        """_cleanup() closes Twilio WebSocket."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        await handler._cleanup()

        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_task_already_done(self) -> None:
        """_cleanup() skips cancellation if task is already done."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Task already done
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = True
        handler.streaming_task = mock_task

        await handler._cleanup()

        # Should not call cancel
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_handles_no_task(self) -> None:
        """_cleanup() handles case where streaming task was never created."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # No task created
        handler.streaming_task = None

        # Should not raise exception
        await handler._cleanup()

        mock_session.close.assert_called_once()
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_websocket_close_error(self) -> None:
        """_cleanup() continues cleanup even if WebSocket close fails."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.close = AsyncMock(side_effect=RuntimeError("Already closed"))
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Should not raise exception
        await handler._cleanup()

        # Session should still be closed
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestVoiceCallHandlerIntegration:
    """Integration tests for complete call flows."""

    @pytest.mark.asyncio
    async def test_complete_call_flow(self) -> None:
        """Test complete call flow: start, media exchange, stop."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock()
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Mock audio stream from OpenAI
        async def mock_audio_stream():
            yield "openai_audio_1"
            yield "openai_audio_2"

        mock_session.receive_audio_stream = mock_audio_stream

        # Simulate call flow
        events = [
            json.dumps({"event": "connected", "protocol": "Call"}),
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "MZ123",
                    "start": {"callSid": "CA123", "tracks": ["inbound"]},
                }
            ),
            json.dumps({"event": "media", "media": {"payload": "twilio_audio_1"}}),
            json.dumps({"event": "media", "media": {"payload": "twilio_audio_2"}}),
            json.dumps({"event": "stop", "streamSid": "MZ123"}),
        ]

        mock_ws.receive_text = AsyncMock(side_effect=events)
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Verify complete flow
        assert handler.stream_sid == "MZ123"
        assert handler.call_sid == "CA123"
        assert handler.media_packet_count == 2
        # Verify audio was sent to OpenAI
        assert mock_session.send_audio_chunk.call_count == 2
        # Verify cleanup was performed
        mock_session.close.assert_called_once()
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_during_call_triggers_cleanup(self) -> None:
        """Test that errors during call still trigger cleanup."""
        mock_ws = MagicMock(spec=WebSocket)
        mock_session = MagicMock(spec=RealtimeSession)
        mock_session.send_audio_chunk = AsyncMock(side_effect=RuntimeError("Error"))
        mock_session.close = AsyncMock()

        handler = VoiceCallHandler(
            twilio_websocket=mock_ws,
            realtime_session=mock_session,
        )

        # Error during media processing
        events = [
            json.dumps(
                {
                    "event": "start",
                    "streamSid": "MZ123",
                    "start": {"callSid": "CA123"},
                }
            ),
            json.dumps({"event": "media", "media": {"payload": "audio"}}),
        ]

        mock_ws.receive_text = AsyncMock(side_effect=events + [WebSocketDisconnect])
        mock_ws.close = AsyncMock()

        await handler.handle_call()

        # Verify cleanup was still performed
        mock_session.close.assert_called_once()
        mock_ws.close.assert_called_once()
