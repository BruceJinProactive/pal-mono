"""Integration tests: process evaluators + existing eval pipeline.

Verifies that:
1. Existing evaluators are unaffected when expected_process is not defined
2. Process evaluators run only when expected_process is defined
3. Process evaluators produce expected output format
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.eval_service._evaluators import (
    ConversationRecord,
    EvaluatorResult,
    evaluate_scenario,
)
from services.eval_service.schema import (
    EvalScenario,
    ExpectedProcess,
    ExpectedToolCall,
    OutputUseConstraint,
    ToolTimingConstraint,
)

JUDGE_MODULE = "services.eval_service.evaluators.judge_adapter"
OUTPUT_JUDGE_MODULE = "pal_agents.evals.judge"


def _make_scenario(**overrides: object) -> EvalScenario:
    defaults = {
        "scenario_id": "integration-test",
        "scenario": "Integration test scenario",
        "test_category": "general",
        "user_turns": ["Hello"],
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


class TestExistingPipelineUnaffected:
    """Verify existing evaluators work when expected_process is None."""

    @pytest.mark.asyncio
    async def test_no_expected_process_no_process_evaluators(self) -> None:
        scenario = _make_scenario(expected_process=None)
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "task_completion" in metric_names
        assert "tool_timing" not in metric_names
        assert "param_collection" not in metric_names
        assert "output_use" not in metric_names

    @pytest.mark.asyncio
    async def test_tool_call_evaluator_still_works(self) -> None:
        scenario = _make_scenario(
            expected_tool_calls=[ExpectedToolCall(tool="query_hours")],
            expected_process=None,
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "What hours?", "assistant": "9-5"}],
            agent_responses=["9-5"],
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
        assert "tool_timing" not in metric_names


class TestProcessEvaluatorsIntegration:
    """Verify process evaluators activate when expected_process is defined."""

    @pytest.mark.asyncio
    async def test_tool_timing_runs_with_expected_process(self) -> None:
        scenario = _make_scenario(
            expected_process=ExpectedProcess(
                tool_timing=[
                    ToolTimingConstraint(
                        tool="get_toast_item_details_v3",
                        must_precede="toast_takeout_create_order_v1",
                    ),
                ],
            ),
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "I want a pizza", "assistant": "Let me look that up"},
                {"user": "Large", "assistant": "Order placed!"},
            ],
            agent_responses=["Let me look that up", "Order placed!"],
            tool_calls=[
                {
                    "payload": {
                        "tool_name": "get_toast_item_details_v3",
                        "arguments": {"items": [{"item_name": "Pizza"}]},
                    }
                },
                {
                    "payload": {
                        "tool_name": "toast_takeout_create_order_v1",
                        "arguments": {"items": [{"item_name": "Pizza"}]},
                    }
                },
            ],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "tool_timing" in metric_names
        assert "param_collection" in metric_names
        assert "task_completion" in metric_names

    @pytest.mark.asyncio
    async def test_output_use_runs_with_constraints(self) -> None:
        scenario = _make_scenario(
            expected_process=ExpectedProcess(
                output_use=[
                    OutputUseConstraint(
                        tool="create_order",
                        on_success="Confirm order details",
                    ),
                ],
            ),
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Order pizza", "assistant": "Placing order"},
                {"user": "", "assistant": "Order #123 confirmed!"},
            ],
            agent_responses=["Placing order", "Order #123 confirmed!"],
            tool_calls=[
                {
                    "tool_name": "create_order",
                    "arguments": {"item": "pizza"},
                    "result": {"order_id": "123"},
                    "status": "success",
                }
            ],
        )

        mock_output_judge = AsyncMock(
            return_value={
                "conversation_quality_score": 0.9,
                "conversation_quality_passed": True,
                "overall_reasoning": "Correct",
            }
        )

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_task_completion(),
            ),
            patch(
                f"{OUTPUT_JUDGE_MODULE}.judge_conversation",
                mock_output_judge,
            ),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "output_use" in metric_names
        assert "param_collection" in metric_names

    @pytest.mark.asyncio
    async def test_output_use_error_does_not_abort_pipeline(self) -> None:
        scenario = _make_scenario(
            expected_process=ExpectedProcess(
                output_use=[
                    OutputUseConstraint(
                        tool="create_order",
                        on_success="Confirm order details",
                    ),
                ],
            ),
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Order pizza", "assistant": "Placing order"},
                {"user": "", "assistant": "Order confirmed!"},
            ],
            agent_responses=["Placing order", "Order confirmed!"],
            tool_calls=[
                {
                    "tool_name": "create_order",
                    "arguments": {"item": "pizza"},
                    "result": {"order_id": "123"},
                    "status": "success",
                }
            ],
        )

        output_use_mock = AsyncMock(side_effect=RuntimeError("judge unavailable"))

        with (
            patch(
                f"{JUDGE_MODULE}.evaluate_task_completion",
                _mock_task_completion(),
            ),
            patch(
                "services.eval_service.evaluators.output_use.evaluate_output_use",
                output_use_mock,
            ),
        ):
            results = await evaluate_scenario(record)

        output_use_mock.assert_awaited_once()
        results_by_metric = {r.metric_name: r for r in results}
        assert "task_completion" in results_by_metric
        assert results_by_metric["output_use"].passed is False
        assert "judge unavailable" in results_by_metric["output_use"].reason

    @pytest.mark.asyncio
    async def test_both_tool_call_and_process_evaluators(self) -> None:
        """Tool call accuracy and process evaluators can run together."""
        scenario = _make_scenario(
            expected_tool_calls=[
                ExpectedToolCall(tool="create_order"),
            ],
            expected_process=ExpectedProcess(
                tool_timing=[
                    ToolTimingConstraint(tool="create_order"),
                ],
            ),
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Order pizza", "assistant": "Done!"}],
            agent_responses=["Done!"],
            tool_calls=[{"tool_name": "create_order", "arguments": {"item": "pizza"}}],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "tool_call_accuracy" in metric_names
        assert "tool_timing" in metric_names
        assert "param_collection" in metric_names
        assert "task_completion" in metric_names


class TestVoiceModeProcessTrace:
    """Verify process trace works with voice ConversationRecord."""

    @pytest.mark.asyncio
    async def test_voice_record_builds_trace(self) -> None:
        scenario = _make_scenario(
            expected_process=ExpectedProcess(
                tool_timing=[
                    ToolTimingConstraint(tool="create_order"),
                ],
            ),
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[],
            agent_responses=[],
            is_voice=True,
            voice_transcript=[
                {
                    "role": "user",
                    "content": "I want a pizza",
                    "start_time": 0.0,
                    "end_time": 1.5,
                },
                {
                    "role": "assistant",
                    "content": "Order placed!",
                    "start_time": 2.0,
                    "end_time": 3.0,
                },
            ],
            tool_calls=[{"tool_name": "create_order", "arguments": {"item": "pizza"}}],
        )

        with patch(
            f"{JUDGE_MODULE}.evaluate_task_completion",
            _mock_task_completion(),
        ):
            results = await evaluate_scenario(record)

        metric_names = {r.metric_name for r in results}
        assert "param_collection" in metric_names
