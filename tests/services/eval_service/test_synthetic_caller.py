"""Tests for SyntheticCaller — the livekit-rtc based eval caller."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._synthetic_caller import SyntheticCaller

_FAKE_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test"  # noqa: S105


def _make_room_info() -> MagicMock:
    ri = MagicMock()
    ri.room_name = "eval-voice-abc"
    ri.livekit_url = "wss://test.livekit.cloud"
    return ri


def _make_voice_profile() -> MagicMock:
    vp = MagicMock()
    vp.voice_id = "voice-123"
    vp.speed = 1.0
    return vp


def _make_tts_engine(chunks: list[bytes] | None = None) -> MagicMock:
    """Create a mock TTS engine with an async-generator synthesize_streaming."""
    engine = MagicMock()
    engine.close = AsyncMock()

    audio_chunks = chunks if chunks is not None else []

    async def _synth_stream(*args: Any, **kwargs: Any) -> AsyncIterator[bytes]:
        for c in audio_chunks:
            yield c

    engine.synthesize_streaming = _synth_stream
    return engine


def _make_mock_room() -> MagicMock:
    """Create a pre-configured mock Room with common defaults."""
    mock_room = MagicMock()
    mock_room.connect = AsyncMock()
    mock_room.disconnect = AsyncMock()
    mock_room.remote_participants = {"agent-1": MagicMock()}
    mock_room.local_participant = MagicMock()
    mock_room.local_participant.publish_track = AsyncMock()
    mock_room.local_participant.sid = "local-sid"
    mock_room.on = MagicMock(return_value=lambda fn: fn)
    mock_room.off = MagicMock()
    return mock_room


# ---------------------------------------------------------------------------
# run_call — full flow
# ---------------------------------------------------------------------------


class TestSyntheticCallerRunCall:
    async def test_returns_call_id(self) -> None:
        """run_call returns the provided call_id after the call completes."""
        caller = SyntheticCaller(livekit_url="wss://test.livekit.cloud")

        with patch.object(caller, "_room", _make_mock_room()):
            with (
                patch.object(caller, "_speak_turn", new_callable=AsyncMock),
                patch.object(
                    caller, "_wait_for_agent_response", new_callable=AsyncMock
                ),
            ):
                call_id = await caller.run_call(
                    room_info=_make_room_info(),
                    caller_token=_FAKE_TOKEN,
                    turns=["Hello"],
                    voice_profile=_make_voice_profile(),
                    tts_engine=_make_tts_engine(),
                    call_id="eval-abc123",
                )

        assert call_id == "eval-abc123"

    async def test_connects_to_room(self) -> None:
        """Verifies room.connect is called with the correct URL and token."""
        caller = SyntheticCaller(livekit_url="wss://test.livekit.cloud")
        mock_room = _make_mock_room()

        with patch.object(caller, "_room", mock_room):
            with (
                patch.object(caller, "_speak_turn", new_callable=AsyncMock),
                patch.object(
                    caller, "_wait_for_agent_response", new_callable=AsyncMock
                ),
            ):
                await caller.run_call(
                    room_info=_make_room_info(),
                    caller_token=_FAKE_TOKEN,
                    turns=["Hello"],
                    voice_profile=_make_voice_profile(),
                    tts_engine=_make_tts_engine(),
                    call_id="eval-abc",
                )

        mock_room.connect.assert_awaited_once_with(
            "wss://test.livekit.cloud", _FAKE_TOKEN
        )

    async def test_multi_turn_pauses_between_turns(self) -> None:
        """With 2+ turns, waits for agent and pauses between each turn."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            pause_between_turns_s=0.01,
        )

        mock_wait = AsyncMock()

        with patch.object(caller, "_room", _make_mock_room()):
            with (
                patch.object(caller, "_speak_turn", new_callable=AsyncMock),
                patch.object(caller, "_wait_for_agent_response", mock_wait),
            ):
                await caller.run_call(
                    room_info=_make_room_info(),
                    caller_token=_FAKE_TOKEN,
                    turns=["Hello", "Order a pizza"],
                    voice_profile=_make_voice_profile(),
                    tts_engine=_make_tts_engine(),
                    call_id="eval-multi",
                )

        # wait_for_agent_response called: once for greeting + once between turns + once after last
        assert mock_wait.await_count == 3

    async def test_disconnects_on_error(self) -> None:
        """Room.disconnect is called even when the call fails."""
        caller = SyntheticCaller(livekit_url="wss://test.livekit.cloud")
        mock_room = _make_mock_room()
        mock_room.local_participant.publish_track = AsyncMock(
            side_effect=RuntimeError("publish failed")
        )

        with patch.object(caller, "_room", mock_room):
            with pytest.raises(RuntimeError, match="publish failed"):
                await caller.run_call(
                    room_info=_make_room_info(),
                    caller_token=_FAKE_TOKEN,
                    turns=["Hello"],
                    voice_profile=_make_voice_profile(),
                    tts_engine=_make_tts_engine(),
                    call_id="eval-err",
                )

        mock_room.disconnect.assert_awaited_once()

    async def test_disconnect_exception_is_swallowed(self) -> None:
        """If disconnect raises, the error is logged but not re-raised."""
        caller = SyntheticCaller(livekit_url="wss://test")
        mock_room = _make_mock_room()
        mock_room.local_participant.publish_track = AsyncMock(
            side_effect=RuntimeError("publish failed")
        )
        mock_room.disconnect = AsyncMock(side_effect=OSError("socket closed"))

        with patch.object(caller, "_room", mock_room):
            with pytest.raises(RuntimeError, match="publish failed"):
                await caller.run_call(
                    room_info=_make_room_info(),
                    caller_token=_FAKE_TOKEN,
                    turns=["Hello"],
                    voice_profile=_make_voice_profile(),
                    tts_engine=_make_tts_engine(),
                    call_id="eval-disc-err",
                )

        mock_room.disconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# _wait_for_agent
