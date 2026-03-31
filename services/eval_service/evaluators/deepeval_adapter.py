"""Adapter layer: wraps pal-agents DeepEval metrics into EvaluatorResult.

Each function creates a DeepEval metric, runs it against a test case,
and returns an EvaluatorResult for DB storage.
"""

from __future__ import annotations

from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn
from pal_agents.evals.metrics import (
    create_faithfulness_metric,
    create_responsive_metric,
    create_task_completion_metric,
    create_voice_appropriate_metric,
    preprocess_context,
)

from services.eval_service._evaluators import ConversationRecord, EvaluatorResult
from utils.log import logger


async def evaluate_faithfulness(
    record: ConversationRecord,
    context_override: list[str] | None = None,
) -> EvaluatorResult:
    """Run FaithfulnessMetric (claim-by-claim verification against context).

    Replaces E2 menu_hallucination and E3 groundedness.

    Args:
        record: The conversation record to evaluate.
        context_override: If provided, use this instead of record.scenario.context.
    """
    metric = create_faithfulness_metric()
    full_response = "\n".join(record.agent_responses)
    raw_context = (
        context_override if context_override is not None else record.scenario.context
    )
    context = preprocess_context(raw_context)

    test_case = LLMTestCase(
        input=_first_user_message(record),
        actual_output=full_response,
        retrieval_context=context,
    )

    try:
        await metric.a_measure(test_case)
        return EvaluatorResult(
            metric_name="faithfulness",
            score=metric.score or 0.0,
            passed=metric.is_successful(),
            reason=metric.reason or "No reason provided",
        )
    except Exception:
        logger.exception("Faithfulness metric failed")
        return EvaluatorResult(
            metric_name="faithfulness",
            score=0.0,
            passed=False,
            reason="Faithfulness metric failed — treating as ungrounded",
        )


async def evaluate_responsive(record: ConversationRecord) -> EvaluatorResult:
    """Run Responsive GEval metric (does the agent answer the question?)."""
    metric = create_responsive_metric()
    last_input, last_output = _last_turn(record)

    test_case = LLMTestCase(
        input=last_input,
        actual_output=last_output,
    )

    try:
        await metric.a_measure(test_case)
        return EvaluatorResult(
            metric_name="responsive",
            score=metric.score or 0.0,
            passed=metric.is_successful(),
            reason=metric.reason or "No reason provided",
        )
    except Exception:
        logger.exception("Responsive metric failed")
        return EvaluatorResult(
            metric_name="responsive",
            score=0.0,
            passed=False,
            reason="Responsive metric failed",
        )


async def evaluate_voice_appropriate(record: ConversationRecord) -> EvaluatorResult:
    """Run VoiceAppropriateMetric (word count + DAG tone check)."""
    metric = create_voice_appropriate_metric()
    _, last_output = _last_turn(record)

    test_case = LLMTestCase(
        input="(evaluation)",
        actual_output=last_output,
    )

    try:
        await metric.a_measure(test_case)
        return EvaluatorResult(
            metric_name="voice_appropriate",
            score=metric.score or 0.0,
            passed=metric.is_successful(),
            reason=metric.reason or "No reason provided",
        )
    except Exception:
        logger.exception("Voice appropriate metric failed")
        return EvaluatorResult(
            metric_name="voice_appropriate",
            score=0.0,
            passed=False,
            reason="Voice appropriate metric failed",
        )


async def evaluate_task_completion(record: ConversationRecord) -> EvaluatorResult:
    """Run TaskCompletion ConversationalGEval (multi-turn completion scoring)."""
    metric = create_task_completion_metric()
    turns = _build_turns(record)

    test_case = ConversationalTestCase(
        turns=turns,
    )

    try:
        await metric.a_measure(test_case)
        return EvaluatorResult(
            metric_name="task_completion",
            score=metric.score or 0.0,
            passed=metric.is_successful(),
            reason=metric.reason or "No reason provided",
        )
    except Exception:
        logger.exception("Task completion metric failed")
        return EvaluatorResult(
            metric_name="task_completion",
            score=0.0,
            passed=False,
            reason="Task completion metric failed",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_user_message(record: ConversationRecord) -> str:
    """Extract the first user message from the record."""
    if record.turns:
        return record.turns[0].get("user", "")
    return ""


def _last_turn(record: ConversationRecord) -> tuple[str, str]:
    """Extract the last user-assistant exchange."""
    if record.turns:
        last = record.turns[-1]
        return last.get("user", ""), last.get("assistant", "")
    return "", ""


def _build_turns(record: ConversationRecord) -> list[Turn]:
    """Convert ConversationRecord turns into DeepEval Turn objects."""
    turns: list[Turn] = []
    for turn in record.turns:
        user_msg = turn.get("user", "")
        assistant_msg = turn.get("assistant", "")
        if user_msg:
            turns.append(Turn(role="user", content=user_msg))
        if assistant_msg:
            turns.append(Turn(role="assistant", content=assistant_msg))
    return turns
