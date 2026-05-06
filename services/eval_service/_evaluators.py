"""Evaluator orchestrator for the eval service.

Coordinates running individual evaluators against a conversation record
and aggregating their results.

Evaluation sources:
- Tool call: deterministic, local (services/eval_service/evaluators/tool_call_args.py)
- Conversation judge: pal-agents LLM judge via judge_adapter.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from services.eval_service.schema import EvalScenario
from utils.log import logger


@dataclass
class EvaluatorResult:
    """Result from a single evaluator."""

    metric_name: str
    score: float
    passed: bool
    reason: str
    raw_output: dict[str, Any] | None = None


@dataclass
class ConversationRecord:
    """Record of a completed evaluation conversation.

    Core fields (all modes):
        scenario, turns, tool_calls, agent_responses

    Voice-specific fields (populated only for ``driver="voice"``):
        voice_transcript — timestamped entries with speaker/start_time/end_time
        turn_latencies_ms — per-turn latencies from CallMetricsReport
        audio_recording_s3_uri — S3 URI of the call recording
        is_voice — flag indicating this record came from a voice eval
    """

    scenario: EvalScenario
    turns: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    agent_responses: list[str] = field(default_factory=list)

    # Voice-specific metadata
    voice_transcript: list[dict[str, Any]] = field(default_factory=list)
    turn_latencies_ms: list[float] = field(default_factory=list)
    audio_recording_s3_uri: str | None = None
    is_voice: bool = False
    voice_params: dict[str, Any] | None = None


def _should_run_tool_call(scenario: EvalScenario) -> bool:
    """E1 runs when expected_tool_calls is non-empty."""
    return len(scenario.expected_tool_calls) > 0


async def evaluate_scenario(
    record: ConversationRecord,
) -> list[EvaluatorResult]:
    """Run all applicable evaluators against a conversation record.

    Execution order:
    - Phase 1: Deterministic (E1 tool call)
    - Phase 2: LLM judge (task_completion — always runs)
      - Voice-specific (when ``record.is_voice``): interruption, latency_silence,
        speech_rate, speech_fidelity

    Args:
        record: The completed conversation record to evaluate.

    Returns:
        List of EvaluatorResult from all evaluators that ran.
    """
    from services.eval_service.evaluators.judge_adapter import evaluate_task_completion
    from services.eval_service.evaluators.tool_call_args import evaluate_tool_call_args

    results: list[EvaluatorResult] = []

    # Phase 1: Deterministic evaluators
    if _should_run_tool_call(record.scenario):
        expected = [
            {"tool": tc.tool, "args": tc.args, "optional": tc.optional}
            for tc in record.scenario.expected_tool_calls
        ]
        result = evaluate_tool_call_args(expected, record.tool_calls)
        results.append(result)
        logger.debug(
            "tool_call_accuracy: score=%s passed=%s", result.score, result.passed
        )

    # Phase 2: LLM judge + voice-specific evaluators in parallel
    metric_tasks: list[asyncio.Task[EvaluatorResult]] = []

    metric_tasks.append(
        asyncio.create_task(
            evaluate_task_completion(record),
            name="task_completion",
        )
    )

    # Phase 2b: Voice-specific evaluators (only when is_voice=True)
    if record.is_voice:
        _schedule_voice_evaluators(record, metric_tasks)

    if metric_tasks:
        metric_results = await asyncio.gather(*metric_tasks, return_exceptions=True)
        for task_result in metric_results:
            if isinstance(task_result, EvaluatorResult):
                results.append(task_result)
                logger.debug(
                    "Evaluator %s: score=%s passed=%s",
                    task_result.metric_name,
                    task_result.score,
                    task_result.passed,
                )
            elif isinstance(task_result, BaseException):
                logger.exception("Evaluator task failed", exc_info=task_result)
                results.append(
                    EvaluatorResult(
                        metric_name="unknown",
                        score=0.0,
                        passed=False,
                        reason=f"Evaluator error: {task_result}",
                    )
                )

    return results


async def _run_sync_evaluator(fn: Any, *args: Any) -> EvaluatorResult:
    """Wrap a synchronous evaluator function as a coroutine."""
    return fn(*args)


def _schedule_voice_evaluators(
    record: ConversationRecord,
    tasks: list[asyncio.Task[EvaluatorResult]],
) -> None:
    """Add voice-specific evaluator tasks to the parallel task list.

    Evaluators are only scheduled when the record contains the data they
    need, so missing metadata degrades gracefully (evaluator is skipped,
    not errored).
    """
    from services.eval_service.evaluators.interruption import evaluate_interruptions
    from services.eval_service.evaluators.latency_silence import (
        evaluate_latency_silence,
    )
    from services.eval_service.evaluators.speech_fidelity import (
        evaluate_speech_fidelity,
    )
    from services.eval_service.evaluators.speech_rate import evaluate_speech_rate
    from services.eval_service.evaluators.stt_accuracy import (
        evaluate_stt_accuracy,
        extract_primary_transcript,
    )

    # E14: Interruption detection (needs timestamped transcript)
    if record.voice_transcript:
        tasks.append(
            asyncio.create_task(
                _run_sync_evaluator(evaluate_interruptions, record.voice_transcript),
                name="interruption",
            )
        )

    # E15: Latency / silence (needs latencies and/or transcript)
    if record.turn_latencies_ms or record.voice_transcript:
        tasks.append(
            asyncio.create_task(
                _run_sync_evaluator(
                    evaluate_latency_silence,
                    record.turn_latencies_ms,
                    record.voice_transcript,
                ),
                name="latency_silence",
            )
        )

    # E16: STT accuracy (needs audio recording + transcript)
    if record.audio_recording_s3_uri and record.voice_transcript:
        primary_transcript = extract_primary_transcript(
            record.voice_transcript, speaker="user"
        )
        tasks.append(
            asyncio.create_task(
                evaluate_stt_accuracy(
                    record.audio_recording_s3_uri, primary_transcript
                ),
                name="stt_accuracy",
            )
        )

    # E17: Speech rate (needs timestamped transcript)
    if record.voice_transcript:
        tasks.append(
            asyncio.create_task(
                _run_sync_evaluator(
                    evaluate_speech_rate, record.voice_transcript, "assistant"
                ),
                name="speech_rate",
            )
        )

    # E18: Speech fidelity LALM-as-Judge (needs agent output)
    if record.agent_responses:
        tasks.append(
            asyncio.create_task(
                evaluate_speech_fidelity(record),
                name="speech_fidelity",
            )
        )
