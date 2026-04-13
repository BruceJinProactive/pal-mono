"""E14: Interruption evaluator.

Detects overlapping speech from transcript timestamps.
Score = ratio of clean (non-interrupted) turns to total turns.
No LLM needed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from services.eval_service._evaluators import EvaluatorResult

# A turn is "interrupted" when the next speaker's start_time is earlier than
# the current speaker's end_time, indicating overlapping speech.
_OVERLAP_TOLERANCE_S = 0.05  # 50ms tolerance to ignore trivial timing jitter


def evaluate_interruptions(
    transcript: Sequence[dict[str, Any]],
    interruption_events: Sequence[dict[str, Any]] | None = None,
) -> EvaluatorResult:
    """Compute the clean-turn ratio for a conversation.

    Two complementary signals are used:

    1. **Explicit interruption events** — if ``interruption_events`` is
       provided and non-empty, each event counts as an interrupted turn.
    2. **Timestamp overlap** — consecutive transcript entries where the next
       speaker's ``start_time`` is earlier than the current entry's
       ``end_time`` (minus a small tolerance) are counted as overlaps.

    The final score is the ratio of clean turns to total turns.

    Args:
        transcript: List of dicts with ``speaker``, ``text``,
            ``start_time``, and ``end_time`` keys.
        interruption_events: Optional list of dicts with at least a
            ``turn_index`` key indicating which turns were interrupted.

    Returns:
        EvaluatorResult with score in [0, 1] and passed = score >= 0.8.
    """
    if not transcript:
        return EvaluatorResult(
            metric_name="interruption",
            score=1.0,
            passed=True,
            reason="No transcript entries to evaluate",
        )

    total_turns = len(transcript)

    # Collect indices of interrupted turns from both signals
    interrupted_indices: set[int] = set()

    # Signal 1: Explicit interruption events (from CallMetricsReport)
    if interruption_events:
        for event in interruption_events:
            idx = event.get("turn_index")
            if isinstance(idx, int) and 0 <= idx < total_turns:
                interrupted_indices.add(idx)

    # Signal 2: Timestamp overlap detection
    for i in range(len(transcript) - 1):
        current = transcript[i]
        next_entry = transcript[i + 1]

        current_end = float(current.get("end_time", 0.0))
        next_start = float(next_entry.get("start_time", 0.0))

        # Only count overlap when speakers differ (cross-talk)
        if (
            current.get("speaker") != next_entry.get("speaker")
            and current_end > 0
            and next_start > 0
            and next_start < current_end - _OVERLAP_TOLERANCE_S
        ):
            interrupted_indices.add(i)

    clean_turns = total_turns - len(interrupted_indices)
    score = clean_turns / total_turns
    passed = score >= 0.8

    parts: list[str] = [f"{clean_turns}/{total_turns} clean turns (score={score:.2f})."]
    if interrupted_indices:
        parts.append(f"Interrupted turn indices: {sorted(interrupted_indices)}")

    return EvaluatorResult(
        metric_name="interruption",
        score=score,
        passed=passed,
        reason=" ".join(parts),
    )