# ---------------------------------------------------------------------------


class TestWaitForAgent:
    async def test_returns_immediately_if_agent_present(self) -> None:
        """If remote_participants is non-empty, returns immediately."""
        caller = SyntheticCaller(livekit_url="wss://test")

        with patch.object(caller, "_room") as mock_room:
            mock_room.remote_participants = {"agent-1": MagicMock()}
            await caller._wait_for_agent()

    async def test_timeout_when_no_agent(self) -> None:
        """Raises TimeoutError if no agent joins within timeout."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            agent_response_timeout_s=0.1,
        )

        with patch.object(caller, "_room") as mock_room:
            mock_room.remote_participants = {}
            mock_room.on = MagicMock(return_value=lambda fn: fn)
            mock_room.off = MagicMock()

            with pytest.raises(TimeoutError, match="Agent did not join"):
                await caller._wait_for_agent()

    async def test_agent_joins_after_wait(self) -> None:
        """Agent joins via participant_connected event while waiting."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            agent_response_timeout_s=5.0,
        )

        on_callbacks: dict[str, Any] = {}

        def fake_on(event: str) -> Any:
            def decorator(fn: Any) -> Any:
                on_callbacks[event] = fn
                return fn

            return decorator

        with patch.object(caller, "_room") as mock_room:
            mock_room.remote_participants = {}
            mock_room.on = MagicMock(side_effect=fake_on)
            mock_room.off = MagicMock()

            async def fire_event() -> None:
                await asyncio.sleep(0.05)
                cb = on_callbacks.get("participant_connected")
                if cb:
                    cb(MagicMock(identity="agent-1"))

            task = asyncio.create_task(fire_event())
            await caller._wait_for_agent()
            await task


# ---------------------------------------------------------------------------
# _wait_for_agent_response
# ---------------------------------------------------------------------------


