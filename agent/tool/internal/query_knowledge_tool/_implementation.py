import json
from typing import Any

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool
from llama_index.core.indices.query.base import BaseQueryEngine
from phi.tools.toolkit import Toolkit

from agent.knowledge import KnowledgeConfig, get_knowledge
from utils.log import logger


class QueryKnowledgeTool(Toolkit):
    def __init__(self, knowledge_config: KnowledgeConfig):
        super().__init__(name="query_knowledge_tool")
        self.register(self.query_knowledge)

        # NOTE: for now it's just llamaindex
        self.knowledge: BaseQueryEngine = get_knowledge(knowledge_config)

    def _convert_documents_to_string(self, docs: list[dict[str, Any]]) -> str:
        if docs is None or len(docs) == 0:
            return ""

        return json.dumps(docs, indent=2)

    @tool
    def query_knowledge(self, query: str) -> str:
        """Use this function to search the knowledge base for information about a query.

        Args:
            query: The query to search for.

        Returns:
            str: A string containing the response from the knowledge base.
        """
        response = self.knowledge.query(query)
        docs_from_knowledge = []
        output_data = []
        for node in response.source_nodes:
            docs_from_knowledge.append(node.text)
            output_data.append({"text": node.text})

        logger.info(docs_from_knowledge)

        LLMObs.annotate(input_data=query, output_data=output_data)

        if not docs_from_knowledge:
            return "No documents found"

        return self._convert_documents_to_string(docs_from_knowledge)
