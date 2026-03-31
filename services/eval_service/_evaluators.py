"""Evaluator orchestrator for the eval service.

Coordinates running individual evaluators against a conversation record
and aggregating their results.

Evaluation sources:
- E1 tool_call: deterministic, local (services/eval_service/evaluators/tool_call.py)
- All others: pal-agents DeepEval metrics via deepeval_adapter.py
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
    """Record of a completed evaluation conversation."""

    scenario: EvalScenario
    turns: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    agent_responses: list[str] = field(default_factory=list)


def _should_run_tool_call(scenario: EvalScenario) -> bool:
    """E1 runs when expected_tool_calls is non-empty."""
    return len(scenario.expected_tool_calls) > 0


def _should_run_faithfulness(scenario: EvalScenario) -> bool:
    """Faithfulness runs when context is provided."""
    return len(scenario.context) > 0


def _should_run_task_completion(scenario: EvalScenario) -> bool:
    """Task completion runs on multi-turn conversations."""
    return len(scenario.user_turns) > 1


async def evaluate_scenario(
    record: ConversationRecord,
    project_context: list[str] | None = None,
) -> list[EvaluatorResult]:
    """Run all applicable evaluators against a conversation record.

    Execution order:
    - Phase 1: Deterministic (E1 tool call)
    - Phase 2: DeepEval metrics in parallel (faithfulness, responsive,
      voice_appropriate, task_completion)

    Args:
        record: The completed conversation record to evaluate.
        project_context: Optional additional project-level context
            (overrides scenario context for faithfulness).

    Returns:
        List of EvaluatorResult from all evaluators that ran.
    """
    from services.eval_service.evaluators.deepeval_adapter import (
        evaluate_faithfulness,
        evaluate_responsive,
        evaluate_task_completion,
        evaluate_voice_appropriate,
    )
    from services.eval_service.evaluators.tool_call import evaluate_tool_calls

    results: list[EvaluatorResult] = []

    # Use project_context if provided, without mutating the original record
    effective_context = project_context if project_context else record.scenario.context

    # Phase 1: Deterministic evaluators
    if _should_run_tool_call(record.scenario):
        expected = [
            {"tool": tc.tool, "args": tc.args}
            for tc in record.scenario.expected_tool_calls
        ]
        result = evaluate_tool_calls(expected, record.tool_calls)
        results.append(result)
        logger.debug("E1 tool_call: score=%s passed=%s", result.score, result.passed)

    # Phase 2: DeepEval metrics in parallel
    metric_tasks: list[asyncio.Task[EvaluatorResult]] = []

    if effective_context:
        metric_tasks.append(
            asyncio.create_task(
                evaluate_faithfulness(record, context_override=effective_context),
                name="faithfulness",
            )
        )

    # Responsive and voice_appropriate always run (only need input + output)
    if record.agent_responses:
        metric_tasks.append(
            asyncio.create_task(
                evaluate_responsive(record),
                name="responsive",
            )
        )
        metric_tasks.append(
            asyncio.create_task(
                evaluate_voice_appropriate(record),
                name="voice_appropriate",
            )
        )

    if _should_run_task_completion(record.scenario):
        metric_tasks.append(
            asyncio.create_task(
                evaluate_task_completion(record),
                name="task_completion",
            )
        )

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
