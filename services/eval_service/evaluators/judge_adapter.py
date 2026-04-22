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
                evaluation_question="Did the agent end with the correct and complete captured order or requested update state, independent of backend submission availability? If the user never requested a food order or modification, score 5 — this dimension only applies when ordering is involved.",
                why_it_matters="The primary job is to capture the requested food or update exactly. If submission is temporarily unavailable, do not penalize that alone as long as the final order state is clearly preserved and communicated. If no order was requested, this dimension is automatically satisfied.",
                scale_1="The final captured order or requested update state is wrong, incomplete, or unstable.",
                scale_2="Multiple meaningful order details are missing, contradictory, or likely wrong.",
                scale_3="The core request is probably right, but at least one meaningful detail is weakly captured or not re-anchored.",
                scale_4="The captured order state is clear and largely complete. If submission is unavailable, the agent communicates that cleanly without losing the final order state.",
                scale_5="The final captured order or requested update state is explicit, complete, and fully updated after all changes. If submission is unavailable, the agent communicates that clearly without any loss of order accuracy. If no order or modification was requested by the user, this is automatically a 5.",
                high_signals=[
                    "Captures item names, sizes, quantities, modifiers, and add-ons clearly",
                    "Folds late changes into the final order state",
                    "If submission is unavailable, clearly restates the final order and next state",
                ],
                low_signals=[
                    "Drops a modifier or substitution",
                    "Confuses specialty items and customizations",
                    "Leaves the final order state unclear when submission is unavailable",
                ],
                failure_modes=[
                    "Wrong or unresolved item capture",
                    "Changed topping or substitution never reflected in final order state",
                    "Claims the order was placed when submission was unavailable",
                ],
                outcome_critical=False,
            ),
            JudgeDimension(
                name="contextual_relevancy",
                weight=1.0,
                evaluation_question="Did each response directly address the user's question and stay on topic?",
                why_it_matters="Off-topic or misinterpreted responses waste turns and erode trust, especially in voice ordering where the customer cannot easily re-orient.",
                scale_1="Responses consistently misinterpret questions or go off-topic.",
                scale_2="Multiple responses miss the point or address the wrong aspect.",
                scale_3="Most responses are on-topic but at least one meaningfully misinterprets the user.",
                scale_4="Responses are relevant with only minor tangential content.",
                scale_5="Every response directly and precisely addresses the user's intent.",
                high_signals=[
                    "Answers the exact question asked",
                    "References specific menu items when asked about the menu",
                    "Handles follow-ups in context of prior turns",
                ],
                low_signals=[
                    "Gives generic responses to specific questions",
                    "Repeats information already provided",
                    "Misinterprets a modification as a new order",
                ],
                failure_modes=[
                    "Responds to a different question than what was asked",
                    "Ignores the customer's stated constraint or preference",
                ],
                outcome_critical=False,
            ),
            JudgeDimension(
                name="role_adherence",
                weight=1.0,
                evaluation_question="Did the agent maintain its restaurant assistant persona while truthfully communicating operational constraints?",
                why_it_matters="The agent should stay in character and avoid false claims. Truthfully stating that ordering or submission is temporarily unavailable is acceptable and should not count as a persona break by itself.",
                scale_1="Agent frequently breaks character or makes false claims about restaurant capabilities or order status.",
                scale_2="Agent breaks character or misrepresents order status in multiple turns.",
                scale_3="Agent mostly stays in character but has one meaningful slip.",
                scale_4="Agent maintains persona with only a minor slip. Truthful mention of temporary submission unavailability does not reduce this score by itself.",
                scale_5="Agent fully represents the restaurant naturally throughout, including any necessary explanation that submission is temporarily unavailable.",
                high_signals=[
                    "Uses restaurant-appropriate language",
                    "Stays within ordering and menu scope",
                    "Explains temporary submission unavailability as an operational restaurant or ordering status when needed",
                ],
                low_signals=[
                    "Claims to be an AI or breaks the fourth wall",
                    "Uses opaque internal-tool language",
                    "Implies the order was placed when it was not",
                ],
                failure_modes=[
                    "Explicitly identifies as AI when not asked",
                    "Falsely claims successful order placement",
                ],
                outcome_critical=False,
            ),
            JudgeDimension(
                name="conversation_quality",
                weight=1.0,
                evaluation_question="Were the responses concise, natural, and well-formatted for a voice ordering interaction?",
                why_it_matters="Verbose or robotic responses are especially painful in voice ordering where the customer must listen to the full response.",
                scale_1="Responses are robotic, excessively long, or heavily formatted with bullet lists.",
                scale_2="Responses are mostly formulaic with some natural moments, or consistently too long.",
                scale_3="Responses are acceptable but unremarkable in naturalness and length.",
                scale_4="Responses are natural and concise with minor formatting issues.",
                scale_5="Responses are concise (<80 words), natural, conversational, with no bullet lists.",
                high_signals=[
                    "Short, direct responses under 80 words",
                    "Natural conversational tone",
                    "No bullet lists or heavy markdown",
                ],
                low_signals=[
                    "Responses exceed 100 words",
                    "Bullet-list formatting in responses",
                    "Robotic or template-sounding phrasing",
                ],
                failure_modes=[
                    "Wall-of-text responses",
                    "Markdown formatting in voice context",
                ],
                outcome_critical=False,
            ),
        ],
    )
