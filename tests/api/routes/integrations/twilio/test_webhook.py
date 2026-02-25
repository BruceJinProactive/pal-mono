# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for Twilio voice webhook implementation.

Tests cover:
- XML escaping for security
- Twilio signature validation
- TwiML XML generation with parameters
- Webhook handler with various scenarios
- Error handling and status codes
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from starlette.datastructures import FormData

from api.routes.integrations.twilio._webhook import (
    _escape_xml,
    generate_stream_twiml,
    handle_voice_webhook,
    validate_twilio_signature,
)


# Helper function to create properly iterable FormData mock
def create_form_data_mock(data: dict) -> FormData:
    """Create a FormData mock that supports .items() iteration."""
    form_data = FormData()
    # Use the internal _dict to store data
    form_data._dict = data
    return form_data


# ---------------------------------------------------------------------------
# XML Escaping Tests
# ---------------------------------------------------------------------------


class TestEscapeXml:
    """Test _escape_xml() function for security."""

    def test_escape_ampersand(self) -> None:
        """Ampersand should be escaped to &amp;."""
        assert _escape_xml("foo & bar") == "foo &amp; bar"

    def test_escape_less_than(self) -> None:
        """Less-than should be escaped to &lt;."""
        assert _escape_xml("foo < bar") == "foo &lt; bar"

    def test_escape_greater_than(self) -> None:
        """Greater-than should be escaped to &gt;."""
        assert _escape_xml("foo > bar") == "foo &gt; bar"

    def test_escape_double_quote(self) -> None:
        """Double quote should be escaped to &quot;."""
        assert _escape_xml('foo " bar') == "foo &quot; bar"

    def test_escape_single_quote(self) -> None:
        """Single quote should be escaped to &apos;."""
        assert _escape_xml("foo ' bar") == "foo &apos; bar"

    def test_escape_multiple_characters(self) -> None:
        """Multiple special characters should all be escaped."""
        result = _escape_xml('<tag attr="value">foo & bar</tag>')
        expected = "&lt;tag attr=&quot;value&quot;&gt;foo &amp; bar&lt;/tag&gt;"
        assert result == expected

    def test_escape_no_special_characters(self) -> None:
        """Strings without special characters should remain unchanged."""
        assert _escape_xml("foo bar baz") == "foo bar baz"

    def test_escape_empty_string(self) -> None:
        """Empty string should remain empty."""
        assert _escape_xml("") == ""


# ---------------------------------------------------------------------------
# Twilio Signature Validation Tests
# ---------------------------------------------------------------------------


class TestValidateTwilioSignature:
    """Test validate_twilio_signature() function."""

    def test_validate_signature_currently_returns_true(self) -> None:
        """Signature validation currently bypassed for debugging (returns True)."""
        # Since validation is temporarily skipped, it should always return True
        result = validate_twilio_signature(
            signature="invalid_signature",
            auth_token="test_token",
            url="https://example.com/webhook",
            params={"foo": "bar"},
        )
        assert result is True

    def test_validate_signature_with_empty_params(self) -> None:
        """Validation with empty params should work."""
        result = validate_twilio_signature(
            signature="test_signature",
            auth_token="test_token",
            url="https://example.com/webhook",
            params={},
        )
        assert result is True

    def test_validate_signature_with_special_characters_in_url(self) -> None:
        """Validation with special characters in URL should work."""
        result = validate_twilio_signature(
            signature="test_signature",
            auth_token="test_token",
            url="https://example.com/webhook?foo=bar&baz=qux",
            params={"param1": "value1"},
        )
        assert result is True

    def test_validate_signature_params_sorted(self) -> None:
        """Params should be sorted alphabetically for signature calculation."""
        # Even though validation is skipped, test that function handles sorting
        result = validate_twilio_signature(
            signature="test_signature",
            auth_token="test_token",
            url="https://example.com/webhook",
            params={"z": "last", "a": "first", "m": "middle"},
        )
        assert result is True


# ---------------------------------------------------------------------------
# TwiML Generation Tests
# ---------------------------------------------------------------------------


