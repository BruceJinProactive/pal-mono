"""Tests for services/eval_service/_driver_factory.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.eval_service._driver_factory import create_driver
from services.eval_service._inprocess_driver import InProcessDriver

FACTORY_MODULE = "services.eval_service._driver_factory"


class TestCreateDriverHttp:
    def test_returns_inprocess_driver(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(driver_mode="http", project_identifier="proj-123")

        assert isinstance(result, InProcessDriver)
        assert result.recipient_identifier == "proj-123"

    def test_sender_identifier_is_unique_per_call(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            a = create_driver(driver_mode="http", project_identifier="proj-123")
            b = create_driver(driver_mode="http", project_identifier="proj-123")

        assert a.sender_identifier != b.sender_identifier
        assert a.sender_identifier.endswith("@test.com")
        assert b.sender_identifier.endswith("@test.com")

    def test_sender_includes_scenario_id(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(
                driver_mode="http",
                project_identifier="proj-123",
                scenario_id="order-simple-001",
            )

        assert "order-simple-001" in result.sender_identifier


class TestCreateDriverCustomerPhone:
    def test_passes_customer_phone_to_driver(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(
                driver_mode="http",
                project_identifier="proj-123",
                customer_phone="5551234567",
            )

        assert result.customer_phone == "5551234567"

    def test_customer_phone_defaults_to_none(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(
                driver_mode="http",
                project_identifier="proj-123",
            )

        assert result.customer_phone is None


class TestCreateDriverSpecModifier:
    def test_default_is_eval_safety(self) -> None:
        from services.eval_service._safety import apply_eval_safety

        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(driver_mode="http", project_identifier="proj-123")

        assert result.spec_modifier is apply_eval_safety

    def test_custom_spec_modifier_is_forwarded(self) -> None:
        def custom(spec: object) -> None:  # pragma: no cover - identity only
            pass

        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(
                driver_mode="http",
                project_identifier="proj-123",
                spec_modifier=custom,
            )

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