class TestWaitForAgentResponse:
    async def test_timeout_returns_gracefully(self) -> None:
        """If agent never speaks, returns after timeout without error."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            agent_response_timeout_s=0.1,
        )

        with patch.object(caller, "_room") as mock_room:
            mock_room.local_participant = MagicMock()
            mock_room.local_participant.sid = "local-sid"
            mock_room.on = MagicMock(return_value=lambda fn: fn)
            mock_room.off = MagicMock()

            await caller._wait_for_agent_response()

    async def test_agent_speaks_then_stops(self) -> None:
        """Detects agent start → stop via active_speakers_changed events."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            agent_response_timeout_s=5.0,
        )

        on_callbacks: dict[str, Any] = {}

        def fake_on(event: str) -> Any:
            def decorator(fn: Any) -> Any:
                on_callbacks[event] = fn
                return fn

            return decorator

        agent_participant = MagicMock()
        agent_participant.sid = "agent-sid"

        with patch.object(caller, "_room") as mock_room:
            mock_room.local_participant = MagicMock()
            mock_room.local_participant.sid = "local-sid"
            mock_room.on = MagicMock(side_effect=fake_on)
            mock_room.off = MagicMock()

            async def fire_events() -> None:
                await asyncio.sleep(0.05)
                cb = on_callbacks.get("active_speakers_changed")
                if cb:
                    # Agent starts speaking
                    cb([agent_participant])
                    await asyncio.sleep(0.05)
                    # Agent stops speaking
                    cb([])

            task = asyncio.create_task(fire_events())
            await caller._wait_for_agent_response()
            await task

    async def test_agent_stop_timeout(self) -> None:
        """If agent starts speaking but never stops, returns after timeout."""
        caller = SyntheticCaller(
            livekit_url="wss://test",
            agent_response_timeout_s=0.15,
        )

        on_callbacks: dict[str, Any] = {}

        def fake_on(event: str) -> Any:
            def decorator(fn: Any) -> Any:
                on_callbacks[event] = fn
                return fn

            return decorator

        agent_participant = MagicMock()
        agent_participant.sid = "agent-sid"

        with patch.object(caller, "_room") as mock_room:
            mock_room.local_participant = MagicMock()
            mock_room.local_participant.sid = "local-sid"
            mock_room.on = MagicMock(side_effect=fake_on)
            mock_room.off = MagicMock()

            async def fire_start_only() -> None:
                await asyncio.sleep(0.05)
                cb = on_callbacks.get("active_speakers_changed")
                if cb:
                    cb([agent_participant])
                # Never fire stop

            task = asyncio.create_task(fire_start_only())
            await caller._wait_for_agent_response()
            await task


# ---------------------------------------------------------------------------
# _speak_turn
# ---------------------------------------------------------------------------


class TestSpeakTurn:
    async def test_publishes_tts_frames(self) -> None:
        """TTS chunks are captured as AudioFrames on the audio source."""
        caller = SyntheticCaller(livekit_url="wss://test")

        mock_audio_source = MagicMock()
        mock_audio_source.capture_frame = AsyncMock()

        profile = _make_voice_profile()
        chunks = [b"\x00" * 1920, b"\x00" * 1920]  # 2 frames of 20ms
        tts_engine = _make_tts_engine(chunks=chunks)

        with patch("services.eval_service._synthetic_caller.rtc") as mock_rtc:
            mock_frame = MagicMock()
            mock_rtc.AudioFrame.return_value = mock_frame

            await caller._speak_turn("Hello", mock_audio_source, tts_engine, profile)

        assert mock_audio_source.capture_frame.await_count == 2


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_satisfies_synthetic_caller_factory(self) -> None:
        """SyntheticCaller has the same run_call signature as the protocol."""
        from services.eval_service._voice_eval_runner import SyntheticCallerFactory

        proto_sig = inspect.signature(SyntheticCallerFactory.run_call)
        impl_sig = inspect.signature(SyntheticCaller.run_call)

        proto_params = list(proto_sig.parameters.keys())
        impl_params = list(impl_sig.parameters.keys())
        assert proto_params == impl_params
