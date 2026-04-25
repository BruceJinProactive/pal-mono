"""Tests for tools.adora_tool._implementation — Langfuse migration paths."""

from typing import Any
from unittest.mock import MagicMock, patch


def _make_adora_tool(**overrides: Any) -> Any:
    """Create an AdoraTool without running __init__ (avoids asyncio/query engine)."""
    from tools.adora_tool._implementation import AdoraTool

    tool = object.__new__(AdoraTool)
    defaults = {
        "store_id": "TEST1",
        "namespace": "test",
        "index_name": "agents",
        "tool_metadata": MagicMock(
            account_name="testaccount", timezone="America/Los_Angeles"
        ),
        "qa_store": False,
        "token_api_endpoint": None,
        "general_api_endpoint": None,
        "backdoor_tool_prompt": {},
        "loyalty_enabled": False,
        "coupons_enabled": False,
        "default_coupon_id": None,
        "cached_store_info": None,
        "_adora_bearer_token": None,
        "query_engine": MagicMock(),
        "query_messages_tool": MagicMock(),
        "discounts": [],
        "order_construction_model": "llama",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(tool, k, v)
    return tool


class TestGetAdoraBearerToken:
    """Covers lines 138-139: start_as_current_observation in _get_adora_bearer_token."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_fetches_token_with_langfuse_observation(self, mock_get_client):
        from tools.adora_tool.classes import AdoraAccessToken

        tool = _make_adora_tool()
        tool._adora_bearer_token = None

        mock_token = MagicMock(spec=AdoraAccessToken)
        with patch.object(tool, "_fetch_adora_bearer_token", return_value=mock_token):
            result = tool._get_adora_bearer_token()

        assert result == mock_token
        mock_get_client().start_as_current_observation.assert_called_once_with(
            name="get_adora_bearer_token"
        )

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_cached_token(self, mock_get_client):
        from tools.adora_tool.classes import AdoraAccessToken

        cached = MagicMock(spec=AdoraAccessToken)
        tool = _make_adora_tool(_adora_bearer_token=cached)

        result = tool._get_adora_bearer_token()

        assert result == cached
        mock_get_client().start_as_current_observation.assert_not_called()


class TestFetchAdoraBearerToken:
    """Covers line 187: return None on exception."""

    @patch("tools.adora_tool._implementation.get_client_secret_with_fallback")
    @patch("tools.adora_tool._implementation._apis")
    def test_returns_none_on_exception(self, mock_apis, mock_secret):
        mock_secret.side_effect = Exception("secret not found")
        tool = _make_adora_tool(store_id="CUSTOM_STORE")

        result = tool._fetch_adora_bearer_token()

        assert result is None


class TestCheckOnlineOrderingStatus:
    """Covers line 230: error return path."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_adora_tool()
        with patch.object(
            tool, "_get_adora_bearer_token", side_effect=Exception("api down")
        ):
            result = tool.check_online_ordering_status()

        assert "Failed to check" in result


class TestGetStoreInfo:
    """Covers lines 262 (cached) and 290 (error)."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_cached_store_info(self, mock_get_client):
        tool = _make_adora_tool(cached_store_info="cached info")

        result = tool.get_store_info(date="2026-04-24")

        assert result == "cached info"

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_adora_tool()
        with patch.object(
            tool, "_get_adora_bearer_token", side_effect=Exception("fail")
        ):
            result = tool.get_store_info(date="2026-04-24")

        assert "Failed to get" in result


class TestValidateAddress:
    """Covers line 384: address validated success path."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._apis")
    @patch("tools.adora_tool._implementation._utils")
    def test_returns_success_when_address_valid(
        self, mock_utils, mock_apis, mock_get_client
    ):
        from tools.adora_tool.classes import DeliveryAddress

        mock_addr = MagicMock(spec=DeliveryAddress)
        mock_token = MagicMock()
        tool = _make_adora_tool(_adora_bearer_token=mock_token)

        mock_utils.build_validate_address_payload.return_value = (
            {"payload": "data"},
            "",
        )
        mock_apis.validate_address.return_value = (True, {"address": "123 Main"})

        success, message = tool._validate_address(mock_addr)

        assert success is True
        assert "validated" in message.lower()


class TestCheckAddress:
    """Covers line 330: return validate_order_message."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._llm")
    def test_returns_validation_message(self, mock_llm, mock_get_client):
        from tools.adora_tool.classes import DeliveryAddress

        tool = _make_adora_tool()
        mock_addr = MagicMock(spec=DeliveryAddress)
        mock_llm.llm_call.return_value = mock_addr

        with patch.object(
            tool,
            "_validate_address",
            return_value=(True, "Address is validated and is in the delivery zone."),
        ):
            result = tool.check_address("123 Main St, LA, CA 90001")

        assert "validated" in result.lower()


class TestGetRelevantDocs:
    """Covers line 463: update_current_span call."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._llm")
    def test_updates_span_with_input_output(self, mock_llm, mock_get_client):
        from tools.adora_tool.classes import SubQueries

        tool = _make_adora_tool()
        mock_llm.llm_call.return_value = SubQueries(queries=["pizza"])

        mock_node = MagicMock()
        mock_node.score = 0.5
        mock_node.text = "Pepperoni pizza"
        mock_node.id_ = "doc-1"
        mock_result = MagicMock()
        mock_result.source_nodes = [mock_node]
        # aquery() is the async method used in _get_relevant_docs
        tool.query_engine.aquery.return_value = mock_result

        tool._get_relevant_docs("I want pizza")

        # update_current_span is called with input and output
        mock_get_client().update_current_span.assert_called_once()
        call_kwargs = mock_get_client().update_current_span.call_args[1]
        assert call_kwargs["input"] == "I want pizza"


