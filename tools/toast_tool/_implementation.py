from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata


class ToastTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="toast_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)
        self.register(self.check_address)

    @tool
    def get_store_info(self) -> str:
        raise Exception("Not Implemented")

    @tool
    def check_online_ordering_status(self) -> str:
        raise Exception("Not Implemented")

    @tool
    def checkout_order(self) -> str:
        raise Exception("Not Implemented")

    @tool
    def check_address(self) -> str:
        raise Exception("Not Implemented")
