"""Tests for the evaluator orchestrator (_evaluators.py)."""

from unittest.mock import AsyncMock, patch

import pytest

from services.eval_service._evaluators import (
    ConversationRecord,
    EvaluatorResult,
    _should_run_faithfulness,
    _should_run_task_completion,
    _should_run_tool_call,
    evaluate_scenario,
)
from services.eval_service.schema import EvalScenario, ExpectedToolCall

ADAPTER_MODULE = "services.eval_service.evaluators.deepeval_adapter"


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


class TestShouldRunEvaluator:
    def test_tool_call_runs_when_expected_tools(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[ExpectedToolCall(tool="query_hours")]
        )
        assert _should_run_tool_call(scenario) is True

    def test_tool_call_skips_when_no_expected_tools(self) -> None:
        scenario = _make_scenario(expected_tool_calls=[])
        assert _should_run_tool_call(scenario) is False

    def test_faithfulness_runs_when_context(self) -> None:
        scenario = _make_scenario(context=["Menu: Pizza $10"])
        assert _should_run_faithfulness(scenario) is True

    def test_faithfulness_skips_when_no_context(self) -> None:
        scenario = _make_scenario(context=[])
        assert _should_run_faithfulness(scenario) is False

    def test_task_completion_runs_for_multi_turn(self) -> None:
        scenario = _make_scenario(user_turns=["Hello", "What are your hours?"])
        assert _should_run_task_completion(scenario) is True

    def test_task_completion_skips_for_single_turn(self) -> None:
        scenario = _make_scenario(user_turns=["Hello"])
        assert _should_run_task_completion(scenario) is False


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

        with (
            patch(
                f"{ADAPTER_MODULE}.evaluate_faithfulness",
                new_callable=AsyncMock,
            ),
            patch(
                f"{ADAPTER_MODULE}.evaluate_responsive",
                new_callable=AsyncMock,
                return_value=EvaluatorResult(
                    metric_name="responsive",
                    score=1.0,
                    passed=True,
                    reason="OK",
                ),
            ),
            patch(
                f"{ADAPTER_MODULE}.evaluate_voice_appropriate",
                new_callable=AsyncMock,
                return_value=EvaluatorResult(
                    metric_name="voice_appropriate",
                    score=1.0,
                    passed=True,
                    reason="OK",
                ),
            ),
        ):
            results = await evaluate_scenario(record)

        assert len(results) >= 1
        tool_result = next(
            r for r in results if r.metric_name == "tool_call_verification"
        )
        assert tool_result.passed is True

    @pytest.mark.asyncio
    async def test_skips_all_when_no_triggers(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[],
            context=[],
            test_category="general",
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=[],
        )

        results = await evaluate_scenario(record)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_deepeval_metrics_run_in_parallel_with_context(self) -> None:
        scenario = _make_scenario(context=["Menu: Pizza $10, Pasta $12"])
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["We have Pizza for $10"],
            turns=[{"user": "What do you have?", "assistant": "We have Pizza for $10"}],
        )

        mock_faithfulness = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="faithfulness",
                score=1.0,
                passed=True,
                reason="All claims verified",
            )
        )
        mock_responsive = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="responsive",
                score=0.9,
                passed=True,
                reason="Addressed question",
            )
        )
        mock_voice = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="voice_appropriate",
                score=0.8,
                passed=True,
                reason="Natural tone",
            )
        )

        with (
            patch(f"{ADAPTER_MODULE}.evaluate_faithfulness", mock_faithfulness),
            patch(f"{ADAPTER_MODULE}.evaluate_responsive", mock_responsive),
            patch(f"{ADAPTER_MODULE}.evaluate_voice_appropriate", mock_voice),
        ):
            results = await evaluate_scenario(record)

        assert len(results) == 3
        metric_names = {r.metric_name for r in results}
        assert "faithfulness" in metric_names
        assert "responsive" in metric_names
        assert "voice_appropriate" in metric_names

    @pytest.mark.asyncio
    async def test_task_completion_runs_for_multi_turn(self) -> None:
        scenario = _make_scenario(
            user_turns=["Hello", "What are your hours?"],
            context=[],
        )
        record = ConversationRecord(
            scenario=scenario,
            agent_responses=["Hi there!", "We're open 9am-5pm"],
            turns=[
                {"user": "Hello", "assistant": "Hi there!"},
                {"user": "What are your hours?", "assistant": "We're open 9am-5pm"},
            ],
        )

        mock_responsive = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="responsive", score=1.0, passed=True, reason="OK"
            )
        )
        mock_voice = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="voice_appropriate", score=1.0, passed=True, reason="OK"
            )
        )
        mock_task = AsyncMock(
            return_value=EvaluatorResult(
                metric_name="task_completion", score=0.9, passed=True, reason="Complete"
            )
        )

        with (
            patch(f"{ADAPTER_MODULE}.evaluate_responsive", mock_responsive),
            patch(f"{ADAPTER_MODULE}.evaluate_voice_appropriate", mock_voice),
            patch(f"{ADAPTER_MODULE}.evaluate_task_completion", mock_task),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "task_completion" in metric_names
        assert "responsive" in metric_names
        assert "voice_appropriate" in metric_names
