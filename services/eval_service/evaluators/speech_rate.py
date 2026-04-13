"""E17: Speech rate evaluator.

Computes words-per-minute (WPM) from transcript word count and turn
durations.  Turns outside the 120-180 WPM range are flagged.

No LLM needed — pure arithmetic on transcript metadata.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

# Acceptable WPM range for conversational speech
_WPM_LOW = 120
_WPM_HIGH = 180


def _word_count(text: str) -> int:
    """Count whitespace-delimited words in *text*."""
    return len(text.split())


def compute_turn_wpm(
    text: str,
    duration_s: float,
) -> float | None:
    """Compute WPM for a single turn.

    Returns ``None`` when duration is too short (< 0.5 s) or the turn
    has no words — both cases are unreliable for rate estimation.
    """
    words = _word_count(text)
    if words == 0 or duration_s < 0.5:
        return None
    return (words / duration_s) * 60.0


def evaluate_speech_rate(
    transcript: Sequence[dict[str, Any]],
    speaker: str = "assistant",
) -> EvaluatorResult:
    """Score TTS speech rate across agent turns.

    For each turn by *speaker* that has ``start_time`` and ``end_time``,
    WPM is computed.  The final score is the ratio of turns within the
    acceptable range (120-180 WPM) to total measurable turns.

    Args:
        transcript: List of dicts with ``speaker`` (or ``role``),
            ``text`` (or ``content``), ``start_time``, ``end_time``.
        speaker: Which speaker to measure (default ``"assistant"``
            for agent TTS output).

    Returns:
        EvaluatorResult with score in [0, 1] and per-turn WPM details.
    """
    turn_details: list[dict[str, Any]] = []

    for i, entry in enumerate(transcript):
        entry_speaker = entry.get("speaker") or entry.get("role")
        if entry_speaker != speaker:
            continue

        text = entry.get("text") or entry.get("content") or ""
        start = entry.get("start_time")
        end = entry.get("end_time")

        if start is None or end is None:
            continue

        try:
            duration = float(end) - float(start)
        except (TypeError, ValueError):
            continue
        wpm = compute_turn_wpm(str(text), duration)
        if wpm is None:
            continue

        in_range = _WPM_LOW <= wpm <= _WPM_HIGH
        turn_details.append(
            {
                "turn_index": i,
                "wpm": round(wpm, 1),
                "duration_s": round(duration, 2),
                "word_count": _word_count(str(text)),
                "in_range": in_range,
            }
        )

    if not turn_details:
        return EvaluatorResult(
            metric_name="speech_rate",
            score=1.0,
            passed=True,
            reason="No measurable agent turns for speech rate evaluation",
        )

    in_range_count = sum(1 for t in turn_details if t["in_range"])
    total = len(turn_details)
    score = in_range_count / total

    avg_wpm = sum(t["wpm"] for t in turn_details) / total
    out_of_range = [t for t in turn_details if not t["in_range"]]

    parts: list[str] = [
        f"{in_range_count}/{total} turns in {_WPM_LOW}-{_WPM_HIGH} WPM range",
        f"avg={avg_wpm:.0f} WPM",
    ]
    if out_of_range:
        indices = [t["turn_index"] for t in out_of_range]
        parts.append(f"out-of-range turns: {indices}")

    raw: dict[str, Any] = {
        "avg_wpm": round(avg_wpm, 1),
        "in_range_count": in_range_count,
        "total_measured": total,
        "wpm_low": _WPM_LOW,
        "wpm_high": _WPM_HIGH,
        "turns": turn_details,
    }

    return EvaluatorResult(
        metric_name="speech_rate",
        score=round(score, 4),
        passed=score >= 0.7,
        reason=" | ".join(parts),
        raw_output=raw,
    )
