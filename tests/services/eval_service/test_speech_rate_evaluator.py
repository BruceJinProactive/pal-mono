"""Tests for E17: Speech rate evaluator."""

from __future__ import annotations

from typing import Any

from services.eval_service.evaluators.speech_rate import (
    compute_turn_wpm,
    evaluate_speech_rate,
)


def _turn(
    speaker: str,
    text: str,
    start: float,
    end: float,
) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "text": text,
        "start_time": start,
        "end_time": end,
    }


# ---------------------------------------------------------------------------
# compute_turn_wpm
# ---------------------------------------------------------------------------


class TestComputeTurnWpm:
    def test_normal_rate(self) -> None:
        # 30 words in 12 seconds = 150 WPM
        text = " ".join(["word"] * 30)
        assert compute_turn_wpm(text, 12.0) == 150.0

    def test_exactly_120_wpm(self) -> None:
        text = " ".join(["word"] * 20)
        wpm = compute_turn_wpm(text, 10.0)
        assert wpm == 120.0

    def test_short_duration_returns_none(self) -> None:
        assert compute_turn_wpm("hello world", 0.3) is None

    def test_zero_duration_returns_none(self) -> None:
        assert compute_turn_wpm("hello", 0.0) is None

    def test_empty_text_returns_none(self) -> None:
        assert compute_turn_wpm("", 5.0) is None

    def test_one_word_half_second(self) -> None:
        wpm = compute_turn_wpm("hello", 0.5)
        assert wpm == 120.0


# ---------------------------------------------------------------------------
# evaluate_speech_rate
# ---------------------------------------------------------------------------


class TestEvaluateSpeechRate:
    def test_no_transcript(self) -> None:
        result = evaluate_speech_rate([])
        assert result.score == 1.0
        assert result.passed is True
        assert "No measurable" in result.reason

    def test_no_agent_turns(self) -> None:
        transcript = [
            _turn("user", "Hello there how are you", 0.0, 3.0),
            _turn("user", "I want a pizza please", 4.0, 7.0),
        ]
        result = evaluate_speech_rate(transcript, speaker="assistant")
        assert result.score == 1.0
        assert "No measurable" in result.reason

    def test_turns_without_timestamps(self) -> None:
        transcript = [{"speaker": "assistant", "text": "Hello world"}]
        result = evaluate_speech_rate(transcript)
        assert result.score == 1.0
        assert "No measurable" in result.reason

    def test_all_turns_in_range(self) -> None:
        # 25 words in 10s = 150 WPM (in 120-180 range)
        text = " ".join(["word"] * 25)
        transcript = [
            _turn("assistant", text, 0.0, 10.0),
            _turn("user", "ok", 10.5, 11.0),
            _turn("assistant", text, 11.5, 21.5),
        ]
        result = evaluate_speech_rate(transcript)
        assert result.score == 1.0
        assert result.passed is True
        assert result.raw_output is not None
        assert result.raw_output["in_range_count"] == 2
        assert result.raw_output["total_measured"] == 2

    def test_all_turns_too_fast(self) -> None:
        # 40 words in 10s = 240 WPM (above 180)
        text = " ".join(["word"] * 40)
        transcript = [
            _turn("assistant", text, 0.0, 10.0),
            _turn("assistant", text, 11.0, 21.0),
        ]
        result = evaluate_speech_rate(transcript)
        assert result.score == 0.0
        assert result.passed is False

    def test_all_turns_too_slow(self) -> None:
        # 10 words in 10s = 60 WPM (below 120)
        text = " ".join(["word"] * 10)
        transcript = [
            _turn("assistant", text, 0.0, 10.0),
            _turn("assistant", text, 11.0, 21.0),
        ]
        result = evaluate_speech_rate(transcript)
        assert result.score == 0.0
        assert result.passed is False

    def test_mixed_in_and_out_of_range(self) -> None:
        good_text = " ".join(["word"] * 25)  # 25 words in 10s = 150 WPM
        fast_text = " ".join(["word"] * 40)  # 40 words in 10s = 240 WPM
        transcript = [
            _turn("assistant", good_text, 0.0, 10.0),
            _turn("user", "ok", 10.5, 11.0),
            _turn("assistant", fast_text, 11.5, 21.5),
            _turn("user", "thanks", 22.0, 22.5),
            _turn("assistant", good_text, 23.0, 33.0),
        ]
        result = evaluate_speech_rate(transcript)
        # 2 in range, 1 out of 3 total => score = 2/3
        assert result.raw_output is not None
        assert result.raw_output["in_range_count"] == 2
        assert result.raw_output["total_measured"] == 3
        assert result.score > 0.6
        assert result.score < 0.7

    def test_role_field_supported(self) -> None:
        text = " ".join(["word"] * 25)
        transcript = [
            {"role": "assistant", "content": text, "start_time": 0.0, "end_time": 10.0},
        ]
        result = evaluate_speech_rate(transcript)
        assert result.raw_output is not None
        assert result.raw_output["total_measured"] == 1

    def test_custom_speaker(self) -> None:
        text = " ".join(["word"] * 25)
        transcript = [
            _turn("agent", text, 0.0, 10.0),
            _turn("user", text, 11.0, 21.0),
        ]
        result = evaluate_speech_rate(transcript, speaker="agent")
        assert result.raw_output is not None
        assert result.raw_output["total_measured"] == 1

    def test_short_turns_skipped(self) -> None:
        """Turns < 0.5s are skipped as unreliable."""
        transcript = [
            _turn("assistant", "hi", 0.0, 0.3),
        ]
        result = evaluate_speech_rate(transcript)
        assert result.score == 1.0
        assert "No measurable" in result.reason

    def test_raw_output_structure(self) -> None:
        text = " ".join(["word"] * 20)
        transcript = [_turn("assistant", text, 0.0, 10.0)]
        result = evaluate_speech_rate(transcript)
        assert result.raw_output is not None
        assert "avg_wpm" in result.raw_output
        assert "in_range_count" in result.raw_output
        assert "total_measured" in result.raw_output
        assert "turns" in result.raw_output
        assert len(result.raw_output["turns"]) == 1
        turn = result.raw_output["turns"][0]
        assert "wpm" in turn
        assert "duration_s" in turn
        assert "word_count" in turn
        assert "in_range" in turn

    def test_boundary_120_wpm(self) -> None:
        # Exactly 120 WPM: 20 words in 10s
        text = " ".join(["word"] * 20)
        transcript = [_turn("assistant", text, 0.0, 10.0)]
        result = evaluate_speech_rate(transcript)
        assert result.score == 1.0

    def test_boundary_180_wpm(self) -> None:
        # Exactly 180 WPM: 30 words in 10s
        text = " ".join(["word"] * 30)
        transcript = [_turn("assistant", text, 0.0, 10.0)]
        result = evaluate_speech_rate(transcript)
        assert result.score == 1.0

    def test_passed_threshold(self) -> None:
        """Score >= 0.7 passes, < 0.7 fails."""
        # 2/3 in range = 0.6667 => fails
        good_text = " ".join(["word"] * 25)  # 150 WPM
        bad_text = " ".join(["word"] * 50)  # 300 WPM
        transcript = [
            _turn("assistant", good_text, 0.0, 10.0),
            _turn("assistant", good_text, 11.0, 21.0),
            _turn("assistant", bad_text, 22.0, 32.0),
        ]
        result = evaluate_speech_rate(transcript)
        assert result.passed is False
