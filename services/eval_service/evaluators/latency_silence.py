"""E15: Latency and silence evaluator.

Computes p50/p95 turn latency from ``turn_latencies_ms`` and detects
awkward silence gaps (>3 s) between transcript entries.
Score penalizes both high latency and long silences against SLA thresholds.
No LLM needed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

# SLA thresholds (milliseconds)
_P50_SLA_MS = 1500.0  # target p50 ≤ 1.5s
_P95_SLA_MS = 3000.0  # target p95 ≤ 3s

# Silence gap threshold (seconds)
_SILENCE_THRESHOLD_S = 3.0


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile using linear interpolation."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _detect_silence_gaps(
    transcript: Sequence[dict[str, Any]],
    threshold_s: float = _SILENCE_THRESHOLD_S,
) -> list[dict[str, Any]]:
    """Find gaps between consecutive transcript entries exceeding *threshold_s*.

    Returns a list of dicts with ``index``, ``gap_seconds``, and the
    ``speakers`` involved.
    """
    gaps: list[dict[str, Any]] = []
    for i in range(len(transcript) - 1):
        current_end = float(transcript[i].get("end_time", 0.0))
        next_start = float(transcript[i + 1].get("start_time", 0.0))

        if current_end <= 0 or next_start <= 0:
            continue

        gap = next_start - current_end
        if gap >= threshold_s:
            gaps.append(
                {
                    "index": i,
                    "gap_seconds": round(gap, 2),
                    "speakers": (
                        transcript[i].get("speaker"),
                        transcript[i + 1].get("speaker"),
                    ),
                }
            )
    return gaps


def evaluate_latency_silence(
    turn_latencies_ms: Sequence[float],
    transcript: Sequence[dict[str, Any]] | None = None,
) -> EvaluatorResult:
    """Score a conversation on latency and silence.

    **Latency sub-score** (0-1): Measures p50 and p95 against SLA
    thresholds. Each metric contributes 0.5 weight to the latency
    sub-score.

    **Silence sub-score** (0-1): Ratio of turns *without* an adjacent
    awkward silence gap to total turns.

    Final score = ``0.7 * latency_score + 0.3 * silence_score`` when both
    signals are available, or whichever signal is present alone.

    Args:
        turn_latencies_ms: Per-turn total latency in milliseconds.
        transcript: Optional list of dicts with ``speaker``, ``text``,
            ``start_time``, ``end_time``.

    Returns:
        EvaluatorResult with composite score and detailed reason.
    """
    if not turn_latencies_ms and not transcript:
        return EvaluatorResult(
            metric_name="latency_silence",
            score=1.0,
            passed=True,
            reason="No latency data or transcript to evaluate",
        )

    parts: list[str] = []
    raw: dict[str, Any] = {}
    latency_score: float | None = None
    silence_score: float | None = None

    # --- Latency sub-score ---
    if turn_latencies_ms:
        sorted_vals = sorted(turn_latencies_ms)
        p50 = _percentile(sorted_vals, 50)
        p95 = _percentile(sorted_vals, 95)
        raw["p50_ms"] = round(p50, 1)
        raw["p95_ms"] = round(p95, 1)
        raw["turn_count"] = len(sorted_vals)

        # Score each metric: 1.0 if within SLA, linearly degrading to 0.0
        # at 2x the SLA threshold.
        p50_score = max(0.0, min(1.0, 1.0 - (p50 - _P50_SLA_MS) / _P50_SLA_MS))
        p95_score = max(0.0, min(1.0, 1.0 - (p95 - _P95_SLA_MS) / _P95_SLA_MS))
        latency_score = 0.5 * p50_score + 0.5 * p95_score

        raw["p50_score"] = round(p50_score, 3)
        raw["p95_score"] = round(p95_score, 3)
        raw["latency_score"] = round(latency_score, 3)

        parts.append(
            f"Latency: p50={p50:.0f}ms p95={p95:.0f}ms "
            f"(sub-score={latency_score:.2f})"
        )

    # --- Silence sub-score ---
    if transcript and len(transcript) > 1:
        silence_gaps = _detect_silence_gaps(transcript)
        raw["silence_gaps"] = silence_gaps

        affected_indices: set[int] = set()
        for gap in silence_gaps:
            affected_indices.add(gap["index"])

        total_transitions = len(transcript) - 1
        clean_transitions = total_transitions - len(affected_indices)
        silence_score = clean_transitions / total_transitions

        raw["silence_score"] = round(silence_score, 3)
        raw["silence_gap_count"] = len(silence_gaps)

        if silence_gaps:
            max_gap = max(g["gap_seconds"] for g in silence_gaps)
            parts.append(
                f"Silence: {len(silence_gaps)} gap(s) >{_SILENCE_THRESHOLD_S}s "
                f"(max={max_gap}s, sub-score={silence_score:.2f})"
            )
        else:
            parts.append(f"Silence: no gaps >{_SILENCE_THRESHOLD_S}s (sub-score=1.00)")

    # --- Composite score ---
    if latency_score is not None and silence_score is not None:
        score = 0.7 * latency_score + 0.3 * silence_score
    elif latency_score is not None:
        score = latency_score
    elif silence_score is not None:
        score = silence_score
    else:
        # Transcript provided but too short for silence analysis,
        # and no latency data — nothing actionable to score.
        return EvaluatorResult(
            metric_name="latency_silence",
            score=1.0,
            passed=True,
            reason="Insufficient data for latency or silence evaluation",
        )

    passed = score >= 0.7

    return EvaluatorResult(
        metric_name="latency_silence",
        score=round(score, 4),
        passed=passed,
        reason=" | ".join(parts),
        raw_output=raw,
    )
