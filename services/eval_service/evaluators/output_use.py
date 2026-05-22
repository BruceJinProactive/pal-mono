"""Output use evaluator — LLM judge-based process verification.

Checks whether the agent correctly used tool results in its subsequent
responses (e.g., confirming order details on success, acknowledging errors).
"""

from __future__ import annotations

from typing import Any

from services.eval_service._evaluators import EvaluatorResult
from services.eval_service.process_trace import (
    ActionType,
    AgentAction,
    EventType,
    ProcessTrace,
    get_text,
)
from services.eval_service.schema import OutputUseConstraint
from utils.log import logger


def _find_action_with_result(
    actions: list[tuple[int, AgentAction]], tool_name: str
) -> tuple[int | None, AgentAction | None]:
    """Find the first action matching tool_name that has a result."""
    for turn_index, action in actions:
        if action.action_type != ActionType.TOOL_CALL:
            continue
        action_tool = action.arguments.get("tool_name", "")
        if action_tool == tool_name and action.result is not None:
            return turn_index, action
    return None, None


async def _llm_judge_output_use(
    tool_name: str,
    tool_result: dict[str, Any] | None,
    agent_response: str,
    expected_behavior: str,
) -> dict[str, Any]:
    """Use LLM judge to evaluate agent's use of tool output.

    Reuses the pal-agents judge infrastructure.
    """
    from pal_agents.evals.judge import JudgeConfig, JudgeDimension, judge_conversation

    conversation = [
        {
            "role": "system",
            "content": (
                f"The agent called tool '{tool_name}' and received this result: "
                f"{tool_result}. "
                f"The agent then responded to the user."
            ),
        },
        {"role": "assistant", "content": agent_response},
    ]

    config = JudgeConfig(
        enabled=True,
        model="gpt-4.1-mini",
        threshold=0.7,
        rubric_name="Output use verification",
        use_case="Verify agent correctly uses tool output in response",
        dimensions=[
            JudgeDimension(
                name="output_use",
                weight=1.0,
                evaluation_question=(
                    f"Expected behavior: {expected_behavior}. "
                    "Did the agent's response correctly reflect the tool result?"
                ),
                why_it_matters="Agent must correctly communicate tool results to users",
                scale_1="Agent completely ignores or contradicts the tool result",
                scale_2="Agent partially reflects the result but with major gaps",
                scale_3="Agent acknowledges the result but misses important details",
                scale_4="Agent correctly reflects the result with minor omissions",
                scale_5="Agent perfectly communicates the tool result per expectations",
                high_signals=[
                    "Confirms key details from tool result",
                    "Natural communication",
                ],
                low_signals=["Ignores result", "Makes up information not in result"],
                failure_modes=["Contradicts tool result", "Claims success on error"],
                outcome_critical=False,
            ),
        ],
    )

    try:
        result = await judge_conversation(
            conversation=conversation,
            agent_id="output_use_eval",
            test_id="output_use_eval",
            config=config,
        )
        score = result.get("conversation_quality_score", 0.0)
        return {
            "passed": score >= 0.7,
            "score": score,
            "reasoning": result.get("overall_reasoning", ""),
        }
    except Exception as exc:
        logger.exception("Output use LLM judge failed")
        return {
            "passed": False,
            "score": 0.0,
            "reasoning": f"Judge error: {exc}",
        }


async def evaluate_output_use(
    trace: ProcessTrace,
    constraints: list[OutputUseConstraint],
) -> EvaluatorResult:
    """Evaluate output use constraints against a ProcessTrace.

    Args:
        trace: The process trace to evaluate.
        constraints: List of output use constraints from the scenario.

    Returns:
        EvaluatorResult with metric_name="output_use".
    """
    if not constraints:
        return EvaluatorResult(
            metric_name="output_use",
            score=1.0,
            passed=True,
            reason="No output use constraints defined",
        )

    actions = trace.get_actions()
    results: list[dict[str, Any]] = []

    for constraint in constraints:
        tool_turn, action = _find_action_with_result(actions, constraint.tool)

        if action is None:
            results.append(
                {
                    "tool": constraint.tool,
                    "passed": False,
                    "reason": "tool never called",
                    "score": 0.0,
                }
            )
            continue

        # The tool result is usually reflected in the same assistant turn that
        # triggered the tool call. Fall back to later turns for multi-message
        # traces.
        agent_msgs_after = [
            e
            for e in trace.get_events(EventType.AGENT_MESSAGE)
            if tool_turn is not None and e.turn_index >= tool_turn
        ]
        next_agent_msg = agent_msgs_after[0] if agent_msgs_after else None
        agent_response_text = get_text(next_agent_msg.content) if next_agent_msg else ""

        if not agent_response_text:
            results.append(
                {
                    "tool": constraint.tool,
                    "passed": False,
                    "reason": "no agent response after tool call",
                    "score": 0.0,
                }
            )
            continue

        # Determine expected behavior based on result status
        if action.result_status == "error":
            expected_behavior = constraint.on_error or "Agent acknowledges the error"
        else:
            expected_behavior = constraint.on_success or "Agent confirms the result"

        judgment = await _llm_judge_output_use(
            tool_name=action.arguments.get("tool_name", constraint.tool),
            tool_result=action.result,
            agent_response=agent_response_text,
            expected_behavior=expected_behavior,
        )

        results.append(
            {
                "tool": constraint.tool,
                "passed": judgment["passed"],
                "reason": judgment["reasoning"],
                "score": judgment["score"],
            }
        )

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    score = sum(r["score"] for r in results) / total if total > 0 else 0.0

    return EvaluatorResult(
        metric_name="output_use",
        score=score,
        passed=all(r["passed"] for r in results),
        reason=f"{passed_count}/{total} output use constraints passed",
        raw_output={"constraints": results},
    )
