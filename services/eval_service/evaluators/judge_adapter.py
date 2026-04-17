"""Adapter layer: wraps pal-agents conversation judge into EvaluatorResult.

Uses judge_conversation() from pal-agents for multi-dimension quality scoring.
"""

from __future__ import annotations

from pal_agents.evals.judge import JudgeConfig, JudgeDimension, judge_conversation

from services.eval_service._evaluators import ConversationRecord, EvaluatorResult
from utils.log import logger


async def evaluate_task_completion(record: ConversationRecord) -> EvaluatorResult:
    """Run pal-agents LLM judge for conversation quality scoring.

    Uses configurable dimensions (request_accuracy, contextual_relevancy,
    role_adherence, conversation_quality) matching pal-agents run_loop.
    """
    config = _build_judge_config()
    conversation = _build_judge_conversation(record)
    scenario_id = record.scenario.scenario_id

    try:
        result = await judge_conversation(
            conversation=conversation,
            agent_id=scenario_id,
            test_id=scenario_id,
            config=config,
        )
    except Exception:
        logger.exception("Task completion judge raised an exception")
        return EvaluatorResult(
            metric_name="task_completion",
            score=0.0,
            passed=False,
            reason="Task completion judge failed",
        )

    if result.get("error"):
        logger.error(
            "Task completion judge failed: %s",
            result["error"],
        )
        return EvaluatorResult(
            metric_name="task_completion",
            score=0.0,
            passed=False,
            reason=f"Judge error: {result['error']}",
            raw_output=result,
        )

    return EvaluatorResult(
        metric_name="task_completion",
        score=result.get("conversation_quality_score") or 0.0,
        passed=bool(result.get("conversation_quality_passed")),
        reason=result.get("overall_reasoning") or "No reasoning provided",
        raw_output=result,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_judge_conversation(record: ConversationRecord) -> list[dict[str, str]]:
    """Convert ConversationRecord turns into judge conversation format."""
    conversation: list[dict[str, str]] = []
    for turn in record.turns:
        user_msg = turn.get("user", "")
        assistant_msg = turn.get("assistant", "")
        if user_msg:
            conversation.append({"role": "user", "content": user_msg})
        if assistant_msg:
            conversation.append({"role": "assistant", "content": assistant_msg})
    return conversation


def _build_judge_config() -> JudgeConfig:
    """Build judge config with ordering-focused dimensions.

    Matches pal-agents Toast run_config.json dimensions exactly.
    """
    return JudgeConfig(
        enabled=True,
        model="gpt-4.1-mini",
        threshold=0.7,
        rubric_name="Toast ordering call quality rubric v1",
        use_case="AI voice ordering for restaurant agents",
        dimensions=[
            JudgeDimension(
                name="request_accuracy",
                weight=2.0,
                evaluation_question=(
                    "Did the agent end with the correct and complete captured "
                    "order, independent of backend submission availability?"
                ),
                scale_1="The final captured order is wrong, incomplete, or unstable.",
                scale_2="Multiple meaningful order details are missing or wrong.",
                scale_3="The core request is probably right, but at least one detail is weak.",
                scale_4="The captured order is clear and largely complete.",
                scale_5=(
                    "The final captured order is explicit, complete, and fully "
                    "updated after all changes."
                ),
                outcome_critical=False,
            ),
            JudgeDimension(
                name="contextual_relevancy",
                weight=1.0,
                evaluation_question=(
                    "Did each response directly address the user's question "
                    "and stay on topic?"
                ),
                scale_1="Responses consistently misinterpret questions or go off-topic.",
                scale_2="Multiple responses miss the point.",
                scale_3="Most responses are on-topic but at least one misinterprets the user.",
                scale_4="Responses are relevant with only minor tangential content.",
                scale_5="Every response directly and precisely addresses the user's intent.",
                outcome_critical=False,
            ),
            JudgeDimension(
                name="role_adherence",
                weight=1.0,
                evaluation_question=(
                    "Did the agent maintain its restaurant assistant persona?"
                ),
                scale_1="Agent frequently breaks character or makes false claims.",
                scale_2="Agent breaks character in multiple turns.",
                scale_3="Agent mostly stays in character but has one meaningful slip.",
                scale_4="Agent maintains persona with only a minor slip.",
                scale_5="Agent fully represents the restaurant naturally throughout.",
                outcome_critical=False,
            ),
            JudgeDimension(
                name="conversation_quality",
                weight=1.0,
                evaluation_question=(
                    "Were the responses concise, natural, and well-formatted "
                    "for a voice ordering interaction?"
                ),
                scale_1="Responses are robotic, excessively long, or heavily formatted with bullet lists.",
                scale_2="Responses are mostly formulaic with some natural moments, or consistently too long.",
                scale_3="Responses are acceptable but unremarkable in naturalness and length.",
                scale_4="Responses are natural and concise with minor formatting issues.",
                scale_5="Responses are concise (<80 words), natural, conversational, with no bullet lists.",
                outcome_critical=False,
            ),
        ],
    )