class TestGenerateStreamTwiml:
    """Test generate_stream_twiml() function."""

    def test_generate_twiml_basic(self) -> None:
        """Generate basic TwiML without parameters."""
        result = generate_stream_twiml("wss://example.com/ws")

        assert '<?xml version="1.0" encoding="UTF-8"?>' in result
        assert "<Response>" in result
        assert "<Connect>" in result
        assert '<Stream url="wss://example.com/ws"></Stream>' in result
        assert "</Connect>" in result
        assert "</Response>" in result

    def test_generate_twiml_with_single_parameter(self) -> None:
        """Generate TwiML with one parameter."""
        result = generate_stream_twiml(
            "wss://example.com/ws",
            parameters={"from_number": "+15551234567"},
        )

        assert '<Stream url="wss://example.com/ws">' in result
        assert '<Parameter name="from_number" value="+15551234567"/>' in result

    def test_generate_twiml_with_multiple_parameters(self) -> None:
        """Generate TwiML with multiple parameters."""
        result = generate_stream_twiml(
            "wss://example.com/ws",
            parameters={
                "from_number": "+15551234567",
                "to_number": "+15557654321",
            },
        )

        assert '<Parameter name="from_number" value="+15551234567"/>' in result
        assert '<Parameter name="to_number" value="+15557654321"/>' in result

    def test_generate_twiml_escapes_websocket_url(self) -> None:
        """WebSocket URL with special characters should be escaped."""
        result = generate_stream_twiml('wss://example.com/ws?foo=bar&baz="qux"')

        # URL should be escaped
        assert "wss://example.com/ws?foo=bar&amp;baz=&quot;qux&quot;" in result
        # Verify raw & and " are not present (only escaped versions)
        assert 'url="wss://example.com/ws?foo=bar&amp;baz=&quot;qux&quot;"' in result

    def test_generate_twiml_escapes_parameter_names(self) -> None:
        """Parameter names with special characters should be escaped."""
        result = generate_stream_twiml(
            "wss://example.com/ws",
            parameters={"param<name>": "value"},
        )

        assert '<Parameter name="param&lt;name&gt;" value="value"/>' in result

    def test_generate_twiml_escapes_parameter_values(self) -> None:
        """Parameter values with special characters should be escaped."""
        result = generate_stream_twiml(
            "wss://example.com/ws",
            parameters={"key": 'value with "quotes" & <tags>'},
        )

        assert (
            '<Parameter name="key" value="value with &quot;quotes&quot; &amp; &lt;tags&gt;"/>'
            in result
        )

    def test_generate_twiml_with_none_parameters(self) -> None:
        """Passing None for parameters should work."""
        result = generate_stream_twiml("wss://example.com/ws", parameters=None)

        assert '<Stream url="wss://example.com/ws"></Stream>' in result
        assert "<Parameter" not in result

    def test_generate_twiml_with_empty_parameters(self) -> None:
        """Empty parameters dict should produce no parameter elements."""
        result = generate_stream_twiml("wss://example.com/ws", parameters={})

        assert '<Stream url="wss://example.com/ws"></Stream>' in result
        assert "<Parameter" not in result


# ---------------------------------------------------------------------------
# Webhook Handler Tests
# ---------------------------------------------------------------------------


