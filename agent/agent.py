import asyncio

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow

from agent.config import AgentConfig
from agent.framework import Framework, PhiDataAgent
from agent.input_output import Input, Output
from agent.memory import get_memory_context, update_memory


class Agent:
    """
    The Agent class is responsible for initializing and running
    with the provided configuration.
    """

    def __init__(self, config: AgentConfig):
        """
        Initializes the Agent with the given configuration.

        Args:
            config (AgentConfig): The configuration for the agent.

        Raises:
            ValueError: If the framework specified in the configuration is not supported.
        """
        framework = (
            config.metadata.framework
            if isinstance(config.metadata.framework, Framework)
            else Framework.PHIDATA
        )
        if framework != Framework.PHIDATA:
            raise ValueError(f"Unsupported framework: {framework}")

        self._agent = PhiDataAgent(config)
        self._metadata = config.metadata

        # Set up Datadog LLM Observability
        LLMObs.enable(
            ml_app=config.metadata.account_name,
            agentless_enabled=True,
        )

    @workflow
    async def arun(self, input: Input) -> Output:
        """
        Runs the agent asynchronously with the given input.

        Args:
            input (Input): The input data for the agent.

        Returns:
            Output: The output data from the agent.
        """

        # Update memory with the user's input
        asyncio.create_task(
            update_memory(
                user_id=self._metadata.user_id,  # type: ignore
                content=input.content,  # type: ignore
            )  # type: ignore
        )
        memories = await get_memory_context(user_id=self._metadata.user_id)  # type: ignore
        input.memories = memories

        output = await self._agent.arun(input)  # type: ignore

        return output
