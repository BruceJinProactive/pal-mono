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

    def test_default_sender_identifier(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            result = create_driver(driver_mode="http", project_identifier="proj-123")

        assert result.sender_identifier == "eval-user@test.com"


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
