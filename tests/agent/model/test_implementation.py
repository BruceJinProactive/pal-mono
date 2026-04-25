"""Tests for agent.model._implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice


def _make_chat_completion() -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl-test",
        object="chat.completion",
        created=1234567890,
        model="gpt-4",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="Hello"),
                finish_reason="stop",
            )
        ],
    )


@pytest.mark.asyncio
class TestCallLlmDefault:
    @patch("agent.model._implementation.get_client")
    @patch("agent.model._implementation._get_deployment_name", return_value="gpt-4")
    @patch("agent.model._implementation._build_azure_client")
    async def test_updates_span_with_input_and_metadata(
        self,
        mock_build_client: MagicMock,
        mock_get_deployment: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.model._config import ModelOptions
        from agent.model._implementation import call_llm_default

        mock_azure = AsyncMock()
        mock_azure.chat.completions.create.return_value = _make_chat_completion()
        mock_build_client.return_value = mock_azure

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        params = {"messages": [{"role": "user", "content": "Hi"}], "temperature": 0.7}
        result = await call_llm_default(ModelOptions.GPT_4O, params)

        assert result.id == "chatcmpl-test"
        mock_client.update_current_span.assert_called_once()
        call_kwargs = mock_client.update_current_span.call_args[1]
        assert call_kwargs["metadata"]["streaming"] is False
        assert call_kwargs["metadata"]["provider"] == "azure"
        assert "input" in call_kwargs


@pytest.mark.asyncio
class TestCallLlmStream:
    @patch("agent.model._implementation.get_client")
    @patch("agent.model._implementation._get_deployment_name", return_value="gpt-4")
    @patch("agent.model._implementation._build_azure_client")
    async def test_updates_span_with_input_and_streaming_metadata(
        self,
        mock_build_client: MagicMock,
        mock_get_deployment: MagicMock,
        mock_get_client: MagicMock,
    ) -> None:
        from agent.model._config import ModelOptions
        from agent.model._implementation import call_llm_stream

        mock_response = AsyncMock()
        mock_response.__aiter__ = AsyncMock(return_value=iter([]))
        mock_azure = AsyncMock()
        mock_azure.chat.completions.create.return_value = mock_response
        mock_build_client.return_value = mock_azure

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        params = {"messages": [{"role": "user", "content": "Hi"}]}
        await call_llm_stream(ModelOptions.GPT_4O, params)

        mock_client.update_current_span.assert_called_once()
        call_kwargs = mock_client.update_current_span.call_args[1]
        assert call_kwargs["metadata"]["streaming"] is True
        assert call_kwargs["metadata"]["provider"] == "azure"
        assert "input" in call_kwargs
