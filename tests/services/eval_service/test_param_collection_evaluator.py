"""Tests for the param collection evaluator."""

from services.eval_service.evaluators.param_collection import (
    _flatten_args,
    _fuzzy_match,
    _is_user_provided_param,
    evaluate_param_collection,
)
from services.eval_service.process_trace import (
    ActionType,
    AgentAction,
    EventType,
    ProcessTrace,
    TextContent,
    TraceEvent,
)


def _make_trace(
    user_messages: list[tuple[str, int]],
    tool_calls: list[tuple[str, dict, int]],
) -> ProcessTrace:
    """Create a trace with user messages and tool calls.

    Args:
        user_messages: list of (text, turn_index) pairs.
        tool_calls: list of (tool_name, args_dict, turn_index) tuples.
    """
    events: list[TraceEvent] = []

    for text, turn_idx in user_messages:
        events.append(
            TraceEvent(
                event_type=EventType.USER_MESSAGE,
                turn_index=turn_idx,
                content=TextContent(text=text),
            )
        )

    for tool_name, args, turn_idx in tool_calls:
        events.append(
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=turn_idx,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": tool_name, **args},
                    )
                ],
            )
        )

    return ProcessTrace(scenario_id="test", driver_mode="http", events=events)


class TestFlattenArgs:
    def test_flat_dict(self) -> None:
        result = _flatten_args({"name": "Sarah", "age": 25})
        assert ("name", "Sarah") in result
        assert ("age", 25) in result

    def test_nested_dict(self) -> None:
        result = _flatten_args({"customer": {"first_name": "Sarah"}})
        assert ("customer.first_name", "Sarah") in result

    def test_list_values(self) -> None:
        result = _flatten_args({"items": ["pizza", "salad"]})
        assert ("items[0]", "pizza") in result
        assert ("items[1]", "salad") in result

    def test_nested_list_of_dicts(self) -> None:
        result = _flatten_args({"items": [{"name": "pizza"}]})
        assert ("items[0].name", "pizza") in result


class TestFuzzyMatch:
    def test_exact_substring(self) -> None:
        assert _fuzzy_match("Sarah", "My name is Sarah Miller") is True

    def test_case_insensitive(self) -> None:
        assert _fuzzy_match("sarah", "My name is Sarah") is True

    def test_phone_digits(self) -> None:
        assert _fuzzy_match("5551234567", "My phone is (555) 123-4567") is True

    def test_no_match(self) -> None:
        assert _fuzzy_match("pizza", "I want a burger") is False

    def test_empty_value(self) -> None:
        assert _fuzzy_match("", "some text") is False

    def test_empty_text(self) -> None:
        assert _fuzzy_match("value", "") is False


class TestIsUserProvidedParam:
    def test_user_param(self) -> None:
        assert _is_user_provided_param("customer.first_name") is True
        assert _is_user_provided_param("items[0].item_name") is True

    def test_system_param(self) -> None:
        assert _is_user_provided_param("tool_name") is False
        assert _is_user_provided_param("request_id") is False
        assert _is_user_provided_param("session_id") is False


class TestEvaluateParamCollection:
    def test_no_tool_calls_passes(self) -> None:
        trace = _make_trace(
            user_messages=[("Hello", 0)],
            tool_calls=[],
        )
        result = evaluate_param_collection(trace, [])
        assert result.passed is True
        assert result.score == 1.0

    def test_params_from_user_passes(self) -> None:
        trace = _make_trace(
            user_messages=[
                ("My name is Sarah Miller", 0),
                ("Phone is 5551234567", 1),
            ],
            tool_calls=[
                (
                    "create_order",
                    {
                        "customer": {
                            "first_name": "Sarah",
                            "phone": "5551234567",
                        }
                    },
                    2,
                ),
            ],
        )
        raw_tool_calls = [
            {
                "tool_name": "create_order",
                "arguments": {
                    "customer": {"first_name": "Sarah", "phone": "5551234567"}
                },
            }
        ]
        result = evaluate_param_collection(trace, raw_tool_calls)
        assert result.passed is True
        assert result.score == 1.0

    def test_hallucinated_param_fails(self) -> None:
        trace = _make_trace(
            user_messages=[("I want a pizza", 0)],
            tool_calls=[
                (
                    "create_order",
                    {"customer": {"first_name": "John"}},
                    1,
                ),
            ],
        )
        raw_tool_calls = [
            {
                "tool_name": "create_order",
                "arguments": {"customer": {"first_name": "John"}},
            }
        ]
        result = evaluate_param_collection(trace, raw_tool_calls)
        assert result.passed is False
        assert result.score < 1.0
        assert result.raw_output is not None
        assert result.raw_output["hallucinated_count"] > 0

    def test_mixed_params(self) -> None:
        trace = _make_trace(
            user_messages=[("My name is Sarah", 0)],
            tool_calls=[
                (
                    "create_order",
                    {
                        "customer": {
                            "first_name": "Sarah",
                            "last_name": "Unknown",
                        }
                    },
                    1,
                ),
            ],
        )
        raw_tool_calls = [
            {
                "tool_name": "create_order",
                "arguments": {
                    "customer": {"first_name": "Sarah", "last_name": "Unknown"}
                },
            }
        ]
        result = evaluate_param_collection(trace, raw_tool_calls)
        assert result.passed is False
        # Sarah is found, Unknown is not
        assert 0 < result.score < 1.0

    def test_params_after_tool_call_not_counted(self) -> None:
        """User messages AFTER the tool call should not validate params."""
        trace = _make_trace(
            user_messages=[
                ("Hello", 0),
                ("My name is Sarah", 2),  # After tool call
            ],
            tool_calls=[
                ("create_order", {"customer": {"first_name": "Sarah"}}, 1),
            ],
        )
        raw_tool_calls = [
            {
                "tool_name": "create_order",
                "arguments": {"customer": {"first_name": "Sarah"}},
            }
        ]
        result = evaluate_param_collection(trace, raw_tool_calls)
        assert result.passed is False
