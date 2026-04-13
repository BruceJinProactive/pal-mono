"""Tests for E17b: Audio quality evaluator."""

from __future__ import annotations

import struct

from services.eval_service.evaluators.audio_quality import (
    _parse_wav_samples,
    detect_clipping_ratio,
    estimate_snr_db,
    evaluate_audio_quality,
)


def _make_wav(samples: list[int], sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Build a minimal 16-bit PCM WAV byte buffer from sample values."""
    num_samples = len(samples)
    data_size = num_samples * 2  # 16-bit = 2 bytes per sample
    byte_rate = sample_rate * channels * 2
    block_align = channels * 2

    header = struct.pack(
        "<4sI4s"  # RIFF header
        "4sIHHIIHH"  # fmt chunk
        "4sI",  # data chunk header
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        16,  # bits per sample
        b"data",
        data_size,
    )
    data = struct.pack(f"<{num_samples}h", *samples)
    return header + data


# ---------------------------------------------------------------------------
# _parse_wav_samples
# ---------------------------------------------------------------------------


class TestParseWavSamples:
    def test_valid_mono_wav(self) -> None:
        samples = [100, -200, 300, -400]
        wav = _make_wav(samples)
        parsed = _parse_wav_samples(wav)
        assert parsed == samples

    def test_too_short(self) -> None:
        assert _parse_wav_samples(b"short") is None

    def test_invalid_header(self) -> None:
        assert _parse_wav_samples(b"NOT_RIFF" + b"\x00" * 40) is None

    def test_empty_data(self) -> None:
        """WAV with 0 samples in data chunk."""
        wav = _make_wav([])
        assert _parse_wav_samples(wav) is None

    def test_stereo_takes_first_channel(self) -> None:
        # Interleaved stereo: L0, R0, L1, R1
        interleaved = [100, 200, 300, 400]
        wav = _make_wav(interleaved, channels=2)
        parsed = _parse_wav_samples(wav)
        # Should extract first channel: [100, 300]
        assert parsed == [100, 300]


# ---------------------------------------------------------------------------
# estimate_snr_db
# ---------------------------------------------------------------------------


class TestEstimateSnrDb:
    def test_too_few_samples(self) -> None:
        assert estimate_snr_db([0] * 100) is None

    def test_silence_returns_high_snr(self) -> None:
        """All-zero samples => noise floor ~0 => returns 60 dB sentinel."""
        samples = [0] * 16000 * 2  # 2 seconds at 16kHz
        snr = estimate_snr_db(samples)
        assert snr == 60.0

    def test_constant_tone_near_zero_snr(self) -> None:
        """A pure sine wave has near-constant frame RMS, so SNR ≈ 0 dB."""
        import math

        samples: list[int] = []
        for i in range(32000):
            val = int(10000 * math.sin(2 * math.pi * 440 * i / 16000))
            samples.append(val)
        snr = estimate_snr_db(samples)
        assert snr is not None
        # Constant-energy tone: top 10% and bottom 10% frames have similar
        # RMS, so SNR is near 0 dB (not indicative of noise — just no
        # dynamic range variation between frames).
        assert snr >= 0.0

    def test_noisy_signal_lower_snr(self) -> None:
        """Mix of loud and quiet frames gives measurable SNR."""
        import random

        random.seed(42)
        # Alternating loud and quiet frames
        samples: list[int] = []
        for frame_idx in range(20):
            amplitude = 10000 if frame_idx % 2 == 0 else 100
            for _ in range(1600):
                samples.append(random.randint(-amplitude, amplitude))
        snr = estimate_snr_db(samples)
        assert snr is not None
        assert snr > 0


# ---------------------------------------------------------------------------
# detect_clipping_ratio
# ---------------------------------------------------------------------------


class TestDetectClippingRatio:
    def test_no_clipping(self) -> None:
        samples = [100, -200, 300, -400, 500]
        assert detect_clipping_ratio(samples) == 0.0

    def test_all_clipped(self) -> None:
        max_val = 32767
        samples = [max_val, -max_val, max_val, -max_val]
        assert detect_clipping_ratio(samples) == 1.0

    def test_partial_clipping(self) -> None:
        max_val = 32767
        samples = [max_val, 0, 0, 0]  # 1 out of 4 clipped
        assert detect_clipping_ratio(samples) == 0.25

    def test_empty_samples(self) -> None:
        assert detect_clipping_ratio([]) == 0.0

    def test_near_max_counts_as_clipped(self) -> None:
        """Values at 99% of max are considered clipped."""
        threshold = int(32767 * 0.99)
        samples = [threshold, 0, 0, 0]
        assert detect_clipping_ratio(samples) == 0.25

    def test_just_below_threshold(self) -> None:
        """Values just below the clip threshold are not clipped."""
        threshold = int(32767 * 0.99)
        samples = [threshold - 1, 0, 0, 0]
        assert detect_clipping_ratio(samples) == 0.0


# ---------------------------------------------------------------------------
# evaluate_audio_quality — orchestrator
# ---------------------------------------------------------------------------


class TestEvaluateAudioQuality:
    def test_unparseable_bytes(self) -> None:
        result = evaluate_audio_quality(b"not-a-wav-file")
        assert result.score == 1.0
        assert result.passed is True
        assert "non-computable" in result.reason

    def test_clean_audio(self) -> None:
        """Normal amplitude samples, no clipping."""
        samples = [1000, -1000, 500, -500] * 8000  # 32000 samples = 2s
        wav = _make_wav(samples)
        result = evaluate_audio_quality(wav)
        assert result.raw_output is not None
        assert result.raw_output["clipping_ratio"] == 0.0
        assert result.raw_output["clipping_score"] == 1.0

    def test_heavily_clipped_audio(self) -> None:
        """All samples at max => high clipping ratio."""
        max_val = 32767
        samples = [max_val, -max_val] * 16000
        wav = _make_wav(samples)
        result = evaluate_audio_quality(wav)
        assert result.raw_output is not None
        assert result.raw_output["clipping_ratio"] == 1.0
        assert result.raw_output["clipping_score"] == 0.0
        assert result.passed is False

    def test_short_audio_no_snr(self) -> None:
        """Too few samples for SNR estimation — clipping-only score."""
        samples = [100, -100, 200, -200]
        wav = _make_wav(samples)
        result = evaluate_audio_quality(wav)
        assert result.raw_output is not None
        # SNR should not be computed
        assert "snr_db" not in result.raw_output
        # Clipping score alone determines the result
        assert result.raw_output["clipping_score"] == 1.0
        assert result.score == 1.0

    def test_raw_output_fields(self) -> None:
        """Verify raw_output contains expected fields for long audio."""
        samples = [5000, -5000, 100, -100] * 8000
        wav = _make_wav(samples)
        result = evaluate_audio_quality(wav)
        assert result.raw_output is not None
        assert "sample_count" in result.raw_output
        assert "clipping_ratio" in result.raw_output
        assert "clipping_score" in result.raw_output

    def test_metric_name(self) -> None:
        result = evaluate_audio_quality(b"bad")
        assert result.metric_name == "audio_quality"

    def test_moderate_clipping_partial_score(self) -> None:
        """~3% clipping should give a partial clipping score."""
        max_val = 32767
        # 3% clipped: 960 clipped out of 32000
        normal = [1000] * 31040
        clipped = [max_val] * 960
        samples = normal + clipped
        wav = _make_wav(samples)
        result = evaluate_audio_quality(wav)
        assert result.raw_output is not None
        assert 0.0 < result.raw_output["clipping_score"] < 1.0
