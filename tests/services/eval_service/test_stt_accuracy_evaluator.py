"""Tests for E16: STT accuracy / WER evaluator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service.evaluators.stt_accuracy import (
    _normalise_text,
    _parse_s3_uri,
    compute_wer,
    evaluate_stt_accuracy,
    extract_primary_transcript,
)

# ---------------------------------------------------------------------------
# compute_wer — pure unit tests
# ---------------------------------------------------------------------------


class TestComputeWer:
    def test_identical_transcripts(self) -> None:
        result = compute_wer("hello world", "hello world")
        assert result["wer"] == 0.0
        assert result["substitutions"] == 0
        assert result["insertions"] == 0
        assert result["deletions"] == 0
        assert result["ref_words"] == 2

    def test_completely_different(self) -> None:
        result = compute_wer("hello world", "foo bar")
        assert result["wer"] == 1.0  # 2 substitutions / 2 words
        assert result["substitutions"] == 2

    def test_insertion(self) -> None:
        result = compute_wer("hello world", "hello big world")
        assert result["wer"] == 0.5  # 1 insertion / 2 words
        assert result["insertions"] == 1

    def test_deletion(self) -> None:
        result = compute_wer("hello big world", "hello world")
        assert result["wer"] == pytest.approx(1 / 3, abs=0.001)
        assert result["deletions"] == 1

    def test_substitution(self) -> None:
        result = compute_wer("hello world", "hello earth")
        assert result["wer"] == 0.5
        assert result["substitutions"] == 1

    def test_empty_reference_empty_hypothesis(self) -> None:
        result = compute_wer("", "")
        assert result["wer"] == 0.0
        assert result["ref_words"] == 0

    def test_empty_reference_nonempty_hypothesis(self) -> None:
        result = compute_wer("", "hello world")
        assert result["wer"] == 2.0  # 2 insertions / 0 ref words → float(m)
        assert result["insertions"] == 2

    def test_nonempty_reference_empty_hypothesis(self) -> None:
        result = compute_wer("hello world", "")
        assert result["wer"] == 1.0  # 2 deletions / 2 words
        assert result["deletions"] == 2

    def test_punctuation_ignored(self) -> None:
        result = compute_wer("Hello, world!", "hello world")
        assert result["wer"] == 0.0

    def test_case_insensitive(self) -> None:
        result = compute_wer("HELLO WORLD", "hello world")
        assert result["wer"] == 0.0

    def test_realistic_stt_errors(self) -> None:
        ref = "I would like a large pepperoni pizza"
        hyp = "I would like a large pepperoni pete's a"
        result = compute_wer(ref, hyp)
        assert result["wer"] > 0.0
        assert result["ref_words"] == 7


# ---------------------------------------------------------------------------
# _normalise_text
# ---------------------------------------------------------------------------


class TestNormaliseText:
    def test_basic(self) -> None:
        assert _normalise_text("Hello, World!") == ["hello", "world"]

    def test_empty(self) -> None:
        assert _normalise_text("") == []

    def test_numbers_preserved(self) -> None:
        assert _normalise_text("Order 123") == ["order", "123"]


# ---------------------------------------------------------------------------
# _parse_s3_uri
# ---------------------------------------------------------------------------


class TestParseS3Uri:
    def test_valid_uri(self) -> None:
        bucket, key = _parse_s3_uri("s3://my-bucket/path/to/file.ogg")
        assert bucket == "my-bucket"
        assert key == "path/to/file.ogg"

    def test_invalid_uri_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            _parse_s3_uri("https://example.com/file.ogg")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            _parse_s3_uri("")


# ---------------------------------------------------------------------------
# extract_primary_transcript
# ---------------------------------------------------------------------------


class TestExtractPrimaryTranscript:
    def test_speaker_field(self) -> None:
        transcript = [
            {"speaker": "agent", "text": "Hello"},
            {"speaker": "user", "text": "I want pizza"},
            {"speaker": "agent", "text": "Sure"},
            {"speaker": "user", "text": "Large please"},
        ]
        result = extract_primary_transcript(transcript, speaker="user")
        assert result == "I want pizza Large please"

    def test_role_field(self) -> None:
        transcript = [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Pizza please"},
        ]
        result = extract_primary_transcript(transcript, speaker="user")
        assert result == "Pizza please"

    def test_empty_transcript(self) -> None:
        assert extract_primary_transcript([]) == ""

    def test_no_matching_speaker(self) -> None:
        transcript = [{"speaker": "agent", "text": "Hello"}]
        assert extract_primary_transcript(transcript, speaker="user") == ""

    def test_mixed_fields(self) -> None:
        transcript = [
            {"speaker": "user", "text": "First"},
            {"role": "user", "content": "Second"},
        ]
        result = extract_primary_transcript(transcript, speaker="user")
        assert result == "First Second"


# ---------------------------------------------------------------------------
# evaluate_stt_accuracy — async orchestrator
# ---------------------------------------------------------------------------


class TestEvaluateSttAccuracy:
    @pytest.mark.asyncio
    async def test_no_audio_uri(self) -> None:
        result = await evaluate_stt_accuracy("", "hello world")
        assert result.metric_name == "stt_accuracy"
        assert result.score == 1.0
        assert result.passed is True
        assert "No audio recording" in result.reason

    @pytest.mark.asyncio
    async def test_no_primary_transcript(self) -> None:
        result = await evaluate_stt_accuracy("s3://bucket/key.ogg", "")
        assert result.score == 1.0
        assert "No primary transcript" in result.reason

    @pytest.mark.asyncio
    async def test_whitespace_only_transcript(self) -> None:
        result = await evaluate_stt_accuracy("s3://bucket/key.ogg", "   ")
        assert result.score == 1.0
        assert "No primary transcript" in result.reason

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._transcribe_with_whisper")
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_perfect_match(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
        mock_whisper: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = (b"fake-wav-bytes", "audio.wav")
        mock_whisper.return_value = "hello world"

        result = await evaluate_stt_accuracy(
            "s3://bucket/recording.ogg",
            "hello world",
        )
        assert result.score == 1.0
        assert result.passed is True
        assert "WER=0.00%" in result.reason

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._transcribe_with_whisper")
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_high_wer_fails(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
        mock_whisper: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = (b"fake-wav-bytes", "audio.wav")
        mock_whisper.return_value = "I want a large pepperoni pizza"

        result = await evaluate_stt_accuracy(
            "s3://bucket/recording.ogg",
            "I want a large pepperdine peeza",  # 2 substitutions out of 7
        )
        assert result.passed is False
        assert result.score < 1.0
        assert "WER=" in result.reason
        assert result.raw_output is not None
        assert result.raw_output["substitutions"] > 0

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._transcribe_with_whisper")
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_low_wer_passes(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
        mock_whisper: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = (b"fake-wav-bytes", "audio.wav")
        # 1 word different out of 20 = 5% WER < 8% threshold
        words = "the quick brown fox jumps over the lazy dog near the river bank on a sunny afternoon in the park"
        hyp = "the quick brown fox jumps over the lazy dog near the river bank on a sunny afternoon in the dark"
        mock_whisper.return_value = words

        result = await evaluate_stt_accuracy("s3://bucket/recording.ogg", hyp)
        assert result.passed is True
        assert result.score > 0.9

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._transcribe_with_whisper")
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_empty_whisper_result(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
        mock_whisper: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = (b"fake-wav-bytes", "audio.wav")
        mock_whisper.return_value = ""

        result = await evaluate_stt_accuracy("s3://bucket/recording.ogg", "hello")
        assert result.score == 1.0
        assert "empty transcription" in result.reason

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_extraction_failure_returns_non_computable(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = None  # ffmpeg failed

        result = await evaluate_stt_accuracy("s3://bucket/recording.ogg", "hello")
        assert result.score == 1.0
        assert result.passed is True
        assert "caller channel" in result.reason

    @pytest.mark.asyncio
    @patch(
        "services.eval_service.evaluators.stt_accuracy._download_audio_from_s3",
        side_effect=Exception("S3 connection error"),
    )
    async def test_s3_error_handled(self, mock_download: AsyncMock) -> None:
        result = await evaluate_stt_accuracy("s3://bucket/recording.ogg", "hello")
        assert result.score == 0.0
        assert result.passed is False
        assert "failed" in result.reason

    @pytest.mark.asyncio
    @patch("services.eval_service.evaluators.stt_accuracy._transcribe_with_whisper")
    @patch("services.eval_service.evaluators.stt_accuracy._download_audio_from_s3")
    @patch(
        "services.eval_service.evaluators.stt_accuracy.extract_right_channel_wav",
    )
    async def test_raw_output_contains_wer_details(
        self,
        mock_extract: MagicMock,
        mock_download: AsyncMock,
        mock_whisper: AsyncMock,
    ) -> None:
        mock_download.return_value = b"fake-ogg-bytes"
        mock_extract.return_value = (b"fake-wav-bytes", "audio.wav")
        mock_whisper.return_value = "hello world foo"

        result = await evaluate_stt_accuracy(
            "s3://bucket/recording.ogg",
            "hello world bar",
        )
        assert result.raw_output is not None
        assert "wer" in result.raw_output
        assert "substitutions" in result.raw_output
        assert "insertions" in result.raw_output
        assert "deletions" in result.raw_output
        assert "ref_words" in result.raw_output
