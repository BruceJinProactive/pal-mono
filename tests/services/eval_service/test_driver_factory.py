"""Tests for services/eval_service/_driver_factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

FACTORY_MODULE = "services.eval_service._driver_factory"


class TestCreateDriverHttp:
    def test_returns_http_driver_with_default_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EVAL_API_BASE_URL", raising=False)
        mock_driver = MagicMock()

        with (
            patch(
                f"{FACTORY_MODULE}.HTTPDriver", return_value=mock_driver
            ) as mock_http_driver_cls,
            patch(f"{FACTORY_MODULE}.logger"),
        ):
            from services.eval_service._driver_factory import create_driver

            result = create_driver(driver_mode="http", project_identifier="proj-123")

        mock_http_driver_cls.assert_called_once_with(
            base_url="http://localhost:8000",
            recipient_identifier="proj-123",
        )
        assert result is mock_driver

    def test_uses_eval_api_base_url_env_var(self) -> None:
        mock_driver = MagicMock()
        custom_url = "https://api.example.com"

        with (
            patch(f"{FACTORY_MODULE}.os.environ.get", return_value=custom_url),
            patch(
                f"{FACTORY_MODULE}.HTTPDriver", return_value=mock_driver
            ) as mock_http_driver_cls,
            patch(f"{FACTORY_MODULE}.logger"),
        ):
            from services.eval_service._driver_factory import create_driver

            result = create_driver(driver_mode="http", project_identifier="proj-456")

        mock_http_driver_cls.assert_called_once_with(
            base_url=custom_url,
            recipient_identifier="proj-456",
        )
        assert result is mock_driver

    def test_uses_eval_api_base_url_from_real_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom_url = "https://staging.example.com"
        monkeypatch.setenv("EVAL_API_BASE_URL", custom_url)
        mock_driver = MagicMock()

        with (
            patch(
                f"{FACTORY_MODULE}.HTTPDriver", return_value=mock_driver
            ) as mock_http_driver_cls,
            patch(f"{FACTORY_MODULE}.logger"),
        ):
            from services.eval_service._driver_factory import create_driver

            result = create_driver(driver_mode="http", project_identifier="proj-789")

        mock_http_driver_cls.assert_called_once_with(
            base_url=custom_url,
            recipient_identifier="proj-789",
        )
        assert result is mock_driver


class TestCreateDriverDirect:
    def test_raises_not_implemented_error(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            from services.eval_service._driver_factory import create_driver

            with pytest.raises(NotImplementedError):
                create_driver(driver_mode="direct", project_identifier="proj-123")

    def test_not_implemented_error_message_mentions_http(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            from services.eval_service._driver_factory import create_driver

            with pytest.raises(NotImplementedError, match="http"):
                create_driver(driver_mode="direct", project_identifier="proj-123")


class TestCreateDriverUnknownMode:
    def test_raises_value_error_for_unknown_mode(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            from services.eval_service._driver_factory import create_driver

            with pytest.raises(ValueError):
                create_driver(driver_mode="grpc", project_identifier="proj-123")

    def test_value_error_includes_unknown_mode_in_message(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            from services.eval_service._driver_factory import create_driver

            with pytest.raises(ValueError, match="grpc"):
                create_driver(driver_mode="grpc", project_identifier="proj-123")

    def test_raises_value_error_for_empty_string_mode(self) -> None:
        with patch(f"{FACTORY_MODULE}.logger"):
            from services.eval_service._driver_factory import create_driver

            with pytest.raises(ValueError):
                create_driver(driver_mode="", project_identifier="proj-123")
