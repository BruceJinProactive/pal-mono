from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from utils.log import logger


class LiveKitTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        **kwargs,  # Accept and ignore unknown args from raw_config
    ):
        super().__init__(name="livekit_tool")
        self.tool_metadata = tool_metadata
        self.register(self.call_transfer)

    @tool
    async def call_transfer(self, purpose: str = "general") -> str:
        """
        Transfer the current call to the appropriate department based on purpose.

        Use when customer needs human assistance. The purpose determines which
        department/number receives the transferred call.

        This tool updates the LiveKit agent metadata to trigger a call transfer.

        Args:
            purpose: The reason for transfer. Common values:
                - "general": Default transfer destination
                - "faq": Questions about menu, hours, location, etc.
                - "complaint": Customer complaints or escalations
                - "order_support": Issues with existing orders
                - "catering": Catering inquiries

        NEVER invoke this tool if user is NOT communicating via voice channel.

        Returns:
            str: Success or error message about the call transfer attempt.
        """
        log_extra = {
            "project_id": str(self.tool_metadata.project_id),
            "account_name": self.tool_metadata.account_name,
        }

        # Validate channel — defense in depth
        if (
            hasattr(self.tool_metadata, "channel")
            and self.tool_metadata.channel
            and self.tool_metadata.channel != "voice"
        ):
            error_msg = "Call transfer is only available for voice calls. This conversation is not a voice call."
            logger.warning(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra={**log_extra, "channel": self.tool_metadata.channel},
            )
            return error_msg

        try:
            # TODO: Implement actual metadata update logic to trigger transfer
            logger.info(
                "[LiveKitTool.call_transfer] Call transfer requested via metadata update",
                extra={
                    **log_extra,
                    "user_id": str(self.tool_metadata.user_id),
                    "session_id": str(self.tool_metadata.session_id),
                    "purpose": purpose,
                },
            )

            # Placeholder return - will be implemented in next step
            return f"Call transfer requested for purpose '{purpose}'"

        except Exception as e:
            error_msg = f"Unexpected error occurred while transferring call: {e}"
            logger.error(
                f"[LiveKitTool.call_transfer] {error_msg}",
                extra={
                    **log_extra,
                    "purpose": purpose,
                },
                exc_info=True,
            )
            return error_msg
