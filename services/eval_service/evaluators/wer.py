"""E19: Word Error Rate evaluator for voice eval transcript accuracy.

Thin adapter that delegates to ``pal_agents.evals.evaluators.wer.WEREvaluator``
and converts the result to pal-mono's ``EvaluatorResult`` type.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from services.eval_service._evaluators import EvaluatorResult
from utils.log import logger


async def evaluate_wer(
    ground_truth_texts: Sequence[str],
    voice_transcript: Sequence[dict[str, Any]],
) -> EvaluatorResult:
    """Compute WER by delegating to the pal-agents WEREvaluator.

    Args:
        ground_truth_texts: What TTS was instructed to speak for each user turn.
        voice_transcript: Transcript entries with ``speaker``/``role`` and
            ``text``/``content`` keys.

    Returns:
        EvaluatorResult with score = 1 - average_wer (higher is better).
    """
    from pal_agents.evals.evaluators import (
        ConversationData,
        TranscriptEntry,
        WEREvaluator,
    )

    # Build transcript entries for the pal-agents evaluator
    entries: list[TranscriptEntry] = []
    for entry in voice_transcript:
        speaker = entry.get("speaker") or entry.get("role") or ""
        text = entry.get("text") or entry.get("content") or ""
        try:
            start_time = float(entry.get("start_time") or 0.0)
            end_time = float(entry.get("end_time") or 0.0)
        except (TypeError, ValueError):
            start_time = 0.0
            end_time = 0.0
        entries.append(
            TranscriptEntry(
                speaker=speaker,
                text=text,
                start_time=start_time,
                end_time=end_time,
            )
        )

    # Build minimal ConversationData with ground_truth_texts in call_metadata
    _zero = UUID(int=0)
    data = ConversationData(
        conversation_id=_zero,
        call_id="",
        user_id=_zero,
        account_id=_zero,
        account_name="",
        project_id=_zero,
        channel="voice",
        is_test=True,
        transcript=tuple(entries),
        call_metadata={"ground_truth_texts": list(ground_truth_texts)},
    )

    evaluator = WEREvaluator()
    result = await evaluator.evaluate(data)

    # Convert pal-agents EvalResult -> pal-mono EvaluatorResult
    if result.error:
        logger.warning("WER evaluator error: %s", result.error)
        return EvaluatorResult(
            metric_name="wer",
            score=0.0,
            passed=False,
            reason=result.error,
        )

    score = result.score if result.score is not None else 0.0
    average_wer = result.dimensions.get("average_wer", 1.0 - score)

    return EvaluatorResult(
        metric_name="wer",
        score=round(score, 4),
        passed=result.passed,
        reason=(
            f"WER={average_wer:.2%} across "
            f"{result.metadata.get('num_turns_compared', '?')} turns"
        ),
        raw_output={**result.dimensions, **result.metadata},
    )
