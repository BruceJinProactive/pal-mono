"""Tests for the judge adapter (judge_adapter.py).

Covers:
- evaluate_task_completion: happy path, error result, exception, score/reason defaults
- Helper functions: _build_judge_conversation, _build_judge_config
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from services.eval_service._evaluators import ConversationRecord, EvaluatorResult
from services.eval_service.evaluators.judge_adapter import (
    _build_judge_config,
    _build_judge_conversation,
    evaluate_task_completion,
)
from services.eval_service.schema import EvalScenario

ADAPTER_MODULE = "services.eval_service.evaluators.judge_adapter"


def _make_scenario(**overrides: Any) -> EvalScenario:
    defaults: dict[str, Any] = {
        "scenario_id": "test",
        "scenario": "Test",
        "test_category": "general",
        "user_turns": ["Hello"],
        "expected_tool_calls": [],
        "context": [],
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


class TestEvaluateTaskCompletion:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result(self) -> None:
        scenario = _make_scenario(user_turns=["Hello", "What are your hours?"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi there"},
                {"user": "What are your hours?", "assistant": "We are open 9am-5pm"},
            ],
            agent_responses=["Hi there", "We are open 9am-5pm"],
        )
        judge_result = {
            "conversation_quality_score": 0.95,
            "conversation_quality_passed": True,
            "overall_reasoning": "Task completed successfully",
            "error": None,
        }

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            return_value=judge_result,
        ):
            result = await evaluate_task_completion(record)

        assert isinstance(result, EvaluatorResult)
        assert result.metric_name == "task_completion"
        assert result.score == 0.95
        assert result.passed is True
        assert result.reason == "Task completed successfully"
        assert result.raw_output == judge_result

    @pytest.mark.asyncio
    async def test_passes_conversation_and_config_to_judge(self) -> None:
        scenario = _make_scenario(
            scenario_id="order-test-001", user_turns=["Hi", "Bye"]
        )
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Bye", "assistant": "Goodbye"},
            ],
            agent_responses=["Hello", "Goodbye"],
        )
        judge_result = {
            "conversation_quality_score": 0.8,
            "conversation_quality_passed": True,
            "overall_reasoning": "Good",
            "error": None,
        }

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            return_value=judge_result,
        ) as mock_judge:
            await evaluate_task_completion(record)

        mock_judge.assert_awaited_once()
        call_kwargs = mock_judge.call_args[1]
        assert call_kwargs["agent_id"] == "order-test-001"
        assert call_kwargs["test_id"] == "order-test-001"
        assert len(call_kwargs["conversation"]) == 4

    @pytest.mark.asyncio
    async def test_error_in_judge_result_returns_failed(self) -> None:
        scenario = _make_scenario(user_turns=["Hi"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        judge_result = {
            "conversation_quality_score": 0.0,
            "conversation_quality_passed": False,
            "overall_reasoning": "",
            "error": "LLM call failed",
        }

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            return_value=judge_result,
        ):
            result = await evaluate_task_completion(record)

        assert result.metric_name == "task_completion"
        assert result.score == 0.0
        assert result.passed is False
        assert "Judge error: LLM call failed" in result.reason

    @pytest.mark.asyncio
    async def test_score_none_defaults_to_zero(self) -> None:
        scenario = _make_scenario(user_turns=["Hi"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        judge_result = {
            "conversation_quality_score": None,
            "conversation_quality_passed": True,
            "overall_reasoning": "OK",
            "error": None,
        }

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            return_value=judge_result,
        ):
            result = await evaluate_task_completion(record)

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reasoning_none_defaults_to_no_reasoning_provided(self) -> None:
        scenario = _make_scenario(user_turns=["Hi"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        judge_result = {
            "conversation_quality_score": 0.8,
            "conversation_quality_passed": True,
            "overall_reasoning": None,
            "error": None,
        }

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            return_value=judge_result,
        ):
            result = await evaluate_task_completion(record)

        assert result.reason == "No reasoning provided"

    @pytest.mark.asyncio
    async def test_judge_exception_returns_failed_result(self) -> None:
        scenario = _make_scenario(user_turns=["Hi"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )

        with patch(
            f"{ADAPTER_MODULE}.judge_conversation",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network timeout"),
        ):
            result = await evaluate_task_completion(record)

        assert result.metric_name == "task_completion"
        assert result.score == 0.0
        assert result.passed is False
        assert "failed" in result.reason


class TestBuildJudgeConversation:
    def test_empty_turns_returns_empty_list(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])
        result = _build_judge_conversation(record)
        assert result == []

    def test_single_turn_creates_two_messages(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hello", "assistant": "Hi there"}],
        )
        result = _build_judge_conversation(record)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi there"}

    def test_multiple_turns_creates_interleaved_messages(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi"},
                {"user": "What is the price?", "assistant": "Pizza is $10"},
            ],
        )
        result = _build_judge_conversation(record)
        assert len(result) == 4
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi"}
        assert result[2] == {"role": "user", "content": "What is the price?"}
        assert result[3] == {"role": "assistant", "content": "Pizza is $10"}

    def test_skips_empty_user_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "", "assistant": "Hi there"}],
        )
        result = _build_judge_conversation(record)
        assert len(result) == 1
        assert result[0] == {"role": "assistant", "content": "Hi there"}

    def test_skips_empty_assistant_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hello", "assistant": ""}],
        )
        result = _build_judge_conversation(record)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "Hello"}

    def test_skips_turn_with_missing_keys(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{}],
        )
        result = _build_judge_conversation(record)
        assert result == []


class TestBuildJudgeConfig:
    def test_returns_enabled_config(self) -> None:
        config = _build_judge_config()
        assert config.enabled is True

    def test_has_four_dimensions(self) -> None:
        config = _build_judge_config()
        assert len(config.dimensions) == 4

    def test_dimension_names(self) -> None:
        config = _build_judge_config()
        names = [d.name for d in config.dimensions]
        assert names == [
            "request_accuracy",
            "contextual_relevancy",
            "role_adherence",
            "conversation_quality",
        ]

    def test_request_accuracy_has_higher_weight(self) -> None:
        config = _build_judge_config()
        request_acc = config.dimensions[0]
        assert request_acc.weight == 2.0
        assert config.dimensions[1].weight == 1.0
        assert config.dimensions[2].weight == 1.0
        assert config.dimensions[3].weight == 1.0
