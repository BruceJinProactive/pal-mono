"""Tests for tools.toast_tool._implementation — Langfuse migration paths."""

from typing import Any
from unittest.mock import MagicMock, patch


def _make_toast_tool(**overrides: Any) -> Any:
    """Create a ToastTool without running __init__."""
    from tools.toast_tool._implementation import ToastTool

    tool = object.__new__(ToastTool)
    defaults = {
        "store_id": "test-store",
        "tool_metadata": MagicMock(
            account_name="testaccount",
            timezone="America/Los_Angeles",
            session_id="sess-1",
            agent_id="agent-1",
        ),
        "general_api_endpoint": "https://api.test.com",
        "token_api_endpoint": "https://token.test.com",
        "query_engine": MagicMock(),
        "query_messages_tool": MagicMock(),
        "_cached_store_info": None,
        "enable_hosted_checkout": False,
        "skip_order_submission": False,
        "delivery_enabled": False,
        "enable_tipping": False,
        "name": "toast_tool",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(tool, k, v)
    return tool


class TestToastBearerTokenProperty:
    """Covers line 175: start_as_current_observation in _toast_bearer_token."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.get_toast_access_token_from_aws")
    def test_bearer_token_uses_langfuse_observation(
        self, mock_get_token, mock_get_client
    ):
        from tools.toast_tool._implementation import ToastTool

        mock_token = MagicMock()
        mock_get_token.return_value = mock_token

        tool = _make_toast_tool(general_api_endpoint="https://api.production.com")
        # cached_property uses __get__ not fget
        result = ToastTool._toast_bearer_token.__get__(tool, type(tool))

        assert result == mock_token
        mock_get_client().start_as_current_observation.assert_called_once_with(
            name="get_toast_bearer_token"
        )


class TestToastHostedPaymentCheckoutToken:
    """Covers line 186: start_as_current_observation."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.get_toast_access_token_from_aws")
    def test_hosted_checkout_token_uses_langfuse_observation(
        self, mock_get_token, mock_get_client
    ):
        from tools.toast_tool._implementation import ToastTool

        mock_token = MagicMock()
        mock_get_token.return_value = mock_token

        tool = _make_toast_tool()
        result = ToastTool._toast_hosted_payment_checkout_bearer_token.__get__(
            tool, type(tool)
        )

        assert result == mock_token
        mock_get_client().start_as_current_observation.assert_called_once_with(
            name="get_toast_hosted_payment_checkout_bearer_token"
        )


