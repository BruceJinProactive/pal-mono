"""Tests for tools.utils.ordering._llm."""

from unittest.mock import MagicMock, patch


class TestLlmCall:
    @patch("tools.utils.ordering._llm.get_client")
    @patch("tools.utils.ordering._llm.Agent")
    @patch("tools.utils.ordering._llm.Groq")
    def test_updates_span_on_successful_call(
        self,
        mock_groq_cls: MagicMock,
        mock_agent_cls: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from tools.utils.ordering._llm import llm_call

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_run_result = MagicMock()
        mock_run_result.content = "Extracted: 2x Margherita"
        mock_agent = MagicMock()
        mock_agent.run.return_value = mock_run_result
        mock_agent_cls.return_value = mock_agent

        result = llm_call(
            system_prompt="Extract items",
            prompt="Two margherita pizzas please",
            name="test",
        )

        assert result == "Extracted: 2x Margherita"
        mock_client.update_current_span.assert_called_once()
        call_kwargs = mock_client.update_current_span.call_args[1]
        assert call_kwargs["input"] == "Two margherita pizzas please"
        assert call_kwargs["metadata"]["system_prompt"] == "Extract items"


class TestCallAnthropicClient:
    """Covers line 119: get_client().update_current_span() on successful anthropic call."""

    @patch("tools.utils.ordering._llm.get_client")
    @patch("tools.utils.ordering._llm.Anthropic")
    @patch("tools.utils.ordering._llm.get_server_secret_with_fallback")
    def test_updates_span_on_successful_text_completion(
        self,
        mock_get_secret: MagicMock,
        mock_anthropic_cls: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from anthropic.types import TextBlock

        from tools.utils.ordering._llm import _call_anthropic_client

        mock_get_secret.return_value = "fake-api-key"
        mock_langfuse = MagicMock()
        mock_get_client.return_value = mock_langfuse

        # Mock the Anthropic client response
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = [TextBlock(type="text", text="Order: 1x Burger")]
        mock_client.messages.create.return_value = mock_message

        result = _call_anthropic_client(
            system_prompt="Extract order",
            prompt="One burger please",
            response_format=None,
            name="test",
        )

        assert result == "Order: 1x Burger"
        mock_langfuse.update_current_span.assert_called_once()
        call_kwargs = mock_langfuse.update_current_span.call_args[1]
        assert call_kwargs["input"] == "One burger please"
        assert "system_prompt" in call_kwargs["metadata"]
