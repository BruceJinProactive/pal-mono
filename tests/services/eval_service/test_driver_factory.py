"""Tests for services/eval_service/_driver_factory.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from services.eval_service._driver_factory import create_driver
from services.eval_service._http_voice_driver import HttpVoiceDriver
from services.eval_service._inprocess_driver import InProcessDriver

FACTORY_MODULE = "services.eval_service._driver_factory"


def _make_http(**kwargs: Any) -> InProcessDriver:
    """Helper: build an ``http`` driver and narrow the return type."""
    with patch(f"{FACTORY_MODULE}.logger"):
        result = create_driver(driver_mode="http", **kwargs)
    assert isinstance(result, InProcessDriver)
    return result


def _make_http_voice(**kwargs: Any) -> HttpVoiceDriver:
    """Helper: build an ``http_voice`` driver and narrow the return type."""
    with patch(f"{FACTORY_MODULE}.logger"):
        result = create_driver(driver_mode="http_voice", **kwargs)
    assert isinstance(result, HttpVoiceDriver)
    return result


class TestCreateDriverHttp:
    def test_returns_inprocess_driver(self) -> None:
        result = _make_http(project_identifier="proj-123")
        assert result.recipient_identifier == "proj-123"

    def test_sender_identifier_is_unique_per_call(self) -> None:
        a = _make_http(project_identifier="proj-123")
        b = _make_http(project_identifier="proj-123")

        assert a.sender_identifier != b.sender_identifier
        assert a.sender_identifier.endswith("@test.com")
        assert b.sender_identifier.endswith("@test.com")

    def test_sender_includes_scenario_id(self) -> None:
        result = _make_http(
            project_identifier="proj-123",
            scenario_id="order-simple-001",
        )
        assert "order-simple-001" in result.sender_identifier


class TestCreateDriverCustomerPhone:
    def test_passes_customer_phone_to_driver(self) -> None:
        result = _make_http(
            project_identifier="proj-123",
            customer_phone="5551234567",
        )
        assert result.customer_phone == "5551234567"

    def test_customer_phone_defaults_to_none(self) -> None:
        result = _make_http(project_identifier="proj-123")
        assert result.customer_phone is None


class TestCreateDriverSpecModifier:
    def test_default_is_eval_safety(self) -> None:
        from services.eval_service._safety import apply_eval_safety

        result = _make_http(project_identifier="proj-123")
        assert result.spec_modifier is apply_eval_safety

    def test_custom_spec_modifier_is_forwarded(self) -> None:
        def custom(spec: object) -> None:  # pragma: no cover - identity only
            pass

        result = _make_http(project_identifier="proj-123", spec_modifier=custom)
        assert result.spec_modifier is custom


class TestCreateDriverDirect:
    def test_raises_not_implemented_error(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            with pytest.raises(NotImplementedError):
                create_driver(driver_mode="direct", project_identifier="proj-123")

    def test_not_implemented_error_message_mentions_http(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            with pytest.raises(NotImplementedError, match="http"):
                create_driver(driver_mode="direct", project_identifier="proj-123")


class TestCreateDriverUnknownMode:
    def test_raises_value_error_for_unknown_mode(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            with pytest.raises(ValueError):
                create_driver(driver_mode="grpc", project_identifier="proj-123")

    def test_value_error_includes_unknown_mode_in_message(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            with pytest.raises(ValueError, match="grpc"):
                create_driver(driver_mode="grpc", project_identifier="proj-123")

    def test_raises_value_error_for_empty_string_mode(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            with pytest.raises(ValueError):
                create_driver(driver_mode="", project_identifier="proj-123")


class TestCreateDriverHttpVoice:
    def test_returns_http_voice_driver(self) -> None:
        result = _make_http_voice(project_identifier="+14155551212")

        # Attributes exposed on the public surface.
        assert result.last_conversation_id is None
        assert result.call_id.startswith("eval-")

    def test_customer_phone_becomes_caller_number(self) -> None:
        result = _make_http_voice(
            project_identifier="+14155551212",
            customer_phone="+15551234567",
        )
        # _caller_number is the private attribute used on /internal/voice/init.
        assert result._caller_number == "+15551234567"

    def test_scenario_id_is_embedded_in_call_id(self) -> None:
        result = _make_http_voice(
            project_identifier="+14155551212",
            scenario_id="pick-4-combo-001",
        )
        assert "pick-4-combo-001"[:16] in result.call_id

    def test_each_call_generates_unique_call_id(self) -> None:
        a = _make_http_voice(
            project_identifier="+14155551212",
            scenario_id="s1",
        )
        b = _make_http_voice(
            project_identifier="+14155551212",
            scenario_id="s1",
        )

        assert a.call_id != b.call_id
