"""E16: STT accuracy / Word Error Rate evaluator.

Compares the primary STT transcript (Deepgram/Gladia produced during the call)
against a reference transcription (OpenAI Whisper) to compute Word Error Rate.

Pipeline:
    1. Download dual-channel audio from S3
    2. Extract caller channel (right channel for DUAL_CHANNEL_AGENT recordings)
    3. Re-transcribe caller audio with Whisper (reference)
    4. Normalise both transcripts and compute WER via edit distance

No LLM needed — pure signal processing + Whisper API call.
"""

from __future__ import annotations

import io
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from services.eval_service._evaluators import EvaluatorResult
from utils.log import logger

# WER threshold: calls with WER above this fail
_WER_THRESHOLD = 0.08  # 8% — aligned with phase-2 proposal target


# ---------------------------------------------------------------------------
# Pure WER computation (no I/O)
# ---------------------------------------------------------------------------


def _normalise_text(text: str) -> list[str]:
    """Lowercase, strip punctuation, and tokenise into words."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.split()


def compute_wer(reference: str, hypothesis: str) -> dict[str, Any]:
    """Compute Word Error Rate between *reference* and *hypothesis*.

    Uses the standard Levenshtein edit-distance algorithm at the word level.

    Returns a dict with:
        wer: float in [0, ∞) — 0.0 is perfect
        substitutions, insertions, deletions: int counts
        ref_words: int — total words in reference
    """
    ref_words = _normalise_text(reference)
    hyp_words = _normalise_text(hypothesis)

    n = len(ref_words)
    m = len(hyp_words)

    if n == 0:
        return {
            "wer": 0.0 if m == 0 else float(m),
            "substitutions": 0,
            "insertions": m,
            "deletions": 0,
            "ref_words": 0,
        }

    # DP matrix: d[i][j] = edit distance between ref[:i] and hyp[:j]
    d: list[list[int]] = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(
                    d[i - 1][j - 1],  # substitution
                    d[i - 1][j],  # deletion
                    d[i][j - 1],  # insertion
                )

    # Backtrace to count S, I, D
    i, j = n, m
    subs, ins, dels = 0, 0, 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i - 1] == hyp_words[j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
        elif j > 0 and d[i][j] == d[i][j - 1] + 1:
            ins += 1
            j -= 1
        else:
            dels += 1
            i -= 1

    wer = d[n][m] / n

    return {
        "wer": wer,
        "substitutions": subs,
        "insertions": ins,
        "deletions": dels,
        "ref_words": n,
    }


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

_S3_URI_PATTERN = re.compile(r"^s3://([^/]+)/(.+)$")


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse ``s3://bucket/key`` into (bucket, key).

    Raises ValueError if the URI is malformed.
    """
    match = _S3_URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid S3 URI: {uri!r}")
    return match.group(1), match.group(2)


def extract_right_channel_wav(ogg_bytes: bytes) -> tuple[bytes, str] | None:
    """Extract the right channel from stereo audio and return as WAV bytes.

    For DUAL_CHANNEL_AGENT recordings the layout is:
        Left  = agent audio
        Right = caller audio

    Uses ffmpeg for OGG decoding and channel extraction. Returns ``None``
    if extraction fails (ffmpeg unavailable or error) — callers should
    treat this as non-computable rather than transcribing mixed audio.

    Returns:
        Tuple of (audio_bytes, filename) on success, or ``None`` on failure.
    """
    import subprocess

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_in:
        tmp_in.write(ogg_bytes)
        tmp_in_path = Path(tmp_in.name)

    tmp_out_path = tmp_in_path.with_suffix(".wav")

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(tmp_in_path),
                "-af",
                "pan=mono|c0=c1",  # extract right channel
                "-ar",
                "16000",  # 16kHz for Whisper
                "-ac",
                "1",
                "-f",
                "wav",
                str(tmp_out_path),
                "-y",
                "-loglevel",
                "error",
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning(
                "ffmpeg channel extraction failed: %s",
                result.stderr.decode(errors="replace")[:200],
            )
            return None

        return tmp_out_path.read_bytes(), "audio.wav"
    except FileNotFoundError:
        logger.warning("ffmpeg not found, cannot extract caller channel")
        return None
    finally:
        tmp_in_path.unlink(missing_ok=True)
        tmp_out_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Transcript extraction from conversation
