"""Tests for the DeepEval adapter (deepeval_adapter.py).

Covers:
- Happy path for each evaluate_* function
- Error path (metric.a_measure raises) for each evaluate_* function
- evaluate_faithfulness with context_override
- Helper functions: _first_user_message, _last_turn, _build_turns
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._evaluators import ConversationRecord, EvaluatorResult
from services.eval_service.evaluators.deepeval_adapter import (
    _build_turns,
    _first_user_message,
    _last_turn,
    evaluate_faithfulness,
    evaluate_responsive,
    evaluate_task_completion,
    evaluate_voice_appropriate,
)
from services.eval_service.schema import EvalScenario

ADAPTER_MODULE = "services.eval_service.evaluators.deepeval_adapter"


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


def _make_metric(
    score: float = 1.0, is_successful: bool = True, reason: str = "OK"
) -> MagicMock:
    """Build a mock DeepEval metric with a_measure, score, is_successful, and reason."""
    metric = MagicMock()
    metric.a_measure = AsyncMock()
    metric.score = score
    metric.is_successful = MagicMock(return_value=is_successful)
    metric.reason = reason
    return metric


class TestEvaluateFaithfulness:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result(self) -> None:
        scenario = _make_scenario(context=["Menu: Pizza $10"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "What do you have?", "assistant": "We have Pizza for $10"}],
            agent_responses=["We have Pizza for $10"],
        )
        metric = _make_metric(
            score=0.9, is_successful=True, reason="All claims verified"
        )

        with patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric):
            result = await evaluate_faithfulness(record)

        assert isinstance(result, EvaluatorResult)
        assert result.metric_name == "faithfulness"
        assert result.score == 0.9
        assert result.passed is True
        assert result.reason == "All claims verified"

    @pytest.mark.asyncio
    async def test_happy_path_uses_scenario_context_by_default(self) -> None:
        scenario = _make_scenario(context=["Scenario context item"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()

        with (
            patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric),
            patch(
                f"{ADAPTER_MODULE}.preprocess_context",
                return_value=["Scenario context item"],
            ) as mock_preprocess,
        ):
            await evaluate_faithfulness(record)

        mock_preprocess.assert_called_once_with(["Scenario context item"])

    @pytest.mark.asyncio
    async def test_context_override_replaces_scenario_context(self) -> None:
        scenario = _make_scenario(context=["Scenario context"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        override = ["Override context item"]
        metric = _make_metric()

        with (
            patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric),
            patch(
                f"{ADAPTER_MODULE}.preprocess_context", return_value=override
            ) as mock_preprocess,
        ):
            await evaluate_faithfulness(record, context_override=override)

        mock_preprocess.assert_called_once_with(override)

    @pytest.mark.asyncio
    async def test_context_override_none_falls_back_to_scenario_context(self) -> None:
        scenario = _make_scenario(context=["Fallback context"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()

        with (
            patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric),
            patch(
                f"{ADAPTER_MODULE}.preprocess_context",
                return_value=["Fallback context"],
            ) as mock_preprocess,
        ):
            await evaluate_faithfulness(record, context_override=None)

        mock_preprocess.assert_called_once_with(["Fallback context"])

    @pytest.mark.asyncio
    async def test_error_path_returns_failed_result(self) -> None:
        scenario = _make_scenario(context=["Some context"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.a_measure = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        with patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric):
            result = await evaluate_faithfulness(record)

        assert result.metric_name == "faithfulness"
        assert result.score == 0.0
        assert result.passed is False
        assert "ungrounded" in result.reason

    @pytest.mark.asyncio
    async def test_score_none_defaults_to_zero(self) -> None:
        scenario = _make_scenario(context=["ctx"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.score = None

        with patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric):
            result = await evaluate_faithfulness(record)

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reason_none_defaults_to_no_reason_provided(self) -> None:
        scenario = _make_scenario(context=["ctx"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.reason = None

        with patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric):
            result = await evaluate_faithfulness(record)

        assert result.reason == "No reason provided"

    @pytest.mark.asyncio
    async def test_agent_responses_joined_as_full_response(self) -> None:
        scenario = _make_scenario(context=["ctx"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["First response", "Second response"],
        )
        metric = _make_metric()

        with (
            patch(f"{ADAPTER_MODULE}.create_faithfulness_metric", return_value=metric),
            patch(f"{ADAPTER_MODULE}.preprocess_context", return_value=["ctx"]),
        ):
            await evaluate_faithfulness(record)

        call_args = metric.a_measure.call_args
        test_case = call_args[0][0]
        assert test_case.actual_output == "First response\nSecond response"


class TestEvaluateResponsive:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "What are your hours?", "assistant": "We are open 9am-5pm"}
            ],
            agent_responses=["We are open 9am-5pm"],
        )
        metric = _make_metric(
            score=0.85, is_successful=True, reason="Answered directly"
        )

        with patch(f"{ADAPTER_MODULE}.create_responsive_metric", return_value=metric):
            result = await evaluate_responsive(record)

        assert isinstance(result, EvaluatorResult)
        assert result.metric_name == "responsive"
        assert result.score == 0.85
        assert result.passed is True
        assert result.reason == "Answered directly"

    @pytest.mark.asyncio
    async def test_uses_last_turn_as_input_and_output(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi"},
                {"user": "What is your price?", "assistant": "Pizza is $10"},
            ],
            agent_responses=["Hi", "Pizza is $10"],
        )
        metric = _make_metric()

        with patch(f"{ADAPTER_MODULE}.create_responsive_metric", return_value=metric):
            await evaluate_responsive(record)

        call_args = metric.a_measure.call_args
        test_case = call_args[0][0]
        assert test_case.input == "What is your price?"
        assert test_case.actual_output == "Pizza is $10"

    @pytest.mark.asyncio
    async def test_error_path_returns_failed_result(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.a_measure = AsyncMock(side_effect=Exception("Metric error"))

        with patch(f"{ADAPTER_MODULE}.create_responsive_metric", return_value=metric):
            result = await evaluate_responsive(record)

        assert result.metric_name == "responsive"
        assert result.score == 0.0
        assert result.passed is False
        assert "Responsive metric failed" in result.reason

    @pytest.mark.asyncio
    async def test_score_none_defaults_to_zero(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.score = None

        with patch(f"{ADAPTER_MODULE}.create_responsive_metric", return_value=metric):
            result = await evaluate_responsive(record)

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reason_none_defaults_to_no_reason_provided(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.reason = None

        with patch(f"{ADAPTER_MODULE}.create_responsive_metric", return_value=metric):
            result = await evaluate_responsive(record)

        assert result.reason == "No reason provided"


class TestEvaluateVoiceAppropriate:
    @pytest.mark.asyncio
    async def test_happy_path_returns_result(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Tell me about pizza", "assistant": "We have great pizza"}],
            agent_responses=["We have great pizza"],
        )
        metric = _make_metric(
            score=0.75, is_successful=True, reason="Conversational tone"
        )

        with patch(
            f"{ADAPTER_MODULE}.create_voice_appropriate_metric", return_value=metric
        ):
            result = await evaluate_voice_appropriate(record)

        assert isinstance(result, EvaluatorResult)
        assert result.metric_name == "voice_appropriate"
        assert result.score == 0.75
        assert result.passed is True
        assert result.reason == "Conversational tone"

    @pytest.mark.asyncio
    async def test_uses_last_output_with_evaluation_input(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi there"},
                {
                    "user": "What is on the menu?",
                    "assistant": "We have pizza and pasta",
                },
            ],
            agent_responses=["Hi there", "We have pizza and pasta"],
        )
        metric = _make_metric()

        with patch(
            f"{ADAPTER_MODULE}.create_voice_appropriate_metric", return_value=metric
        ):
            await evaluate_voice_appropriate(record)

        call_args = metric.a_measure.call_args
        test_case = call_args[0][0]
        assert test_case.input == "(evaluation)"
        assert test_case.actual_output == "We have pizza and pasta"

    @pytest.mark.asyncio
    async def test_error_path_returns_failed_result(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.a_measure = AsyncMock(side_effect=ValueError("unexpected"))

        with patch(
            f"{ADAPTER_MODULE}.create_voice_appropriate_metric", return_value=metric
        ):
            result = await evaluate_voice_appropriate(record)

        assert result.metric_name == "voice_appropriate"
        assert result.score == 0.0
        assert result.passed is False
        assert "Voice appropriate metric failed" in result.reason

    @pytest.mark.asyncio
    async def test_score_none_defaults_to_zero(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.score = None

        with patch(
            f"{ADAPTER_MODULE}.create_voice_appropriate_metric", return_value=metric
        ):
            result = await evaluate_voice_appropriate(record)

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reason_none_defaults_to_no_reason_provided(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.reason = None

        with patch(
            f"{ADAPTER_MODULE}.create_voice_appropriate_metric", return_value=metric
        ):
            result = await evaluate_voice_appropriate(record)

        assert result.reason == "No reason provided"


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
        metric = _make_metric(
            score=0.95, is_successful=True, reason="Task completed successfully"
        )

        with patch(
            f"{ADAPTER_MODULE}.create_task_completion_metric", return_value=metric
        ):
            result = await evaluate_task_completion(record)

        assert isinstance(result, EvaluatorResult)
        assert result.metric_name == "task_completion"
        assert result.score == 0.95
        assert result.passed is True
        assert result.reason == "Task completed successfully"

    @pytest.mark.asyncio
    async def test_builds_conversational_test_case_with_turns(self) -> None:
        scenario = _make_scenario(user_turns=["Hi", "Bye"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Bye", "assistant": "Goodbye"},
            ],
            agent_responses=["Hello", "Goodbye"],
        )
        metric = _make_metric()

        with patch(
            f"{ADAPTER_MODULE}.create_task_completion_metric", return_value=metric
        ):
            await evaluate_task_completion(record)

        call_args = metric.a_measure.call_args
        test_case = call_args[0][0]
        # ConversationalTestCase has turns; 4 Turn objects expected (2 user + 2 assistant)
        assert len(test_case.turns) == 4

    @pytest.mark.asyncio
    async def test_error_path_returns_failed_result(self) -> None:
        scenario = _make_scenario(user_turns=["Hi", "Bye"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Bye", "assistant": "Goodbye"},
            ],
            agent_responses=["Hello", "Goodbye"],
        )
        metric = _make_metric()
        metric.a_measure = AsyncMock(side_effect=Exception("network error"))

        with patch(
            f"{ADAPTER_MODULE}.create_task_completion_metric", return_value=metric
        ):
            result = await evaluate_task_completion(record)

        assert result.metric_name == "task_completion"
        assert result.score == 0.0
        assert result.passed is False
        assert "Task completion metric failed" in result.reason

    @pytest.mark.asyncio
    async def test_score_none_defaults_to_zero(self) -> None:
        scenario = _make_scenario(user_turns=["Hi", "Bye"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.score = None

        with patch(
            f"{ADAPTER_MODULE}.create_task_completion_metric", return_value=metric
        ):
            result = await evaluate_task_completion(record)

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reason_none_defaults_to_no_reason_provided(self) -> None:
        scenario = _make_scenario(user_turns=["Hi", "Bye"])
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            agent_responses=["Hello"],
        )
        metric = _make_metric()
        metric.reason = None

        with patch(
            f"{ADAPTER_MODULE}.create_task_completion_metric", return_value=metric
        ):
            result = await evaluate_task_completion(record)

        assert result.reason == "No reason provided"


class TestFirstUserMessage:
    def test_returns_first_user_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "First message", "assistant": "Reply one"},
                {"user": "Second message", "assistant": "Reply two"},
            ],
        )
        assert _first_user_message(record) == "First message"

    def test_returns_empty_string_when_no_turns(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])
        assert _first_user_message(record) == ""

    def test_returns_empty_string_when_user_key_missing(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"assistant": "Hi there"}],
        )
        assert _first_user_message(record) == ""

    def test_single_turn_returns_that_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Only message", "assistant": "Only reply"}],
        )
        assert _first_user_message(record) == "Only message"


class TestLastTurn:
    def test_returns_last_user_and_assistant(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "First", "assistant": "Reply one"},
                {"user": "Second", "assistant": "Reply two"},
            ],
        )
        user_msg, assistant_msg = _last_turn(record)
        assert user_msg == "Second"
        assert assistant_msg == "Reply two"

    def test_returns_empty_strings_when_no_turns(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])
        user_msg, assistant_msg = _last_turn(record)
        assert user_msg == ""
        assert assistant_msg == ""

    def test_returns_empty_strings_when_keys_missing(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{}],
        )
        user_msg, assistant_msg = _last_turn(record)
        assert user_msg == ""
        assert assistant_msg == ""

    def test_single_turn_returns_that_turn(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Only user", "assistant": "Only assistant"}],
        )
        user_msg, assistant_msg = _last_turn(record)
        assert user_msg == "Only user"
        assert assistant_msg == "Only assistant"

    def test_partial_turn_missing_assistant(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hello"}],
        )
        user_msg, assistant_msg = _last_turn(record)
        assert user_msg == "Hello"
        assert assistant_msg == ""


class TestBuildTurns:
    def test_empty_turns_returns_empty_list(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])
        result = _build_turns(record)
        assert result == []

    def test_single_turn_creates_two_turn_objects(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hello", "assistant": "Hi there"}],
        )
        result = _build_turns(record)
        assert len(result) == 2
        assert result[0].role == "user"
        assert result[0].content == "Hello"
        assert result[1].role == "assistant"
        assert result[1].content == "Hi there"

    def test_multiple_turns_creates_interleaved_turn_objects(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hello", "assistant": "Hi"},
                {"user": "What is the price?", "assistant": "Pizza is $10"},
            ],
        )
        result = _build_turns(record)
        assert len(result) == 4
        assert result[0].role == "user"
        assert result[0].content == "Hello"
        assert result[1].role == "assistant"
        assert result[1].content == "Hi"
        assert result[2].role == "user"
        assert result[2].content == "What is the price?"
        assert result[3].role == "assistant"
        assert result[3].content == "Pizza is $10"

    def test_skips_empty_user_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "", "assistant": "Hi there"}],
        )
        result = _build_turns(record)
        # Empty user message is skipped; only assistant Turn is created
        assert len(result) == 1
        assert result[0].role == "assistant"
        assert result[0].content == "Hi there"

    def test_skips_empty_assistant_message(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hello", "assistant": ""}],
        )
        result = _build_turns(record)
        # Empty assistant message is skipped; only user Turn is created
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Hello"

    def test_skips_turn_with_missing_keys(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{}],
        )
        result = _build_turns(record)
        assert result == []

    def test_user_only_turn_creates_one_object(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Goodbye"}],
        )
        result = _build_turns(record)
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == "Goodbye"
