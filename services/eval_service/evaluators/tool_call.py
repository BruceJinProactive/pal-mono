"""E1: Tool Call Verification evaluator.

Deterministic comparison of expected vs actual tool calls.
No LLM needed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services.eval_service._evaluators import EvaluatorResult


def evaluate_tool_calls(
    expected_tool_calls: Sequence[Mapping[str, Any]],
    actual_tool_calls: Sequence[Mapping[str, Any]],
) -> EvaluatorResult:
    """Compare expected tool calls against actual ones.

    Matching is by tool name. A call is "matched" if the expected tool name
    appears in the actual calls list. Argument matching is not enforced
    (tool names are the primary signal).

    Args:
        expected_tool_calls: List of dicts with at least a "tool" key.
        actual_tool_calls: List of dicts with at least a "tool_name" or "tool" key.

    Returns:
        EvaluatorResult with score = matched / expected, passed = score >= 1.0.
    """
    if not expected_tool_calls:
        return EvaluatorResult(
            metric_name="tool_call_verification",
            score=1.0,
            passed=True,
            reason="No tool calls expected",
        )

    actual_counts = Counter(
        str(tc.get("tool_name") or tc.get("tool", "")) for tc in actual_tool_calls
    )
    expected_counts = Counter(str(tc.get("tool", "")) for tc in expected_tool_calls)

    matched = sum(
        min(actual_counts[name], count) for name, count in expected_counts.items()
    )
    missing = [
        name
        for name, count in expected_counts.items()
        for _ in range(max(count - actual_counts.get(name, 0), 0))
    ]
    unexpected = sorted((actual_counts - expected_counts).elements())

    total = len(expected_tool_calls)
    score = matched / total if total > 0 else 1.0
    passed = score >= 1.0

    parts: list[str] = [f"Matched {matched}/{total} expected tool calls."]
    if missing:
        parts.append(f"Missing: {missing}")
    if unexpected:
        parts.append(f"Unexpected: {unexpected}")

    return EvaluatorResult(
        metric_name="tool_call_verification",
        score=score,
        passed=passed,
        reason=" ".join(parts),
    )