class TestToastHostedPaymentIframeToken:
    """Covers line 197: start_as_current_observation."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.get_toast_access_token_from_aws")
    def test_iframe_token_uses_langfuse_observation(
        self, mock_get_token, mock_get_client
    ):
        from tools.toast_tool._implementation import ToastTool

        mock_token = MagicMock()
        mock_get_token.return_value = mock_token

        tool = _make_toast_tool()
        # _toast_hosted_payment_iframe_bearer_token is a @property, not cached_property
        assert ToastTool._toast_hosted_payment_iframe_bearer_token.fget is not None
        result = ToastTool._toast_hosted_payment_iframe_bearer_token.fget(tool)

        assert result == mock_token
        mock_get_client().start_as_current_observation.assert_called_once_with(
            name="get_toast_hosted_payment_iframe_bearer_token"
        )


class TestGenerateIframePaymentLink:
    @patch("tools.toast_tool._implementation.shorten_url")
    def test_shortens_with_env_url_prefix(self, mock_shorten_url):
        mock_shorten_url.return_value = "https://pay.palona.ai/abc123"
        tool = _make_toast_tool(
            hosted_payment_iframe_endpoint="https://console.palona.ai/checkout/toast"
        )
        tool._payment_iframe_fernet = MagicMock()
        tool._payment_iframe_fernet.encrypt.return_value = b"encrypted-token"

        result = tool._generate_iframe_payment_link({"order": "order-1"})

        assert result == "https://pay.palona.ai/abc123"
        mock_shorten_url.assert_called_once_with(
            "https://console.palona.ai/checkout/toast?t=encrypted-token",
            use_env_url_prefix=True,
        )


class TestGetChatHistory:
    """Covers lines 914 (warning) and 918 (update_current_span)."""

    @patch("tools.toast_tool._implementation.get_client")
    def test_updates_span_with_chat_history(self, mock_get_client):
        tool = _make_toast_tool()
        tool.query_messages_tool.query_messages.return_value = (
            "User: I want a burger\nAgent: What size?"
        )

        result = tool._get_chat_history()

        assert "burger" in result
        mock_get_client().update_current_span.assert_called_once_with(
            output="User: I want a burger\nAgent: What size?"
        )

    @patch("tools.toast_tool._implementation.get_client")
    def test_logs_warning_on_error_indicator(self, mock_get_client):
        tool = _make_toast_tool()
        tool.query_messages_tool.query_messages.return_value = (
            "Error in getting chat history"
        )

        result = tool._get_chat_history()

        assert "Error" in result
        mock_get_client().update_current_span.assert_called_once()


class TestCheckoutOrder:
    """Covers line 838: exception in checkout_order."""

    @patch("tools.toast_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_toast_tool(enable_hosted_checkout=False)

        with patch.object(
            tool,
            "_checkout_order_traditional",
            side_effect=Exception("checkout failed"),
        ):
            result = tool.checkout_order()

        assert "Failed to process checkout" in result


class TestGetRestaurantLocation:
    """Covers line 482: returns None when coordinates missing."""

    @patch("tools.toast_tool._implementation.get_client")
    def test_returns_none_when_no_coordinates(self, mock_get_client):
        tool = _make_toast_tool()
        # Mock get_store_info to return JSON without lat/lng
        with patch.object(
            tool,
            "get_store_info",
            return_value='{"location": {}}',
        ):
            result = tool._get_restaurant_location()

        assert result is None


class TestTransformSelectionsForDb:
    """Covers line 1079: transformed['modifiers'] = mods branch."""

    @patch("tools.toast_tool._implementation.get_client")
    def test_includes_modifiers_when_present(self, mock_get_client):
        from tools.toast_tool._implementation import ToastTool

        mock_modifier = MagicMock()
        mock_modifier.item = MagicMock()
        mock_modifier.item.guid = "mod-1"
        mock_modifier.item.name = "Extra Cheese"
        mock_modifier.displayName = "Extra Cheese"
        mock_modifier.modifiers = None

        mock_selection = MagicMock()
        mock_selection.item = MagicMock()
        mock_selection.item.guid = "item-1"
        mock_selection.displayName = "Burger"
        mock_selection.quantity = 1
        mock_selection.modifiers = [mock_modifier]

        result = ToastTool._transform_selections_for_db([mock_selection])

        assert len(result) == 1
        assert "modifiers" in result[0]
        assert result[0]["modifiers"][0]["modifier_name"] == "Extra Cheese"


class TestGetExistingOrderFromToast:
    """Covers line 738: exception returns None."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.get_existing_order")
    def test_returns_none_on_exception(self, mock_get_order, mock_get_client):
        mock_get_order.side_effect = Exception("API error")
        tool = _make_toast_tool()
        tool._toast_bearer_token = MagicMock()

        result = tool._get_existing_order_from_toast("ext-123")

        assert result is None


class TestCheckoutOrderHosted:
    """Covers line 792: exception in _checkout_order_hosted."""

    @patch("tools.toast_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_toast_tool(skip_order_submission=True)

        with patch.object(
            tool, "_get_existing_order_from_db", side_effect=Exception("db error")
        ):
            result = tool._checkout_order_hosted()

        assert "Error processing checkout" in result


class TestConstructOrder:
    """Covers line 1256: general exception in _construct_order."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.llm_call")
    def test_returns_error_on_non_validation_exception(
        self, mock_llm_call, mock_get_client
    ):
        tool = _make_toast_tool()
        tool.query_messages_tool.query_messages.return_value = "User: checkout"
        tool.backdoor_tool_prompt = {}
        tool.order_construction_model = "llama"

        # llm_call returns None which triggers ValueError in the try block
        mock_llm_call.return_value = None

        with patch.object(tool, "_get_relevant_docs", return_value="menu docs"):
            result = tool._construct_order()

        assert "Failed to construct order" in result


class TestSubmitOrder:
    """Covers line 1417: exception in _submit_order."""

    @patch("tools.toast_tool._implementation.get_client")
    @patch("tools.toast_tool._implementation.submit_order")
    def test_returns_error_on_exception(self, mock_submit, mock_get_client):
        mock_submit.side_effect = Exception("submit failed")
        tool = _make_toast_tool()
        tool._toast_bearer_token = MagicMock()

        mock_order = MagicMock()
        result = tool._submit_order(mock_order)

        assert "error while submitting" in result.lower()
