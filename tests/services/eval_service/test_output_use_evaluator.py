"""Tests for the output use evaluator."""

from unittest.mock import AsyncMock, patch

import pytest

from services.eval_service.evaluators.output_use import (
    _find_action_with_result,
    evaluate_output_use,
)
from services.eval_service.process_trace import (
    ActionType,
    AgentAction,
    EventType,
    ProcessTrace,
    TextContent,
    TraceEvent,
)
from services.eval_service.schema import OutputUseConstraint

JUDGE_MODULE = "pal_agents.evals.judge"


def _make_trace_with_tool_and_response(
    tool_name: str,
    tool_result: dict | None,
    result_status: str | None,
    agent_response: str,
    tool_turn: int = 1,
    response_turn: int = 2,
) -> ProcessTrace:
    """Create a trace with a tool call followed by an agent response."""
    events = [
        TraceEvent(
            event_type=EventType.USER_MESSAGE,
            turn_index=0,
            content=TextContent(text="Do something"),
        ),
        TraceEvent(
            event_type=EventType.ACTION,
            turn_index=tool_turn,
            actions=[
                AgentAction(
                    action_type=ActionType.TOOL_CALL,
                    arguments={"tool_name": tool_name, "item": "pizza"},
                    result=tool_result,
                    result_status=result_status,
                )
            ],
        ),
        TraceEvent(
            event_type=EventType.AGENT_MESSAGE,
            turn_index=response_turn,
            content=TextContent(text=agent_response),
        ),
    ]
    return ProcessTrace(scenario_id="test", driver_mode="http", events=events)


class TestFindActionWithResult:
    def test_finds_matching_action(self) -> None:
        trace = _make_trace_with_tool_and_response(
            "create_order", {"order_id": "123"}, "success", "Order placed!"
        )
        actions = trace.get_actions()
        turn_index, action = _find_action_with_result(actions, "create_order")
        assert turn_index == 1
        assert action is not None
        assert action.arguments["tool_name"] == "create_order"

    def test_returns_none_for_missing_tool(self) -> None:
        trace = _make_trace_with_tool_and_response(
            "create_order", {"order_id": "123"}, "success", "Done"
        )
        actions = trace.get_actions()
        turn_index, action = _find_action_with_result(actions, "nonexistent")
        assert turn_index is None
        assert action is None

    def test_skips_matching_action_without_result(self) -> None:
        events = [
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=1,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": "create_order"},
                        result=None,
                    )
                ],
            ),
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=2,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": "create_order"},
                        result={"order_id": "123"},
                    )
                ],
            ),
        ]
        trace = ProcessTrace(scenario_id="test", driver_mode="http", events=events)
        actions = trace.get_actions()

        turn_index, action = _find_action_with_result(actions, "create_order")

        assert turn_index == 2
        assert action is not None
        assert action.arguments["tool_name"] == "create_order"
        assert action.result == {"order_id": "123"}


class TestEvaluateOutputUse:
    @pytest.mark.asyncio
    async def test_no_constraints_passes(self) -> None:
        trace = ProcessTrace(scenario_id="test", driver_mode="http", events=[])
        result = await evaluate_output_use(trace, [])
        assert result.passed is True
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_tool_never_called_fails(self) -> None:
        trace = ProcessTrace(scenario_id="test", driver_mode="http", events=[])
        constraints = [
            OutputUseConstraint(
                tool="missing_tool",
                on_success="Confirm order",
            )
        ]
        result = await evaluate_output_use(trace, constraints)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_no_agent_response_after_tool_fails(self) -> None:
        events = [
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=1,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": "create_order"},
                        result={"order_id": "123"},
                        result_status="success",
                    )
                ],
            ),
        ]
        trace = ProcessTrace(scenario_id="test", driver_mode="http", events=events)
        constraints = [OutputUseConstraint(tool="create_order", on_success="Confirm")]
        result = await evaluate_output_use(trace, constraints)
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_same_turn_agent_response_is_evaluated(self) -> None:
        events = [
            TraceEvent(
                event_type=EventType.AGENT_MESSAGE,
                turn_index=0,
                content=TextContent(text="Order #123 confirmed."),
            ),
            TraceEvent(
                event_type=EventType.ACTION,
                turn_index=0,
                actions=[
                    AgentAction(
                        action_type=ActionType.TOOL_CALL,
                        arguments={"tool_name": "create_order"},
                        result={"order_id": "123"},
                        result_status="success",
                    )
                ],
            ),
        ]
        trace = ProcessTrace(scenario_id="test", driver_mode="http", events=events)
        constraints = [OutputUseConstraint(tool="create_order", on_success="Confirm")]

        mock_judge = AsyncMock(
            return_value={
                "conversation_quality_score": 1.0,
                "conversation_quality_passed": True,
                "overall_reasoning": "Used result",
            }
        )

        with patch(f"{JUDGE_MODULE}.judge_conversation", mock_judge):
            result = await evaluate_output_use(trace, constraints)

        assert result.passed is True
        mock_judge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_case_calls_judge(self) -> None:
        trace = _make_trace_with_tool_and_response(
            "create_order",
            {"order_id": "123", "total": "$15.99"},
            "success",
            "Your order #123 is confirmed! Total: $15.99",
        )
        constraints = [
            OutputUseConstraint(
                tool="create_order",
                on_success="Agent confirms order details and total",
            )
        ]

        mock_judge = AsyncMock(
            return_value={
                "conversation_quality_score": 0.9,
                "conversation_quality_passed": True,
                "overall_reasoning": "Agent correctly confirmed order details",
            }
        )

        with patch(f"{JUDGE_MODULE}.judge_conversation", mock_judge):
            result = await evaluate_output_use(trace, constraints)

        assert result.passed is True
        assert result.score > 0.7
        mock_judge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_case_uses_on_error(self) -> None:
        trace = _make_trace_with_tool_and_response(
            "create_order",
            {"error": "Payment failed"},
            "error",
            "Sorry, the order could not be placed due to a payment issue.",
        )
        constraints = [
            OutputUseConstraint(
                tool="create_order",
                on_success="Confirm order",
                on_error="Acknowledge failure and offer retry",
            )
        ]

        mock_judge = AsyncMock(
            return_value={
                "conversation_quality_score": 0.85,
                "conversation_quality_passed": True,
                "overall_reasoning": "Agent acknowledged the error",
            }
        )

        with patch(f"{JUDGE_MODULE}.judge_conversation", mock_judge):
            result = await evaluate_output_use(trace, constraints)

        assert result.passed is True
        # Verify the judge was called with on_error behavior
        call_kwargs = mock_judge.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert (
            "failure" in config.dimensions[0].evaluation_question.lower()
            or "Acknowledge" in config.dimensions[0].evaluation_question
        )

    @pytest.mark.asyncio
    async def test_judge_failure_graceful(self) -> None:
        trace = _make_trace_with_tool_and_response(
            "create_order",
            {"order_id": "123"},
            "success",
            "Order placed!",
        )
        constraints = [OutputUseConstraint(tool="create_order", on_success="Confirm")]

        mock_judge = AsyncMock(side_effect=Exception("API error"))

        with patch(f"{JUDGE_MODULE}.judge_conversation", mock_judge):
            result = await evaluate_output_use(trace, constraints)

        assert result.passed is False
        assert result.score == 0.0
