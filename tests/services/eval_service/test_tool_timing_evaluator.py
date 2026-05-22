"""Tests for the tool timing evaluator."""

from services.eval_service.evaluators.tool_timing import (
    _find_action_turn,
    _param_value_in_text,
    evaluate_tool_timing,
)
from services.eval_service.process_trace import (
    ActionType,
    AgentAction,
    EventType,
    ProcessTrace,
    TextContent,
    TraceEvent,
)
from services.eval_service.schema import ToolTimingConstraint


def _make_trace_with_tools(
    tool_sequence: list[tuple[str, int]],
    user_messages: list[tuple[str, int]] | None = None,
) -> ProcessTrace:
    """Create a trace with tool calls at specified turns.

    Args:
        tool_sequence: list of (tool_name, turn_index) pairs.
        user_messages: optional list of (text, turn_index) pairs for user messages.
    """
    events: list[TraceEvent] = []

    if user_messages:
        for text, turn_idx in user_messages:
            events.append(
                TraceEvent(
                    event_type=EventType.USER_MESSAGE,
                    turn_index=turn_idx,
                    content=TextContent(text=text),
                )
            )

    for tool_name, turn_idx in tool_sequence:
        events.append(
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=turn_idx,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": tool_name},
                    )
                ],
            )
        )

    return ProcessTrace(scenario_id="test", driver_mode="http", events=events)


class TestFindActionTurn:
    def test_finds_existing_tool(self) -> None:
        trace = _make_trace_with_tools([("tool_a", 0), ("tool_b", 1)])
        actions = trace.get_actions()
        assert _find_action_turn(actions, "tool_a") == 0
        assert _find_action_turn(actions, "tool_b") == 1

    def test_returns_none_for_missing_tool(self) -> None:
        trace = _make_trace_with_tools([("tool_a", 0)])
        actions = trace.get_actions()
        assert _find_action_turn(actions, "nonexistent") is None


class TestParamValueInText:
    def test_simple_match(self) -> None:
        assert (
            _param_value_in_text("customer.first_name", "My first name is Sarah")
            is True
        )

    def test_segment_match(self) -> None:
        assert _param_value_in_text("customer.phone", "My phone is 555-1234") is True

    def test_generic_container_segment_does_not_match(self) -> None:
        assert _param_value_in_text("customer.phone", "The customer is here") is False

    def test_no_match(self) -> None:
        assert _param_value_in_text("customer.phone", "I want a pizza") is False

    def test_underscore_to_space(self) -> None:
        assert _param_value_in_text("first_name", "my first name is tom") is True

    def test_empty_text(self) -> None:
        assert _param_value_in_text("name", "") is False

    def test_short_segments_skipped(self) -> None:
        # Segments < 3 chars are ignored to avoid false matches
        assert _param_value_in_text("a.b", "a b c") is False


class TestEvaluateToolTiming:
    def test_no_constraints_passes(self) -> None:
        trace = _make_trace_with_tools([])
        result = evaluate_tool_timing(trace, [])
        assert result.passed is True
        assert result.score == 1.0

    def test_must_precede_passes(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("get_toast_item_details_v3", 0),
                ("toast_takeout_create_order_v1", 2),
            ]
        )
        constraints = [
            ToolTimingConstraint(
                tool="get_toast_item_details_v3",
                must_precede="toast_takeout_create_order_v1",
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is True
        assert result.score == 1.0

    def test_must_precede_fails(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("toast_takeout_create_order_v1", 0),
                ("get_toast_item_details_v3", 2),
            ]
        )
        constraints = [
            ToolTimingConstraint(
                tool="get_toast_item_details_v3",
                must_precede="toast_takeout_create_order_v1",
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False
        assert result.score == 0.0

    def test_must_follow_passes(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("get_toast_item_details_v3", 0),
                ("toast_takeout_create_order_v1", 2),
            ]
        )
        constraints = [
            ToolTimingConstraint(
                tool="toast_takeout_create_order_v1",
                must_follow="get_toast_item_details_v3",
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is True

    def test_must_follow_fails(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("toast_takeout_create_order_v1", 0),
                ("get_toast_item_details_v3", 2),
            ]
        )
        constraints = [
            ToolTimingConstraint(
                tool="toast_takeout_create_order_v1",
                must_follow="get_toast_item_details_v3",
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False

    def test_tool_never_called(self) -> None:
        trace = _make_trace_with_tools([("other_tool", 0)])
        constraints = [
            ToolTimingConstraint(
                tool="missing_tool",
                must_precede="other_tool",
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False
        assert result.raw_output is not None
        assert "tool never called" in result.raw_output["constraints"][0]["reason"]

    def test_requires_params_passes(self) -> None:
        trace = _make_trace_with_tools(
            tool_sequence=[("create_order", 2)],
            user_messages=[
                ("My first name is Sarah", 0),
                ("My phone is 5551234567", 1),
            ],
        )
        constraints = [
            ToolTimingConstraint(
                tool="create_order",
                requires_params=["customer.first_name", "customer.phone"],
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is True

    def test_requires_params_fails_when_missing(self) -> None:
        trace = _make_trace_with_tools(
            tool_sequence=[("create_order", 1)],
            user_messages=[("I want a pizza", 0)],
        )
        constraints = [
            ToolTimingConstraint(
                tool="create_order",
                requires_params=["customer.phone"],
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False

    def test_requires_params_fails_with_only_container_token(self) -> None:
        trace = _make_trace_with_tools(
            tool_sequence=[("create_order", 1)],
            user_messages=[("The customer is ready to order", 0)],
        )
        constraints = [
            ToolTimingConstraint(
                tool="create_order",
                requires_params=["customer.phone"],
            )
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False

    def test_multiple_constraints_partial_pass(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("tool_a", 0),
                ("tool_b", 1),
            ]
        )
        constraints = [
            ToolTimingConstraint(tool="tool_a", must_precede="tool_b"),
            ToolTimingConstraint(tool="tool_b", must_precede="tool_a"),
        ]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False
        assert result.score == 0.5

    def test_same_turn_fails_must_precede(self) -> None:
        trace = _make_trace_with_tools(
            [
                ("tool_a", 1),
                ("tool_b", 1),
            ]
        )
        constraints = [ToolTimingConstraint(tool="tool_a", must_precede="tool_b")]
        result = evaluate_tool_timing(trace, constraints)
        assert result.passed is False
