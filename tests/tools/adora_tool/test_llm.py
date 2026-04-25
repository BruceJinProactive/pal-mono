"""Tests for tools.adora_tool._llm — Langfuse update_current_span migration."""

from unittest.mock import MagicMock, patch


class TestAdoraLlmCall:
    """Covers line 160: get_client().update_current_span() after agent.run()."""

    @patch("tools.adora_tool._llm.get_client")
    @patch("tools.adora_tool._llm.Agent")
    @patch("tools.adora_tool._llm.Groq")
    def test_updates_span_on_successful_call(
        self,
        mock_groq_cls: MagicMock,
        mock_agent_cls: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from tools.adora_tool._llm import llm_call

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_run_result = MagicMock()
        mock_run_result.content = "Extracted: 2x Pepperoni"
        mock_agent = MagicMock()
        mock_agent.run.return_value = mock_run_result
        mock_agent_cls.return_value = mock_agent

        result = llm_call(
            system_prompt="Extract items",
            prompt="Two pepperoni pizzas",
            name="test",
        )

        assert result == "Extracted: 2x Pepperoni"
        mock_client.update_current_span.assert_called_once()
        call_kwargs = mock_client.update_current_span.call_args[1]
        assert call_kwargs["input"] == "Two pepperoni pizzas"
        assert call_kwargs["metadata"]["system_prompt"] == "Extract items"
