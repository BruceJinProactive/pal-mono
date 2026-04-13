"""E17b: Audio quality evaluator.

Basic signal-level quality metrics computed from raw audio bytes:

- **SNR estimation**: Signal-to-noise ratio via RMS of signal vs. silent
  segments.
- **Clipping detection**: Ratio of samples at or near the maximum amplitude.

No LLM needed — pure signal processing on PCM data.
"""

from __future__ import annotations

import struct
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

# Thresholds
_MIN_SNR_DB = 15.0  # Minimum acceptable SNR in dB
_MAX_CLIPPING_RATIO = 0.01  # At most 1% of samples may be clipped

# A sample is considered "clipped" when its absolute value reaches this
# fraction of the maximum 16-bit PCM amplitude (32767).
_CLIP_THRESHOLD_FRACTION = 0.99


def _parse_wav_samples(wav_bytes: bytes) -> list[int] | None:
    """Extract 16-bit PCM samples from a WAV byte buffer.

    Handles only the common case: mono/stereo, 16-bit PCM (format tag 1).
    Returns ``None`` if the format is unsupported or the data is too short.
    """
    if len(wav_bytes) < 44:
        return None

    # RIFF header validation
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        return None

    # fmt chunk — audio format must be PCM (1)
    audio_format = struct.unpack_from("<H", wav_bytes, 20)[0]
    if audio_format != 1:
        return None

    num_channels = struct.unpack_from("<H", wav_bytes, 22)[0]
    if num_channels == 0:
        return None
    bits_per_sample = struct.unpack_from("<H", wav_bytes, 34)[0]
    if bits_per_sample != 16:
        return None

    # Find the "data" sub-chunk
    offset = 12
    while offset + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", wav_bytes, offset + 4)[0]
        if chunk_id == b"data":
            data_start = offset + 8
            data_end = min(data_start + chunk_size, len(wav_bytes))
            raw = wav_bytes[data_start:data_end]
            # Decode interleaved 16-bit signed samples
            n_samples = len(raw) // 2
            if n_samples == 0:
                return None
            samples = list(struct.unpack_from(f"<{n_samples}h", raw))
            # For stereo, take every Nth sample (first channel)
            if num_channels > 1:
                samples = samples[::num_channels]
            return samples
        offset += 8 + chunk_size
        # Chunks are word-aligned
        if chunk_size % 2 != 0:
            offset += 1

    return None


def estimate_snr_db(samples: list[int], frame_size: int = 1600) -> float | None:
    """Estimate signal-to-noise ratio in dB.

    Splits the audio into frames of *frame_size* samples.  The quietest
    10% of frames approximate noise; the loudest 10% approximate signal.
    SNR = 20 * log10(rms_signal / rms_noise).

    Returns ``None`` when there are too few frames.  When the noise floor
    is effectively zero (synthetic silence), returns 60.0 dB as a sentinel
    for clean audio.
    """
    import math

    if len(samples) < frame_size * 10:
        return None

    frame_rms: list[float] = []
    for start in range(0, len(samples) - frame_size + 1, frame_size):
        frame = samples[start : start + frame_size]
        rms = math.sqrt(sum(s * s for s in frame) / len(frame))
        frame_rms.append(rms)

    if len(frame_rms) < 10:
        return None

    frame_rms.sort()
    n = len(frame_rms)
    bottom_10 = max(1, n // 10)
    top_10 = max(1, n // 10)

    noise_rms = sum(frame_rms[:bottom_10]) / bottom_10
    signal_rms = sum(frame_rms[-top_10:]) / top_10

    if noise_rms < 1.0:
        # Noise floor is effectively zero — can't compute meaningful SNR.
        # Return a high value to indicate clean audio.
        return 60.0

    return 20.0 * math.log10(signal_rms / noise_rms)


def detect_clipping_ratio(samples: list[int]) -> float:
    """Return the fraction of samples that are clipped.

    A sample is clipped when its absolute value is >= 99% of the 16-bit
    maximum (32767).
    """
    if not samples:
        return 0.0

    threshold = int(32767 * _CLIP_THRESHOLD_FRACTION)
    clipped = sum(1 for s in samples if abs(s) >= threshold)
    return clipped / len(samples)


def evaluate_audio_quality(
    wav_bytes: bytes,
) -> EvaluatorResult:
    """Score audio quality from a WAV byte buffer.

    Sub-scores:
        - SNR: 1.0 if >= 15 dB, linearly degrades to 0.0 at 0 dB
        - Clipping: 1.0 if <= 1% clipped, linearly degrades to 0.0 at 5%

    Final score = ``0.6 * snr_score + 0.4 * clipping_score``.

    Args:
        wav_bytes: Raw WAV file bytes (16-bit PCM).

    Returns:
        EvaluatorResult with composite score and detailed breakdown.
    """
    samples = _parse_wav_samples(wav_bytes)
    if samples is None:
        return EvaluatorResult(
            metric_name="audio_quality",
            score=1.0,
            passed=True,
            reason="Could not parse audio — audio quality non-computable",
        )

    raw: dict[str, Any] = {"sample_count": len(samples)}
    parts: list[str] = []
    snr_score: float | None = None
    clipping_score: float | None = None

    # --- SNR sub-score ---
    snr_db = estimate_snr_db(samples)
    if snr_db is not None:
        raw["snr_db"] = round(snr_db, 1)
        # 1.0 at >= _MIN_SNR_DB, linearly to 0.0 at 0 dB
        snr_score = max(0.0, min(1.0, snr_db / _MIN_SNR_DB))
        raw["snr_score"] = round(snr_score, 3)
        parts.append(f"SNR={snr_db:.1f}dB (sub-score={snr_score:.2f})")

    # --- Clipping sub-score ---
    clip_ratio = detect_clipping_ratio(samples)
    raw["clipping_ratio"] = round(clip_ratio, 6)
    # 1.0 at <= _MAX_CLIPPING_RATIO, linearly to 0.0 at 5%
    max_degrade = 0.05  # 5% clipping = score 0
    if clip_ratio <= _MAX_CLIPPING_RATIO:
        clipping_score = 1.0
    else:
        clipping_score = max(
            0.0,
            1.0
            - (clip_ratio - _MAX_CLIPPING_RATIO) / (max_degrade - _MAX_CLIPPING_RATIO),
        )
    raw["clipping_score"] = round(clipping_score, 3)
    parts.append(f"Clipping={clip_ratio:.4%} (sub-score={clipping_score:.2f})")

    # --- Composite ---
    if snr_score is not None:
        score = 0.6 * snr_score + 0.4 * clipping_score
    else:
        score = clipping_score

    return EvaluatorResult(
        metric_name="audio_quality",
        score=round(score, 4),
        passed=score >= 0.7,
        reason=" | ".join(parts),
        raw_output=raw,
    )
