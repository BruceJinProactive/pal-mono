"""Tests for post-call analytics extraction helpers."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from db.tables.types import (
    CallEndedReason,
    CallLanguage,
    CallPurpose,
    CallQualityLabel,
    UserSatisfaction,
)
from services.analytics_service._utils import (
    _format_message_content,
    _normalize_call_quality_reason_codes,
    _normalize_transfer_agent_was_at_fault,
    _normalize_transfer_reason_category,
    extract_call_analytics,
)


class TestFormatMessageContent:
    def test_formats_livekit_content_shapes(self) -> None:
        assert _format_message_content(None) == ""
        assert _format_message_content("hello") == "hello"
        assert _format_message_content(["hello", {"text": "there"}]) == "hello there"
        assert _format_message_content({"text": {"body": "nested"}}) == "nested"
        assert _format_message_content({"body": ["one", "two"]}) == "one two"
        assert _format_message_content({"content": {"text": "fallback"}}) == "fallback"
        assert _format_message_content({"unexpected": "shape"}) == ""
        assert _format_message_content(123) == "123"


class TestTransferNormalization:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            ("", None),
            ("none", None),
            (" null ", None),
            ("not_applicable", None),
            ("tool_failure_order", "tool_failure_order"),
        ],
    )
    def test_normalizes_transfer_reason_category(
        self, value: object, expected: str | None
    ) -> None:
        assert _normalize_transfer_reason_category(value) == expected

    @pytest.mark.parametrize("value", [1, "not_a_category"])
    def test_rejects_invalid_transfer_reason_category(self, value: object) -> None:
        with pytest.raises(ValueError):
            _normalize_transfer_reason_category(value)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (True, True),
            (False, False),
            ("true", True),
            (" FALSE ", False),
            ("none", None),
            ("", None),
            ("not_applicable", None),
        ],
    )
    def test_normalizes_transfer_agent_was_at_fault(
        self, value: object, expected: bool | None
    ) -> None:
        assert _normalize_transfer_agent_was_at_fault(value) is expected

    @pytest.mark.parametrize("value", [1, "maybe"])
    def test_rejects_invalid_transfer_agent_was_at_fault(self, value: object) -> None:
        with pytest.raises(ValueError):
            _normalize_transfer_agent_was_at_fault(value)


class TestCallQualityNormalization:
    def test_normalizes_call_quality_reason_codes(self) -> None:
        assert _normalize_call_quality_reason_codes(
            [
                "restaurant_intent_present",
                " restaurant_intent_present ",
                "",
                "order_or_reservation_intent",
            ]
        ) == ["restaurant_intent_present", "order_or_reservation_intent"]

    @pytest.mark.parametrize("value", ["restaurant_intent_present", [1], ["made_up"]])
    def test_rejects_invalid_call_quality_reason_codes(self, value: object) -> None:
        with pytest.raises(ValueError):
            _normalize_call_quality_reason_codes(value)


@pytest.mark.asyncio
async def test_extract_call_analytics_parses_transfer_fields_and_prompt_context() -> (
    None
):
    response_payload = {
        "ended_reason": "assistant_forwarded",
        "call_purpose": ["ordering"],
        "user_satisfaction": "negative",
        "language": "english",
        "transfer_reason_category": "tool_failure_order",
        "transfer_agent_was_at_fault": "true",
        "call_quality_label": "legitimate_restaurant_call",
        "call_quality_reason_codes": [
            "restaurant_intent_present",
            "order_or_reservation_intent",
        ],
    }
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(response_payload))
            )
        ]
    )

    with patch("agent.model.call_llm_default", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = response

        analytics = await extract_call_analytics(
            [
                {"role": "assistant", "content": [{"text": "How can I help?"}]},
                {"role": "user", "content": {"text": {"body": "I need to order"}}},
            ],
            transfer_purpose="general",
            close_reason="assistant-forwarded-call",
            duration_seconds=64.25,
        )

    assert analytics["ended_reason"] is CallEndedReason.assistant_forwarded
    assert analytics["call_purpose"] == [CallPurpose.ordering]
    assert analytics["user_satisfaction"] is UserSatisfaction.negative
    assert analytics["language"] is CallLanguage.english
    assert analytics["transfer_reason_category"] == "tool_failure_order"
    assert analytics["transfer_agent_was_at_fault"] is True
    assert (
        analytics["call_quality_label"] is CallQualityLabel.legitimate_restaurant_call
    )
    assert analytics["call_quality_reason_codes"] == [
        "restaurant_intent_present",
        "order_or_reservation_intent",
    ]

    params = mock_llm.call_args.kwargs["params"]
    assert params["temperature"] == 0
    assert params["response_format"] == {"type": "json_object"}
    system_message = params["messages"][0]["content"]
    assert "prank_or_abusive" in system_message
    assert "   - silence_no_speech:" not in system_message
    assert "   - wrong_number_or_misdial:" not in system_message
    assert "use ended_reason (misdialed or silence_timeout)" in system_message
    user_message = params["messages"][1]["content"]
    assert (
        "Live call_transfer purpose captured during the call: general" in user_message
    )
    assert (
        "Live close_reason captured at call end: assistant-forwarded-call"
        in user_message
    )
    assert "Call duration seconds: 64.250" in user_message
    assert "ASSISTANT: How can I help?" in user_message
    assert "USER: I need to order" in user_message


@pytest.mark.asyncio
async def test_extract_call_analytics_requires_call_quality_reason_codes() -> None:
    response_payload = {
        "ended_reason": "customer_ended",
        "call_purpose": ["ordering"],
        "user_satisfaction": "neutral",
        "language": "english",
        "transfer_reason_category": None,
        "transfer_agent_was_at_fault": None,
        "call_quality_label": "legitimate_restaurant_call",
    }
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(response_payload))
            )
        ]
    )

    with patch("agent.model.call_llm_default", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = response

        with pytest.raises(KeyError, match="call_quality_reason_codes"):
            await extract_call_analytics(
                [{"role": "user", "content": "I need to order"}],
                transfer_purpose=None,
                close_reason="customer-ended",
                duration_seconds=10.0,
            )
