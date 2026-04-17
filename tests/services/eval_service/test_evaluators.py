"""Tests for the evaluator orchestrator (_evaluators.py)."""

from unittest.mock import AsyncMock, patch

import pytest

from services.eval_service._evaluators import (
    ConversationRecord,
    EvaluatorResult,
    _should_run_tool_call,
    evaluate_scenario,
)
from services.eval_service.schema import EvalScenario, ExpectedToolCall

JUDGE_MODULE = "services.eval_service.evaluators.judge_adapter"


def _make_scenario(**overrides: object) -> EvalScenario:
    defaults = {
        "scenario_id": "test-scenario",
        "scenario": "Test scenario description",
        "test_category": "general",
        "user_turns": ["Hello"],
        "expected_tool_calls": [],
        "context": [],
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


def _mock_task_completion() -> AsyncMock:
    return AsyncMock(
        return_value=EvaluatorResult(
            metric_name="task_completion",
            score=0.9,
            passed=True,
            reason="OK",
        )
    )


class TestShouldRunEvaluator:
    def test_tool_call_runs_when_expected_tools(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[ExpectedToolCall(tool="query_hours")]
        )
        assert _should_run_tool_call(scenario) is True

    def test_tool_call_skips_when_no_expected_tools(self) -> None:
        scenario = _make_scenario(expected_tool_calls=[])
        assert _should_run_tool_call(scenario) is False


class TestEvaluateScenario:
    @pytest.mark.asyncio
    async def test_returns_tool_call_result_when_expected(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[ExpectedToolCall(tool="query_hours")]
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["Our hours are 9am-5pm"],
            tool_calls=[{"tool_name": "query_hours"}],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "tool_call_accuracy" in metric_names
        assert "task_completion" in metric_names
        tool_result = next(r for r in results if r.metric_name == "tool_call_accuracy")
        assert tool_result.passed is True

    @pytest.mark.asyncio
    async def test_returns_tool_call_args_result_when_args_present(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[
                ExpectedToolCall(
                    tool="toast.validate_order_intent",
                    args={
                        "customer": {"first_name": "John"},
                        "items": [{"item_name": "Pizza", "quantity": 1}],
                    },
                )
            ]
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["Order confirmed"],
            tool_calls=[
                {
                    "type": "tool_call",
                    "payload": {
                        "tool_name": "toast.validate_order_intent",
                        "arguments": {
                            "customer": {"first_name": "John"},
                            "items": [{"item_name": "Pizza", "quantity": 1}],
                        },
                    },
                }
            ],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "tool_call_accuracy" in metric_names

        tool_result = next(r for r in results if r.metric_name == "tool_call_accuracy")
        assert tool_result.passed is True
        assert tool_result.score == 1.0

    @pytest.mark.asyncio
    async def test_judge_always_runs(self) -> None:
        """task_completion judge runs even with no tool calls or context."""
        scenario = _make_scenario(
            expected_tool_calls=[],
            context=[],
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["Hello"],
            turns=[{"user": "Hi", "assistant": "Hello"}],
        )

        mock_task = _mock_task_completion()

        with patch(f"{JUDGE_MODULE}.evaluate_task_completion", mock_task):
            results = await evaluate_scenario(record)

        assert len(results) == 1
        assert results[0].metric_name == "task_completion"
        mock_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_task_completion_runs_for_single_turn(self) -> None:
        """task_completion runs even on single-turn conversations."""
        scenario = _make_scenario(
            user_turns=["Hello"],
            context=[],
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["Hi there!"],
            turns=[{"user": "Hello", "assistant": "Hi there!"}],
        )

        mock_task = _mock_task_completion()

        with patch(f"{JUDGE_MODULE}.evaluate_task_completion", mock_task):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "task_completion" in metric_names