class TestFormatPhoneForDb:
    """Covers line 490: PHONE_PLACEHOLDER return for invalid phone."""

    @patch("tools.adora_tool._implementation._utils")
    def test_returns_placeholder_for_invalid_phone(self, mock_utils):
        mock_utils.format_phone_number.return_value = ""
        tool = _make_adora_tool()

        result = tool._format_phone_for_db("bad")

        assert result == "+10000000000"

    def test_returns_placeholder_for_none(self):
        tool = _make_adora_tool()

        result = tool._format_phone_for_db(None)

        assert result == "+10000000000"


class TestValidateCoupons:
    """Covers line 1134: error return in validate_coupons."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_adora_tool()
        with patch.object(
            tool, "_get_adora_bearer_token", side_effect=Exception("auth fail")
        ):
            result = tool.validate_coupons(["CODE1"])

        assert "error validating" in result.lower()


class TestGetLoyaltyInfo:
    """Covers lines 1161 (invalid phone) and 1190 (exception)."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._utils")
    def test_returns_error_for_invalid_phone(self, mock_utils, mock_get_client):
        mock_utils.format_phone_number.return_value = ""
        tool = _make_adora_tool()

        result = tool.get_loyalty_info("bad-phone")

        assert "valid phone number" in result.lower()

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._utils")
    def test_returns_error_on_exception(self, mock_utils, mock_get_client):
        mock_utils.format_phone_number.side_effect = Exception("unexpected")
        tool = _make_adora_tool()

        result = tool.get_loyalty_info("1234567890")

        assert "error retrieving" in result.lower()


class TestGetLastOrderStatus:
    """Covers line 1217: invalid phone return."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._utils")
    def test_returns_error_for_invalid_phone(self, mock_utils, mock_get_client):
        mock_utils.format_phone_number.return_value = ""
        tool = _make_adora_tool()

        result = tool.get_last_order_status("bad")

        assert "confirm your phone" in result.lower()


class TestGetMenuItemInfo:
    """Covers line 1320: exception return."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_adora_tool()
        tool.query_engine.query.side_effect = Exception("index error")

        result = tool.get_menu_item_info("pizza")

        assert "Failed to retrieve" in result


class TestFulfillOrder:
    """Covers lines 606 (exclude_fields) and 677 (unsupported type)."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._apis")
    @patch("tools.adora_tool._implementation._utils")
    def test_returns_error_on_unsupported_validate_type(
        self, mock_utils, mock_apis, mock_get_client
    ):
        tool = _make_adora_tool(qa_store=True)
        mock_token = MagicMock()
        tool._adora_bearer_token = mock_token

        mock_order = MagicMock()
        mock_order.promise_date_time = None
        mock_order.coupon_ids = []
        mock_order.coupon_codes = None
        mock_order.model_dump_json.return_value = (
            '{"customer": {"phone": "1234567890"}}'
        )
        mock_order.order_type = "takeout"
        mock_order.order_items = "1x Pizza"

        mock_utils.is_valid_phone_number.return_value = True

        # Return an unexpected type (not str and not AdoraOrderCalculationResult)
        mock_apis.validate_order.return_value = 12345

        result = tool._fulfill_order(mock_order, mock_token)

        assert "Failed to validate order" in result


class TestSaveOrderToDb:
    """Covers line 599: session.close() in finally block."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation.SyncSessionLocal")
    @patch("tools.adora_tool._implementation.save_order")
    def test_closes_session_in_finally(
        self, mock_save_order, mock_session_local, mock_get_client
    ):
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        mock_save_order.return_value = "txn-123"

        tool = _make_adora_tool()
        tool.tool_metadata.store_phone = "+11234567890"
        tool.tool_metadata.timezone = "America/Los_Angeles"

        mock_order = MagicMock()
        mock_order.customer.phone_number = "1234567890"
        mock_order.order_type = "takeout"
        mock_order.order_items = "1x Pizza"

        mock_validated = MagicMock()
        mock_validated.key = "ORDER-123"
        mock_validated.subTotal = 15.99

        tool._save_order_to_db(mock_order, mock_validated)

        mock_session.close.assert_called_once()


class TestCheckoutOrderException:
    """Covers line 1061: general exception return in checkout_order."""

    @patch("tools.adora_tool._implementation.get_client")
    @patch("tools.adora_tool._implementation._llm")
    def test_returns_please_try_again_on_exception(self, mock_llm, mock_get_client):
        tool = _make_adora_tool()
        # query_messages_tool.query_messages() raises
        tool.query_messages_tool.query_messages.side_effect = Exception("msg fail")

        result = tool.checkout_order()

        assert "try again" in result.lower()


class TestFormatOrderStatus:
    """Covers line 1282: exception in _format_order_status."""

    @patch("tools.adora_tool._implementation.get_client")
    def test_returns_error_on_exception(self, mock_get_client):
        tool = _make_adora_tool()

        # Pass an object whose orderDetail access raises
        mock_order = MagicMock()
        type(mock_order).orderDetail = property(
            lambda self: (_ for _ in ()).throw(Exception("bad data"))
        )

        result = tool._format_order_status(mock_order)

        assert "Error formatting" in result
