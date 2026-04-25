"""Tests for tools.toast_tool._llm."""

from unittest.mock import MagicMock, patch


class TestToastLlmCall:
    @patch("tools.toast_tool._llm.get_client")
    @patch("tools.toast_tool._llm.Agent")
    @patch("tools.toast_tool._llm.Groq")
    def test_updates_span_on_successful_call(
        self,
        mock_groq_cls: MagicMock,
        mock_agent_cls: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from tools.toast_tool._llm import llm_call

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_run_result = MagicMock()
        mock_run_result.content = "Parsed: 1x Cheeseburger"
        mock_agent = MagicMock()
        mock_agent.run.return_value = mock_run_result
        mock_agent_cls.return_value = mock_agent

        result = llm_call(
            system_prompt="Parse order items",
            prompt="One cheeseburger",
            name="test",
        )

        assert result == "Parsed: 1x Cheeseburger"
        mock_client.update_current_span.assert_called_once()
        call_kwargs = mock_client.update_current_span.call_args[1]
        assert call_kwargs["input"] == "One cheeseburger"
        assert "system_prompt" in call_kwargs["metadata"]
