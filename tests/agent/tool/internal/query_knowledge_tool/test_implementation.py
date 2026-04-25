"""Tests for agent.tool.internal.query_knowledge_tool._implementation."""

from unittest.mock import MagicMock, patch


class TestQueryKnowledgeTool:
    @patch("agent.tool.internal.query_knowledge_tool._implementation.get_client")
    @patch(
        "agent.tool.internal.query_knowledge_tool._implementation.get_knowledge",
    )
    def test_query_updates_span_with_input_and_retrieved_docs(
        self, mock_get_knowledge: MagicMock, mock_get_client: MagicMock
    ) -> None:
        from agent.tool.internal.query_knowledge_tool._implementation import (
            QueryKnowledgeTool,
        )

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_node = MagicMock()
        mock_node.text = "We serve Italian food"
        mock_response = MagicMock()
        mock_response.source_nodes = [mock_node]
        mock_response.configure_mock(__str__=lambda self: "We serve Italian food")

        mock_engine = MagicMock()
        mock_engine.query.return_value = mock_response
        mock_get_knowledge.return_value = mock_engine

        tool = QueryKnowledgeTool(knowledge_config=MagicMock())
        result = tool.query_knowledge("What food do you serve?")

        assert "Italian" in result
        mock_client.update_current_span.assert_called_once_with(
            input="What food do you serve?",
            output=[{"text": "We serve Italian food"}],
        )
