"""Parameter collection evaluator — deterministic process verification.

Checks whether tool call arguments were actually collected from the user
(present in user messages) or potentially hallucinated by the agent.
"""

from __future__ import annotations

from typing import Any

from services.eval_service._evaluators import EvaluatorResult
from services.eval_service.process_trace import (
    ActionType,
    EventType,
    ProcessTrace,
    get_text,
)

# Parameters that are system-generated and should not be checked
_SYSTEM_PARAMS = frozenset(
    {
        "tool_name",
        "request_id",
        "session_id",
        "conversation_id",
        "timestamp",
        "channel",
        "account_id",
        "project_id",
    }
)


def _is_user_provided_param(param_path: str) -> bool:
    """Determine if a parameter is user-provided vs system-generated."""
    last_segment = param_path.split(".")[-1]
    return last_segment not in _SYSTEM_PARAMS


def _flatten_args(args: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten nested dict into (dotted_path, leaf_value) pairs."""
    results: list[tuple[str, Any]] = []
    for key, value in args.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            results.extend(_flatten_args(value, path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                item_path = f"{path}[{i}]"
                if isinstance(item, dict):
                    results.extend(_flatten_args(item, item_path))
                else:
                    results.append((item_path, item))
        else:
            results.append((path, value))
    return results


def _fuzzy_match(value: str, text: str) -> bool:
    """Check if a value appears in the user text (case-insensitive).

    Handles common transformations: phone normalization, name matching, etc.
    """
    if not value or not text:
        return False

    value_lower = value.lower().strip()
    text_lower = text.lower()

    # Direct substring match
    if value_lower in text_lower:
        return True

    # Digits-only match (for phone numbers)
    import re

    value_digits = re.sub(r"\D", "", value_lower)
    if value_digits and len(value_digits) >= 4:
        text_digits = re.sub(r"\D", "", text_lower)
        if value_digits in text_digits:
            return True

    return False


def evaluate_param_collection(
    trace: ProcessTrace,
    tool_calls: list[dict[str, Any]],
) -> EvaluatorResult:
    """Evaluate whether tool call parameters were collected from the user.

    Args:
        trace: The process trace with conversation events.
        tool_calls: Raw tool calls from ConversationRecord.

    Returns:
        EvaluatorResult with metric_name="param_collection".
    """
    actions = trace.get_actions()

    if not actions:
        return EvaluatorResult(
            metric_name="param_collection",
            score=1.0,
            passed=True,
            reason="No tool calls to verify",
        )

    results: list[dict[str, Any]] = []

    for turn_index, action in actions:
        if action.action_type != ActionType.TOOL_CALL:
            continue

        # Get all user messages before this action
        user_events = [
            e
            for e in trace.get_events(EventType.USER_MESSAGE)
            if e.turn_index < turn_index
        ]
        user_texts = [get_text(e.content) or "" for e in user_events]
        all_user_text = " ".join(user_texts)

        # Check each arg value
        tool_name = action.arguments.get("tool_name", "unknown")
        args_without_tool_name = {
            k: v for k, v in action.arguments.items() if k != "tool_name"
        }
        flat_args = _flatten_args(args_without_tool_name)

        for param_path, value in flat_args:
            if not _is_user_provided_param(param_path):
                continue

            # Skip non-string/numeric values
            if not isinstance(value, (str, int, float)):
                continue

            str_value = str(value)
            if not str_value or str_value in ("True", "False", "None"):
                continue

            found_in_user = _fuzzy_match(str_value, all_user_text)
            results.append(
                {
                    "tool": tool_name,
                    "param": param_path,
                    "value": str_value,
                    "source": "user" if found_in_user else "hallucinated",
                }
            )

    if not results:
        return EvaluatorResult(
            metric_name="param_collection",
            score=1.0,
            passed=True,
            reason="No user-provided parameters to verify",
        )

    hallucinated = [r for r in results if r["source"] == "hallucinated"]
    score = 1.0 - (len(hallucinated) / len(results))

    reason_parts: list[str] = [
        f"{len(results) - len(hallucinated)}/{len(results)} params traced to user"
    ]
    if hallucinated:
        flagged = [f"{h['param']}={h['value']}" for h in hallucinated[:3]]
        reason_parts.append(f"flagged: {flagged}")

    return EvaluatorResult(
        metric_name="param_collection",
        score=score,
        passed=len(hallucinated) == 0,
        reason="; ".join(reason_parts),
        raw_output={
            "total_params": len(results),
            "hallucinated_count": len(hallucinated),
            "details": results,
        },
    )
