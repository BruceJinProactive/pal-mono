import json
import time
from typing import Any

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool
from llama_index.core.indices.query.base import BaseQueryEngine

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
        start_time = time.time()
        response = self.knowledge.query(query)
        retrieved_documents = [node.text for node in response.source_nodes]
        logger.info(f"Retrieved documents: {retrieved_documents}")
        logger.info(f"Knowledge retrieval time: {time.time() - start_time} seconds")

        LLMObs.annotate(
            input_data=query, output_data=[{"text": doc} for doc in retrieved_documents]
        )

        if not retrieved_documents:
            return "No documents found"

        return str(response)
