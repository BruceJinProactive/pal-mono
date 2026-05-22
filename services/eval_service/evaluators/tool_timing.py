"""Tool timing evaluator — deterministic process verification.

Checks that tools are called in the correct order relative to each other
and that required parameters were collected from the user before tool invocation.
"""

from __future__ import annotations

import re
from typing import Any

from services.eval_service._evaluators import EvaluatorResult
from services.eval_service.process_trace import (
    ActionType,
    AgentAction,
    EventType,
    ProcessTrace,
    get_text,
)
from services.eval_service.schema import ToolTimingConstraint

_GENERIC_PARAM_SEGMENTS = {"customer", "user", "order", "data", "details", "info"}


def _find_action_turn(
    actions: list[tuple[int, AgentAction]], tool_name: str
) -> int | None:
    """Find the turn_index of the first action matching tool_name."""
    for turn_index, action in actions:
        if action.action_type != ActionType.TOOL_CALL:
            continue
        action_tool = action.arguments.get("tool_name", "")
        if action_tool == tool_name:
            return turn_index
    return None


def _param_value_in_text(param_name: str, text: str) -> bool:
    """Check if a parameter concept is discussed in user text.

    Uses heuristics: checks if any word from the param name path appears in
    the text, or if common synonyms/indicators are present.
    """
    if not text:
        return False
    text_lower = text.lower()

    segments = [
        segment.lower()
        for segment in re.split(r"[._\[\]]+", param_name)
        if len(segment) >= 3
    ]
    if not segments:
        return False

    leaf = segments[-1]
    if re.search(rf"\b{re.escape(leaf)}\b", text_lower):
        return True

    for segment in segments[:-1]:
        if segment in _GENERIC_PARAM_SEGMENTS:
            continue
        if re.search(rf"\b{re.escape(segment)}\b", text_lower):
            return True
    return False


def evaluate_tool_timing(
    trace: ProcessTrace,
    constraints: list[ToolTimingConstraint],
) -> EvaluatorResult:
    """Evaluate tool timing constraints against a ProcessTrace.

    Args:
        trace: The process trace to evaluate.
        constraints: List of timing constraints from the scenario.

    Returns:
        EvaluatorResult with metric_name="tool_timing".
    """
    if not constraints:
        return EvaluatorResult(
            metric_name="tool_timing",
            score=1.0,
            passed=True,
            reason="No tool timing constraints defined",
        )

    actions = trace.get_actions()
    results: list[dict[str, Any]] = []

    for constraint in constraints:
        tool_turn = _find_action_turn(actions, constraint.tool)

        if tool_turn is None:
            results.append(
                {
                    "constraint": f"{constraint.tool}",
                    "passed": False,
                    "reason": "tool never called",
                }
            )
            continue

        constraint_passed = True
        reasons: list[str] = []

        # must_precede check
        if constraint.must_precede:
            target_turn = _find_action_turn(actions, constraint.must_precede)
            if target_turn is None:
                constraint_passed = False
                reasons.append(
                    f"must_precede target '{constraint.must_precede}' never called"
                )
            elif tool_turn >= target_turn:
                constraint_passed = False
                reasons.append(
                    f"'{constraint.tool}' (turn {tool_turn}) did not precede "
                    f"'{constraint.must_precede}' (turn {target_turn})"
                )

        # must_follow check
        if constraint.must_follow:
            target_turn = _find_action_turn(actions, constraint.must_follow)
            if target_turn is None:
                constraint_passed = False
                reasons.append(
                    f"must_follow target '{constraint.must_follow}' never called"
                )
            elif tool_turn <= target_turn:
                constraint_passed = False
                reasons.append(
                    f"'{constraint.tool}' (turn {tool_turn}) did not follow "
                    f"'{constraint.must_follow}' (turn {target_turn})"
                )

        # requires_params check
        if constraint.requires_params:
            user_events = [
                e
                for e in trace.get_events(EventType.USER_MESSAGE)
                if e.turn_index < tool_turn
            ]
            for param in constraint.requires_params:
                found = any(
                    _param_value_in_text(param, get_text(e.content) or "")
                    for e in user_events
                )
                if not found:
                    constraint_passed = False
                    reasons.append(
                        f"required param '{param}' not found in user messages "
                        f"before turn {tool_turn}"
                    )

        results.append(
            {
                "constraint": f"{constraint.tool}",
                "passed": constraint_passed,
                "reason": "; ".join(reasons) if reasons else "ok",
            }
        )

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    score = passed_count / total if total > 0 else 1.0

    return EvaluatorResult(
        metric_name="tool_timing",
        score=score,
        passed=all(r["passed"] for r in results),
        reason=f"{passed_count}/{total} timing constraints passed",
        raw_output={"constraints": results},
    )
