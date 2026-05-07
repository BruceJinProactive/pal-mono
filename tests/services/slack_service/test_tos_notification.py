"""Tests for TOS accepted Slack notification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.slack_service._feedback import send_tos_accepted_notification


class TestSendTosAcceptedNotification:
    """Tests for send_tos_accepted_notification function."""

    @pytest.mark.asyncio
    async def test_sends_notification_to_client_updates_in_prd(self):
        """Should send to #client-updates in production."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = MagicMock(
            data={"ok": True, "ts": "123.456"}
        )

        with patch.dict("os.environ", {"RUNTIME_ENV": "prd"}):
            result = await send_tos_accepted_notification(
                account_name="test-account",
                account_display_name="Test Account",
                user_email="user@example.com",
                tos_version="v1.0",
                client=mock_client,
            )

        assert result is not None
        assert result["ok"] is True
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#client-updates"
        assert "T&C accepted" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_sends_notification_to_test_channel_in_non_prd(self):
        """Should send to #test-channel in non-production environments."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = MagicMock(
            data={"ok": True, "ts": "123.456"}
        )

        with patch.dict("os.environ", {"RUNTIME_ENV": "lat"}):
            result = await send_tos_accepted_notification(
                account_name="test-account",
                account_display_name="Test Account",
                user_email="user@example.com",
                tos_version="v1.0",
                client=mock_client,
            )

        assert result is not None
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#test-channel"

    @pytest.mark.asyncio
    async def test_includes_user_name_when_provided(self):
        """Should include user name in fields when provided."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = MagicMock(
            data={"ok": True, "ts": "123.456"}
        )

        with patch.dict("os.environ", {"RUNTIME_ENV": "prd"}):
            result = await send_tos_accepted_notification(
                account_name="test-account",
                account_display_name="Test Account",
                user_email="user@example.com",
                tos_version="v1.0",
                user_name="John Doe",
                client=mock_client,
            )

        assert result is not None
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        blocks = call_kwargs["blocks"]
        # Find fields section and check user name is present
        fields_block = next(
            b for b in blocks if b.get("type") == "section" and "fields" in b
        )
        fields_text = str(fields_block["fields"])
        assert "John Doe" in fields_text

    @pytest.mark.asyncio
    async def test_uses_channel_override(self):
        """Should use provided channel override."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.return_value = MagicMock(
            data={"ok": True, "ts": "123.456"}
        )

        result = await send_tos_accepted_notification(
            account_name="test-account",
            account_display_name="Test Account",
            user_email="user@example.com",
            tos_version="v1.0",
            channel="#custom-channel",
            client=mock_client,
        )

        assert result is not None
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "#custom-channel"

    @pytest.mark.asyncio
    async def test_returns_none_on_slack_api_error(self):
        """Should return None when Slack API raises an error."""
        from slack_sdk.errors import SlackApiError

        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="channel_not_found",
            response=MagicMock(data={"ok": False, "error": "channel_not_found"}),
        )

        with patch.dict("os.environ", {"RUNTIME_ENV": "prd"}):
            result = await send_tos_accepted_notification(
                account_name="test-account",
                account_display_name="Test Account",
                user_email="user@example.com",
                tos_version="v1.0",
                client=mock_client,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_client_init_failure(self):
        """Should return None when Slack client cannot be initialized."""
        with patch(
            "services.slack_service._feedback.get_slack_client",
            side_effect=ValueError("Missing token"),
        ):
            with patch.dict("os.environ", {"RUNTIME_ENV": "prd"}):
                result = await send_tos_accepted_notification(
                    account_name="test-account",
                    account_display_name="Test Account",
                    user_email="user@example.com",
                    tos_version="v1.0",
                )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_unexpected_error(self):
        """Should return None on unexpected exceptions."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = RuntimeError("unexpected")

        with patch.dict("os.environ", {"RUNTIME_ENV": "prd"}):
            result = await send_tos_accepted_notification(
                account_name="test-account",
                account_display_name="Test Account",
                user_email="user@example.com",
                tos_version="v1.0",
                client=mock_client,
            )

        assert result is None
