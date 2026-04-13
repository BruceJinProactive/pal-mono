"""Tests for E18: Speech fidelity LALM-as-Judge evaluator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._evaluators import ConversationRecord
from services.eval_service.evaluators.speech_fidelity import (
    _format_conversation,
    evaluate_speech_fidelity,
)
from services.eval_service.schema import EvalScenario

MODULE = "services.eval_service.evaluators.speech_fidelity"


def _make_scenario(**overrides: Any) -> EvalScenario:
    defaults: dict[str, Any] = {
        "scenario_id": "fidelity-test",
        "scenario": "Test speech fidelity",
        "test_category": "voice",
        "user_turns": ["Hello", "What are your hours?"],
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


def _make_record(
    agent_responses: list[str] | None = None,
    turns: list[dict[str, str]] | None = None,
) -> ConversationRecord:
    return ConversationRecord(
        scenario=_make_scenario(),
        turns=turns or [],
        agent_responses=agent_responses or [],
    )


# ---------------------------------------------------------------------------
# _format_conversation
# ---------------------------------------------------------------------------


class TestFormatConversation:
    def test_extracts_from_turns(self) -> None:
        record = _make_record(
            turns=[
                {"user": "Hi", "assistant": "Hello!"},
                {"user": "Hours?", "assistant": "We're open 9-5."},
            ],
        )
        user_input, agent_output = _format_conversation(record)
        assert "Hi" in user_input
        assert "Hours?" in user_input
        assert "Hello!" in agent_output
        assert "We're open 9-5." in agent_output

    def test_falls_back_to_agent_responses(self) -> None:
        record = _make_record(
            turns=[{"user": "Hi"}],  # no assistant keys
            agent_responses=["Hello!", "How can I help?"],
        )
        _, agent_output = _format_conversation(record)
        assert "Hello!" in agent_output
        assert "How can I help?" in agent_output

    def test_empty_record(self) -> None:
        record = _make_record()
        user_input, agent_output = _format_conversation(record)
        assert user_input == ""
        assert agent_output == ""


# ---------------------------------------------------------------------------
# evaluate_speech_fidelity
# ---------------------------------------------------------------------------


class TestEvaluateSpeechFidelity:
    @pytest.mark.asyncio
    async def test_no_agent_output(self) -> None:
        record = _make_record()
        result = await evaluate_speech_fidelity(record)
        assert result.metric_name == "speech_fidelity"
        assert result.score == 1.0
        assert result.passed is True
        assert "No agent output" in result.reason

    @pytest.mark.asyncio
    async def test_whitespace_only_output(self) -> None:
        record = _make_record(
            turns=[{"user": "Hi", "assistant": "   "}],
        )
        result = await evaluate_speech_fidelity(record)
        assert result.score == 1.0
        assert "No agent output" in result.reason

    @pytest.mark.asyncio
    async def test_successful_evaluation(self) -> None:
        record = _make_record(
            turns=[
                {"user": "What are your hours?", "assistant": "We're open 9 to 5."},
            ],
        )

        mock_metric = MagicMock()
        mock_metric.a_measure = AsyncMock()
        mock_metric.score = 0.85
        mock_metric.is_successful.return_value = True
        mock_metric.reason = "Natural and concise"

        with patch(
            f"{MODULE}._create_speech_fidelity_metric", return_value=mock_metric
        ):
            result = await evaluate_speech_fidelity(record)

        assert result.metric_name == "speech_fidelity"
        assert result.score == 0.85
        assert result.passed is True
        assert result.reason == "Natural and concise"
        mock_metric.a_measure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_low_score_fails(self) -> None:
        record = _make_record(
            turns=[
                {
                    "user": "Menu?",
                    "assistant": (
                        "**Our Menu:** \n- Pizza: $10 (SKU-29481)\n"
                        "- Pasta: $12 (SKU-29482)\n"
                        "Visit https://example.com/menu for more info!"
                    ),
                },
            ],
        )

        mock_metric = MagicMock()
        mock_metric.a_measure = AsyncMock()
        mock_metric.score = 0.3
        mock_metric.is_successful.return_value = False
        mock_metric.reason = "Contains markdown, URLs, and SKU codes"

        with patch(
            f"{MODULE}._create_speech_fidelity_metric", return_value=mock_metric
        ):
            result = await evaluate_speech_fidelity(record)

        assert result.score == 0.3
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_metric_exception_returns_failure(self) -> None:
        record = _make_record(
            turns=[{"user": "Hi", "assistant": "Hello!"}],
        )

        mock_metric = MagicMock()
        mock_metric.a_measure = AsyncMock(side_effect=RuntimeError("LLM API error"))

        with patch(
            f"{MODULE}._create_speech_fidelity_metric", return_value=mock_metric
        ):
            result = await evaluate_speech_fidelity(record)

        assert result.score == 0.0
        assert result.passed is False
        assert "failed" in result.reason

    @pytest.mark.asyncio
    async def test_none_score_defaults_to_zero(self) -> None:
        record = _make_record(
            turns=[{"user": "Hi", "assistant": "Hello!"}],
        )

        mock_metric = MagicMock()
        mock_metric.a_measure = AsyncMock()
        mock_metric.score = None
        mock_metric.is_successful.return_value = False
        mock_metric.reason = None

        with patch(
            f"{MODULE}._create_speech_fidelity_metric", return_value=mock_metric
        ):
            result = await evaluate_speech_fidelity(record)

        assert result.score == 0.0
        assert result.reason == "No reason provided"

    @pytest.mark.asyncio
    async def test_uses_voice_call_placeholder_when_no_user_input(self) -> None:
        record = _make_record(
            agent_responses=["Welcome to our restaurant!"],
        )

        mock_metric = MagicMock()
        mock_metric.a_measure = AsyncMock()
        mock_metric.score = 0.9
        mock_metric.is_successful.return_value = True
        mock_metric.reason = "Good"

        with patch(
            f"{MODULE}._create_speech_fidelity_metric", return_value=mock_metric
        ):
            result = await evaluate_speech_fidelity(record)

        # Verify the test case was constructed with placeholder input
        call_args = mock_metric.a_measure.call_args[0][0]
        assert call_args.input == "(voice call)"
        assert result.score == 0.9