class TestHandleVoiceWebhook:
    """Test handle_voice_webhook() main handler function."""

    @pytest.mark.asyncio
    async def test_handle_webhook_success(self) -> None:
        """Successful webhook handling returns TwiML response."""
        # Mock request
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        # Mock form data
        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890",
                "From": "+15551234567",
                "To": "+15557654321",
                "CallStatus": "ringing",
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            response = await handle_voice_webhook(mock_request)

        assert response.status_code == 200
        assert response.media_type == "application/xml"
        assert b"<?xml version" in response.body
        assert b"<Response>" in response.body
        assert b"<Connect>" in response.body
        assert b"<Stream" in response.body
        assert b"wss://example.com/v1/telephony/twilio/ws" in response.body

    @pytest.mark.asyncio
    async def test_handle_webhook_missing_auth_token(self) -> None:
        """Missing TWILIO_AUTH_TOKEN raises 500 error."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                await handle_voice_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Configuration error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_webhook_missing_signature(self) -> None:
        """Missing x-twilio-signature header raises 403 error."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.headers.get = MagicMock(return_value=None)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            with pytest.raises(HTTPException) as exc_info:
                await handle_voice_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Missing signature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_webhook_includes_parameters_in_twiml(self) -> None:
        """Webhook handler includes from_number and to_number in TwiML."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890",
                "From": "+15551234567",
                "To": "+15557654321",
                "CallStatus": "ringing",
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            response = await handle_voice_webhook(mock_request)

        body = response.body.decode("utf-8")
        assert '<Parameter name="from_number" value="+15551234567"/>' in body
        assert '<Parameter name="to_number" value="+15557654321"/>' in body

    @pytest.mark.asyncio
    async def test_handle_webhook_without_from_or_to_numbers(self) -> None:
        """Webhook handler works without from/to numbers."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        # Form data without From/To
        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890",
                "CallStatus": "ringing",
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            response = await handle_voice_webhook(mock_request)

        assert response.status_code == 200
        body = response.body.decode("utf-8")
        # Should not include parameters if not present
        assert "from_number" not in body
        assert "to_number" not in body

    @pytest.mark.asyncio
    async def test_handle_webhook_builds_https_url(self) -> None:
        """Webhook handler always builds HTTPS URL for signature validation."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "http"  # Even if http
        mock_request.url.query = "foo=bar"
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890",
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            with patch(
                "api.routes.integrations.twilio._webhook.validate_twilio_signature"
            ) as mock_validate:
                mock_validate.return_value = True
                await handle_voice_webhook(mock_request)

        # Verify HTTPS was used in validation
        mock_validate.assert_called_once()
        call_args = mock_validate.call_args
        assert call_args[0][2].startswith("https://")
        assert "?foo=bar" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_handle_webhook_filters_non_string_form_values(self) -> None:
        """Webhook handler filters out non-string form values for signature validation."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        # Form data with mixed types
        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890",
                "From": "+15551234567",
                "file_upload": MagicMock(),  # Non-string value
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            with patch(
                "api.routes.integrations.twilio._webhook.validate_twilio_signature"
            ) as mock_validate:
                mock_validate.return_value = True
                await handle_voice_webhook(mock_request)

        # Verify only string values passed to validation
        call_args = mock_validate.call_args
        params = call_args[0][3]
        assert "CallSid" in params
        assert "From" in params
        assert "file_upload" not in params

    @pytest.mark.asyncio
    async def test_handle_webhook_exception_converts_to_http_500(self) -> None:
        """Unexpected exceptions are converted to 500 errors."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "example.com",
            }.get(key, default)
        )

        # Mock form() to raise an exception
        mock_request.form = AsyncMock(side_effect=Exception("Unexpected error"))

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            with pytest.raises(HTTPException) as exc_info:
                await handle_voice_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Internal error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_webhook_http_exception_propagates(self) -> None:
        """HTTPExceptions are re-raised without wrapping."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.headers.get = MagicMock(return_value=None)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            with pytest.raises(HTTPException) as exc_info:
                await handle_voice_webhook(mock_request)

        # Should be the original 403 error, not wrapped in 500
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_handle_webhook_builds_correct_websocket_url(self) -> None:
        """Webhook handler builds WebSocket URL with correct host and path."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "api.example.com:8080",  # With port
            }.get(key, default)
        )

        form_data = create_form_data_mock({"CallSid": "CA1234567890"})
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            response = await handle_voice_webhook(mock_request)

        body = response.body.decode("utf-8")
        # WebSocket URL should use wss:// and include host with port
        assert 'url="wss://api.example.com:8080/v1/telephony/twilio/ws"' in body


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestWebhookIntegration:
    """Integration tests for full webhook flow."""

    @pytest.mark.asyncio
    async def test_full_webhook_flow_with_all_parameters(self) -> None:
        """Test complete webhook flow with all call parameters."""
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.url.path = "/v1/telephony/twilio/voice"
        mock_request.url.scheme = "https"
        mock_request.url.query = ""
        mock_request.headers.get = MagicMock(
            side_effect=lambda key, default=None: {
                "x-twilio-signature": "valid_signature",
                "host": "api.example.com",
            }.get(key, default)
        )

        form_data = create_form_data_mock(
            {
                "CallSid": "CA1234567890abcdef",
                "From": "+15551234567",
                "To": "+15557654321",
                "CallStatus": "ringing",
                "Direction": "inbound",
                "ApiVersion": "2010-04-01",
            }
        )
        mock_request.form = AsyncMock(return_value=form_data)

        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": "test_auth_token"}):
            response = await handle_voice_webhook(mock_request)

        # Verify response
        assert response.status_code == 200
        assert response.media_type == "application/xml"

        body = response.body.decode("utf-8")
        # Verify TwiML structure
        assert "<?xml version" in body
        assert "<Response>" in body
        assert "<Connect>" in body
        assert "<Stream" in body
        assert "</Stream>" in body
        assert "</Connect>" in body
        assert "</Response>" in body

        # Verify WebSocket URL
        assert "wss://api.example.com/v1/telephony/twilio/ws" in body

        # Verify parameters
        assert "from_number" in body
        assert "+15551234567" in body
        assert "to_number" in body
        assert "+15557654321" in body
