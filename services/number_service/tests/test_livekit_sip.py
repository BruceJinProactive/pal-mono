"""Tests for LiveKit SIP client — dispatch rule management."""

from unittest.mock import MagicMock, patch

import pytest

from services.number_service._livekit_sip import (
    LiveKitProvisionResult,
    LiveKitSIPClient,
)


class TestLiveKitSIPClientConfiguration:
    """Tests for LiveKit client configuration detection."""

    def test_is_configured_returns_true_when_all_vars_set(self):
        """All four env vars present → client is configured."""
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "https://lk.example.com",
                "LIVEKIT_API_KEY": "APIkey123",
                "LIVEKIT_API_SECRET": "secret456",
                "LIVEKIT_INBOUND_TRUNK_ID": "trunk-abc",
            },
        ):
            client = LiveKitSIPClient()
            assert client.is_configured() is True

    def test_is_configured_returns_false_when_url_missing(self):
        """Missing LIVEKIT_URL → client is not configured."""
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "",
                "LIVEKIT_API_KEY": "APIkey123",
                "LIVEKIT_API_SECRET": "secret456",
                "LIVEKIT_INBOUND_TRUNK_ID": "trunk-abc",
            },
        ):
            client = LiveKitSIPClient()
            assert client.is_configured() is False

    def test_is_configured_returns_false_when_trunk_id_missing(self):
        """Missing LIVEKIT_INBOUND_TRUNK_ID → client is not configured."""
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "https://lk.example.com",
                "LIVEKIT_API_KEY": "APIkey123",
                "LIVEKIT_API_SECRET": "secret456",
                "LIVEKIT_INBOUND_TRUNK_ID": "",
            },
        ):
            client = LiveKitSIPClient()
            assert client.is_configured() is False

    def test_is_configured_returns_false_with_no_env_vars(self):
        """No LiveKit env vars set → not configured."""
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "",
                "LIVEKIT_API_KEY": "",
                "LIVEKIT_API_SECRET": "",
                "LIVEKIT_INBOUND_TRUNK_ID": "",
            },
        ):
            client = LiveKitSIPClient()
            assert client.is_configured() is False


class TestLiveKitSIPClientCreateDispatchRule:
    """Tests for creating SIP dispatch rules."""

    def _make_client(self):
        """Create a configured LiveKit client."""
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "https://lk.example.com",
                "LIVEKIT_API_KEY": "APIkey123",
                "LIVEKIT_API_SECRET": "secret456",
                "LIVEKIT_INBOUND_TRUNK_ID": "trunk-abc",
            },
        ):
            return LiveKitSIPClient()

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_create_dispatch_rule_success(self, mock_token_cls, mock_post):
        """Successful dispatch rule creation returns trunk_id and dispatch_rule_id."""
        client = self._make_client()

        # Mock JWT generation
        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sipDispatchRuleId": "dispatch-rule-123"}
        mock_post.return_value = mock_response

        result = client.create_dispatch_rule("+15551234567")

        assert isinstance(result, LiveKitProvisionResult)
        assert result.dispatch_rule_id == "dispatch-rule-123"
        assert result.trunk_id == "trunk-abc"

        # Verify the API was called with correct URL
        call_args = mock_post.call_args
        assert "/twirp/livekit.SIP/CreateSIPDispatchRule" in call_args[0][0]

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_create_dispatch_rule_strips_plus_from_number(
        self, mock_token_cls, mock_post
    ):
        """Phone number should have + prefix stripped for LiveKit room naming."""
        client = self._make_client()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sipDispatchRuleId": "dispatch-rule-456"}
        mock_post.return_value = mock_response

        client.create_dispatch_rule("+15551234567")

        # Verify the payload uses clean number (no +)
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["name"] == "inbound-15551234567"

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_create_dispatch_rule_api_failure_raises(self, mock_token_cls, mock_post):
        """HTTP error from LiveKit API → ValueError raised."""
        client = self._make_client()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="LiveKit CreateSIPDispatchRule failed"):
            client.create_dispatch_rule("+15551234567")

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_create_dispatch_rule_empty_id_raises(self, mock_token_cls, mock_post):
        """API returns empty dispatch rule ID → ValueError raised."""
        client = self._make_client()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sipDispatchRuleId": ""}
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="empty dispatch rule ID"):
            client.create_dispatch_rule("+15551234567")


class TestLiveKitSIPClientDeleteDispatchRule:
    """Tests for deleting SIP dispatch rules."""

    def _make_client(self):
        with patch.dict(
            "os.environ",
            {
                "LIVEKIT_URL": "https://lk.example.com",
                "LIVEKIT_API_KEY": "APIkey123",
                "LIVEKIT_API_SECRET": "secret456",
                "LIVEKIT_INBOUND_TRUNK_ID": "trunk-abc",
            },
        ):
            return LiveKitSIPClient()

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_delete_dispatch_rule_success(self, mock_token_cls, mock_post):
        """Successful deletion completes without error."""
        client = self._make_client()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Should not raise
        client.delete_dispatch_rule("dispatch-rule-123")

        call_args = mock_post.call_args
        assert "/twirp/livekit.SIP/DeleteSIPDispatchRule" in call_args[0][0]
        assert call_args[1]["json"]["sipDispatchRuleId"] == "dispatch-rule-123"

    @patch("services.number_service._livekit_sip.requests.post")
    @patch("services.number_service._livekit_sip.AccessToken")
    def test_delete_dispatch_rule_api_failure_raises(self, mock_token_cls, mock_post):
        """HTTP error during deletion → ValueError raised."""
        client = self._make_client()

        mock_token = MagicMock()
        mock_token.to_jwt.return_value = "fake.jwt.token"
        mock_token_cls.return_value = mock_token

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="LiveKit DeleteSIPDispatchRule failed"):
            client.delete_dispatch_rule("dispatch-rule-999")
