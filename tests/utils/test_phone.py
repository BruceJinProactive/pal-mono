"""Tests for utils.phone module."""

from unittest.mock import patch

from utils.phone import get_test_phone_numbers, is_test_phone_number

MODULE = "utils.phone"


class TestGetTestPhoneNumbers:
    """Tests for get_test_phone_numbers."""

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_parsed_numbers(self, mock_secret: object) -> None:
        """Should parse comma-separated phone numbers from secret."""
        mock_secret.return_value = "+18889738742,+15551234567"  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == {"+18889738742", "+15551234567"}

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_strips_whitespace(self, mock_secret: object) -> None:
        """Should strip whitespace from phone numbers."""
        mock_secret.return_value = " +18889738742 , +15551234567 "  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == {"+18889738742", "+15551234567"}

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_empty_set_when_secret_missing(self, mock_secret: object) -> None:
        """Should return empty set when secret is not configured."""
        mock_secret.side_effect = ValueError("Secret not found")  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == set()

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_empty_set_when_key_error(self, mock_secret: object) -> None:
        """Should return empty set on KeyError."""
        mock_secret.side_effect = KeyError("TEST_PHONE_NUMBERS")  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == set()

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_empty_set_when_empty_string(self, mock_secret: object) -> None:
        """Should return empty set when secret is empty string."""
        mock_secret.return_value = ""  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == set()

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_ignores_empty_entries(self, mock_secret: object) -> None:
        """Should ignore empty entries from trailing commas."""
        mock_secret.return_value = "+18889738742,,,"  # type: ignore[attr-defined]
        result = get_test_phone_numbers()
        assert result == {"+18889738742"}


class TestIsTestPhoneNumber:
    """Tests for is_test_phone_number."""

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_true_for_test_number(self, mock_secret: object) -> None:
        """Should return True for configured test numbers."""
        mock_secret.return_value = "+18889738742,+15551234567"  # type: ignore[attr-defined]
        assert is_test_phone_number("+18889738742") is True

    @patch(f"{MODULE}.get_server_secret_with_fallback")
    def test_returns_false_for_non_test_number(self, mock_secret: object) -> None:
        """Should return False for numbers not in the test list."""
        mock_secret.return_value = "+18889738742"  # type: ignore[attr-defined]
        assert is_test_phone_number("+19995550000") is False
