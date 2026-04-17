"""Integration tests for the voice eval pipeline.

Tests the full flow: scenario → voice runner → ConversationRecord → evaluators.
All external dependencies (LiveKit, TTS, DB, LLM) are mocked.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._evaluators import (
    ConversationRecord,
    EvaluatorResult,
    evaluate_scenario,
)
from services.eval_service._voice_result_collector import (
    VoiceCallMetrics,
    VoiceEvalResult,
)
from services.eval_service.schema import EvalScenario

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_scenario(**overrides: Any) -> EvalScenario:
    defaults: dict[str, Any] = {
        "scenario_id": "voice-int-1",
        "scenario": "Order a pizza by phone",
        "test_category": "voice",
        "persona": "standard_customer",
        "user_turns": ["Hello, I'd like to order a pizza", "Large pepperoni please"],
        "context": ["Menu: Pepperoni pizza $12, Margherita $10"],
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


def _make_voice_transcript() -> list[dict[str, str]]:
    """Timestamped voice transcript with speaker, start_time, end_time."""
    return [
        {
            "role": "assistant",
            "content": "Welcome to Joe's Pizza! How can I help you?",
            "speaker": "agent",
            "start_time": "0.0",
            "end_time": "2.5",
        },
        {
            "role": "user",
            "content": "Hello, I'd like to order a pizza",
            "speaker": "user",
            "start_time": "3.0",
            "end_time": "5.0",
        },
        {
            "role": "assistant",
            "content": "Sure! What kind of pizza would you like?",
            "speaker": "agent",
            "start_time": "5.5",
            "end_time": "7.5",
        },
        {
            "role": "user",
            "content": "Large pepperoni please",
            "speaker": "user",
            "start_time": "8.0",
            "end_time": "9.5",
        },
        {
            "role": "assistant",
            "content": "Great choice! A large pepperoni pizza. Can I get you anything else?",
            "speaker": "agent",
            "start_time": "10.0",
            "end_time": "13.0",
        },
    ]


def _make_voice_record(
    scenario: EvalScenario | None = None,
    voice_transcript: list[dict[str, str]] | None = None,
    turn_latencies_ms: list[float] | None = None,
    audio_recording_s3_uri: str | None = None,
) -> ConversationRecord:
    """Build a ConversationRecord as the voice pipeline would produce."""
    scenario = scenario or _make_scenario()
    transcript = voice_transcript or _make_voice_transcript()

    # Extract turns and agent_responses from voice transcript
    turns: list[dict[str, str]] = []
    agent_responses: list[str] = []
    current_user: str | None = None
    for msg in transcript:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            current_user = content
        elif role == "assistant":
            agent_responses.append(content)
            if current_user is not None:
                turns.append({"user": current_user, "assistant": content})
                current_user = None

    return ConversationRecord(
        scenario=scenario,
        turns=turns,
        agent_responses=agent_responses,
        voice_transcript=transcript,
        turn_latencies_ms=turn_latencies_ms or [800.0, 900.0],
        audio_recording_s3_uri=audio_recording_s3_uri,
        is_voice=True,
    )


# ---------------------------------------------------------------------------
# VoiceEvalResult.to_conversation_record
# ---------------------------------------------------------------------------


class TestVoiceEvalResultConversion:
    def test_populates_voice_fields(self) -> None:
        transcript = [
            {"role": "user", "content": "Hi", "speaker": "user"},
            {"role": "assistant", "content": "Hello!", "speaker": "agent"},
        ]
        result = VoiceEvalResult(
            call_id="call-1",
            room_name="room-1",
            transcript=transcript,
            metrics=VoiceCallMetrics(
                duration_seconds=30.0,
                turn_latency_avg=850.0,
            ),
            audio_recording_s3_uri="s3://bucket/recording.ogg",
        )
        scenario = _make_scenario()
        record = result.to_conversation_record(scenario)

        assert record.is_voice is True
        assert record.voice_transcript == transcript
        assert record.audio_recording_s3_uri == "s3://bucket/recording.ogg"
        assert len(record.turn_latencies_ms) > 0
        assert record.turns == [{"user": "Hi", "assistant": "Hello!"}]
        assert record.agent_responses == ["Hello!"]

    def test_no_latency_avg_gives_empty_list(self) -> None:
        result = VoiceEvalResult(
            call_id="call-2",
            room_name="room-2",
            transcript=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hey"},
            ],
            metrics=VoiceCallMetrics(duration_seconds=10.0),
        )
        record = result.to_conversation_record(_make_scenario())
        assert record.turn_latencies_ms == []

    def test_no_audio_uri_is_none(self) -> None:
        result = VoiceEvalResult(
            call_id="call-3",
            room_name="room-3",
        )
        record = result.to_conversation_record(_make_scenario())
        assert record.audio_recording_s3_uri is None
        assert record.is_voice is True


# ---------------------------------------------------------------------------
# evaluate_scenario — voice happy path
# ---------------------------------------------------------------------------

JUDGE_MODULE = "services.eval_service.evaluators.judge_adapter"
FIDELITY_MODULE = "services.eval_service.evaluators.speech_fidelity"


def _mock_evaluator(metric_name: str, score: float = 0.9) -> AsyncMock:
    return AsyncMock(
        return_value=EvaluatorResult(
            metric_name=metric_name,
            score=score,
            passed=True,
            reason=f"Mock {metric_name}",
        )
    )


class TestEvaluateScenarioVoiceHappyPath:
    """Full voice scenario with timestamped transcript, latencies, agent output."""

    @pytest.mark.asyncio
    async def test_runs_voice_evaluators(self) -> None:
        record = _make_voice_record()

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_evaluator("task_completion"),
            ),
            patch(
                f"{FIDELITY_MODULE}._create_speech_fidelity_metric"
            ) as mock_fidelity_metric,
        ):
            mock_metric = MagicMock()
            mock_metric.a_measure = AsyncMock()
            mock_metric.score = 0.85
            mock_metric.is_successful.return_value = True
            mock_metric.reason = "Good fidelity"
            mock_fidelity_metric.return_value = mock_metric

            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}

        # Judge evaluator
        assert "task_completion" in metric_names

        # Voice-specific evaluators
        assert "interruption" in metric_names
        assert "latency_silence" in metric_names
        assert "speech_rate" in metric_names
        assert "speech_fidelity" in metric_names

    @pytest.mark.asyncio
    async def test_voice_evaluator_scores_are_valid(self) -> None:
        record = _make_voice_record()

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_evaluator("task_completion"),
            ),
            patch(
                f"{FIDELITY_MODULE}._create_speech_fidelity_metric"
            ) as mock_fidelity_metric,
        ):
            mock_metric = MagicMock()
            mock_metric.a_measure = AsyncMock()
            mock_metric.score = 0.8
            mock_metric.is_successful.return_value = True
            mock_metric.reason = "OK"
            mock_fidelity_metric.return_value = mock_metric

            results = await evaluate_scenario(record)

        for r in results:
            assert (
                0.0 <= r.score <= 1.0
            ), f"{r.metric_name} score out of range: {r.score}"
            assert isinstance(r.passed, bool)
            assert isinstance(r.reason, str)


# ---------------------------------------------------------------------------
# evaluate_scenario — voice with interruptions
# ---------------------------------------------------------------------------


class TestEvaluateScenarioInterruption:
    """Voice scenario where overlapping speech triggers E14."""

    @pytest.mark.asyncio
    async def test_overlapping_speech_detected(self) -> None:
        transcript = [
            {
                "role": "assistant",
                "content": "Hello!",
                "speaker": "agent",
                "start_time": "0.0",
                "end_time": "2.0",
            },
            {
                "role": "user",
                "content": "Hi there",
                "speaker": "user",
                "start_time": "1.5",
                "end_time": "3.0",
            },
            {
                "role": "assistant",
                "content": "How can I help?",
                "speaker": "agent",
                "start_time": "3.5",
                "end_time": "5.0",
            },
        ]
        record = _make_voice_record(voice_transcript=transcript)

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_evaluator("task_completion"),
            ),
            patch(f"{FIDELITY_MODULE}._create_speech_fidelity_metric") as mock_fm,
        ):
            m = MagicMock()
            m.a_measure = AsyncMock()
            m.score = 0.8
            m.is_successful.return_value = True
            m.reason = "OK"
            mock_fm.return_value = m

            results = await evaluate_scenario(record)

        interruption_result = next(
            r for r in results if r.metric_name == "interruption"
        )
        # Turn 0 overlaps with turn 1 (end_time 2.0 > start_time 1.5)
        assert interruption_result.score < 1.0


# ---------------------------------------------------------------------------
# evaluate_scenario — voice with silence gaps
# ---------------------------------------------------------------------------


class TestEvaluateScenarioLongSilence:
    """Voice scenario with awkward silence gaps triggering E15."""

    @pytest.mark.asyncio
    async def test_silence_gap_detected(self) -> None:
        transcript = [
            {
                "role": "assistant",
                "content": "Hello!",
                "speaker": "agent",
                "start_time": "0.0",
                "end_time": "2.0",
            },
            {
                "role": "user",
                "content": "...",
                "speaker": "user",
                "start_time": "6.0",
                "end_time": "6.5",
            },
            {
                "role": "assistant",
                "content": "Still there?",
                "speaker": "agent",
                "start_time": "7.0",
                "end_time": "8.0",
            },
        ]
        record = _make_voice_record(
            voice_transcript=transcript,
            turn_latencies_ms=[500.0, 600.0],
        )

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_evaluator("task_completion"),
            ),
            patch(f"{FIDELITY_MODULE}._create_speech_fidelity_metric") as mock_fm,
        ):
            m = MagicMock()
            m.a_measure = AsyncMock()
            m.score = 0.8
            m.is_successful.return_value = True
            m.reason = "OK"
            mock_fm.return_value = m

            results = await evaluate_scenario(record)

        latency_result = next(r for r in results if r.metric_name == "latency_silence")
        # 4-second gap between agent end (2.0) and user start (6.0)
        assert latency_result.raw_output is not None
        assert latency_result.raw_output.get("silence_gap_count", 0) > 0


# ---------------------------------------------------------------------------
# evaluate_scenario — non-voice unchanged
# ---------------------------------------------------------------------------


class TestEvaluateScenarioNonVoice:
    """Text-based records should NOT trigger voice evaluators."""

    @pytest.mark.asyncio
    async def test_text_record_skips_voice_evaluators(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi!"},
                {"user": "Hours?", "assistant": "9 to 5."},
            ],
            agent_responses=["Hi!", "9 to 5."],
            is_voice=False,
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_evaluator("task_completion"),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "interruption" not in metric_names
        assert "latency_silence" not in metric_names
        assert "speech_rate" not in metric_names
        assert "speech_fidelity" not in metric_names
        assert "stt_accuracy" not in metric_names


# ---------------------------------------------------------------------------
# evaluate_scenario — voice with no audio URI skips STT
# ---------------------------------------------------------------------------


class TestEvaluateScenarioNoAudio:
    """Voice record without audio URI should skip E16 STT accuracy."""

    @pytest.mark.asyncio
    async def test_no_audio_skips_stt_accuracy(self) -> None:
        record = _make_voice_record(audio_recording_s3_uri=None)

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_evaluator("task_completion"),
            ),
            patch(f"{FIDELITY_MODULE}._create_speech_fidelity_metric") as mock_fm,
        ):
            m = MagicMock()
            m.a_measure = AsyncMock()
            m.score = 0.9
            m.is_successful.return_value = True
            m.reason = "OK"
            mock_fm.return_value = m

            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "stt_accuracy" not in metric_names
        # Other voice evaluators still run
        assert "interruption" in metric_names
        assert "speech_rate" in metric_names


# ---------------------------------------------------------------------------
# evaluate_scenario — voice with empty transcript
# ---------------------------------------------------------------------------


class TestEvaluateScenarioEmptyTranscript:
    """Voice record with empty transcript skips transcript-dependent evaluators."""

    @pytest.mark.asyncio
    async def test_empty_voice_transcript(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[],
            agent_responses=[],
            voice_transcript=[],
            turn_latencies_ms=[],
            is_voice=True,
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_evaluator("task_completion"),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        # task_completion always runs
        assert "task_completion" in metric_names
        # No data to evaluate — voice evaluators should be skipped
        assert "interruption" not in metric_names
        assert "latency_silence" not in metric_names
        assert "speech_rate" not in metric_names
        assert "speech_fidelity" not in metric_names
        assert "stt_accuracy" not in metric_names