# ---------------------------------------------------------------------------


def extract_primary_transcript(
    transcript: Sequence[dict[str, Any]],
    speaker: str = "user",
) -> str:
    """Join all entries from *speaker* into a single text string.

    This represents the primary STT output (Deepgram/Gladia) for the caller.
    """
    parts: list[str] = []
    for entry in transcript:
        if entry.get("speaker") == speaker or entry.get("role") == speaker:
            text = entry.get("text") or entry.get("content") or ""
            if text:
                parts.append(str(text))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Async orchestrator
# ---------------------------------------------------------------------------


async def _download_audio_from_s3(s3_uri: str) -> bytes:
    """Download audio bytes from an S3 URI."""
    from starlette.concurrency import run_in_threadpool

    from services.asset_service._utils import init_s3

    bucket, key = _parse_s3_uri(s3_uri)
    s3_client = init_s3("us-east-1")

    response = await run_in_threadpool(
        s3_client.get_object,
        Bucket=bucket,
        Key=key,
    )
    try:
        body: bytes = await run_in_threadpool(response["Body"].read)
    finally:
        await run_in_threadpool(response["Body"].close)
    return body


async def _transcribe_with_whisper(
    audio_bytes: bytes, filename: str = "audio.wav"
) -> str:
    """Transcribe audio bytes using OpenAI Whisper API."""
    import openai

    async with openai.AsyncOpenAI() as client:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )
        return transcription.text


async def evaluate_stt_accuracy(
    audio_s3_uri: str,
    primary_transcript: str,
) -> EvaluatorResult:
    """E16: Compare primary STT output against Whisper reference.

    Pipeline:
        1. Download audio from S3
        2. Extract caller channel (right channel of stereo recording)
        3. Transcribe with Whisper as ground-truth reference
        4. Compute WER between primary STT and Whisper reference

    Args:
        audio_s3_uri: S3 URI of the dual-channel call recording.
        primary_transcript: The concatenated primary STT text for the caller.

    Returns:
        EvaluatorResult with WER score (inverted: 1.0 - WER for [0,1] scoring).
    """
    if not audio_s3_uri:
        return EvaluatorResult(
            metric_name="stt_accuracy",
            score=1.0,
            passed=True,
            reason="No audio recording available for STT accuracy evaluation",
        )

    if not primary_transcript.strip():
        return EvaluatorResult(
            metric_name="stt_accuracy",
            score=1.0,
            passed=True,
            reason="No primary transcript to compare against",
        )

    try:
        audio_bytes = await _download_audio_from_s3(audio_s3_uri)

        from starlette.concurrency import run_in_threadpool

        extraction_result = await run_in_threadpool(
            extract_right_channel_wav, audio_bytes
        )

        if extraction_result is None:
            return EvaluatorResult(
                metric_name="stt_accuracy",
                score=1.0,
                passed=True,
                reason="Could not extract caller channel — STT accuracy non-computable",
            )

        caller_audio, audio_filename = extraction_result

        whisper_text = await _transcribe_with_whisper(
            caller_audio, filename=audio_filename
        )

        if not whisper_text.strip():
            return EvaluatorResult(
                metric_name="stt_accuracy",
                score=1.0,
                passed=True,
                reason="Whisper produced empty transcription — cannot compute WER",
            )

        wer_result = compute_wer(reference=whisper_text, hypothesis=primary_transcript)
        wer: float = wer_result["wer"]

        # Invert WER for a [0, 1] score: 0% WER → 1.0, 100% WER → 0.0
        score = max(0.0, 1.0 - wer)
        passed = wer <= _WER_THRESHOLD

        # Round for display/storage, but threshold check uses raw value above
        display_wer = round(wer, 4)
        wer_result["wer"] = display_wer

        return EvaluatorResult(
            metric_name="stt_accuracy",
            score=round(score, 4),
            passed=passed,
            reason=(
                f"WER={display_wer:.2%} "
                f"(S={wer_result['substitutions']} I={wer_result['insertions']} "
                f"D={wer_result['deletions']}, "
                f"ref_words={wer_result['ref_words']})"
            ),
            raw_output=wer_result,
        )

    except Exception:
        logger.exception("STT accuracy evaluation failed")
        return EvaluatorResult(
            metric_name="stt_accuracy",
            score=0.0,
            passed=False,
            reason="STT accuracy evaluation failed — see logs for details",
        )
