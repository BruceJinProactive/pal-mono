from agno.tools.toolkit import Toolkit

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from utils.ordering._query_engine import create_query_engine


class OloTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="olo_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None

        # Register tools

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name
        )
