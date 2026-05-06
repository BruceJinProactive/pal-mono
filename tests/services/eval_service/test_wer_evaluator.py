"""Tests for E19: WER evaluator adapter."""

from __future__ import annotations

from typing import Any

import pytest

from services.eval_service.evaluators.wer import evaluate_wer


def _transcript_entry(
    speaker: str,
    text: str,
    start_time: float = 0.0,
    end_time: float = 0.0,
) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "text": text,
        "start_time": start_time,
        "end_time": end_time,
    }


class TestEvaluateWer:
    @pytest.mark.asyncio
    async def test_perfect_match(self) -> None:
        """Score should be 1.0 when STT perfectly matches ground truth."""
        ground_truth = ["hello how are you", "I would like to order"]
        transcript = [
            _transcript_entry("user", "hello how are you"),
            _transcript_entry("assistant", "I am doing great"),
            _transcript_entry("user", "I would like to order"),
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score == 1.0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_partial_mismatch(self) -> None:
        """Score should reflect WER when STT partially mismatches."""
        ground_truth = ["hello how are you today"]
        transcript = [
            _transcript_entry("user", "hello how you today"),
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score is not None
        assert 0.0 < result.score < 1.0
        assert result.raw_output is not None
        assert result.raw_output["average_wer"] > 0.0

    @pytest.mark.asyncio
    async def test_empty_ground_truth(self) -> None:
        """Should return error result when no ground truth provided."""
        transcript = [_transcript_entry("user", "hello")]

        result = await evaluate_wer([], transcript)

        assert result.metric_name == "wer"
        assert "ground_truth_texts" in (result.reason or "").lower()

    @pytest.mark.asyncio
    async def test_no_user_entries(self) -> None:
        """Should return 0 score when no user entries in transcript."""
        ground_truth = ["hello"]
        transcript = [
            _transcript_entry("assistant", "how can I help you"),
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score == 0.0
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_total_mismatch(self) -> None:
        """Score should be low when STT output is completely wrong."""
        ground_truth = ["hello how are you doing today"]
        transcript = [
            _transcript_entry("user", "xyz abc def ghi jkl"),
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score is not None
        assert result.score < 0.5
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_invalid_timestamps_handled(self) -> None:
        """Should not crash on invalid timestamp values."""
        ground_truth = ["test phrase"]
        transcript = [
            {
                "speaker": "user",
                "text": "test phrase",
                "start_time": "invalid",
                "end_time": None,
            },
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_role_key_fallback(self) -> None:
        """Should support 'role' key as fallback for 'speaker'."""
        ground_truth = ["hello world"]
        transcript = [
            {"role": "user", "content": "hello world", "start_time": 0, "end_time": 1},
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_multiple_turns_alignment(self) -> None:
        """Should align turns correctly when counts differ."""
        ground_truth = ["first turn", "second turn", "third turn"]
        transcript = [
            _transcript_entry("user", "first turn"),
            _transcript_entry("assistant", "response"),
            _transcript_entry("user", "second turn"),
            # Only 2 user turns vs 3 ground truth — should compare min(2, 3)
        ]

        result = await evaluate_wer(ground_truth, transcript)

        assert result.metric_name == "wer"
        assert result.score == 1.0  # Both matched turns are perfect
        assert result.raw_output is not None
        assert result.raw_output["num_turns_compared"] == 2
