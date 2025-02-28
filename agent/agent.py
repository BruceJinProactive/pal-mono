import asyncio

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow

from agent.config import AgentConfig, AgentFramework
from agent.framework import AgnoAgent
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
            if isinstance(config.metadata.framework, AgentFramework)
            else AgentFramework.AGNO
        )
        if framework != AgentFramework.AGNO:
            raise ValueError(f"Unsupported framework: {framework}")

        self._agent = AgnoAgent(config)
        self._metadata = config.metadata

        # Set up Datadog LLM Observability
        LLMObs.enable(
            ml_app="pal",
            agentless_enabled=True,
        )
        LLMObs.annotate(
            tags={
                "user_id": config.metadata.user_id,
                "session_id": config.metadata.session_id,
            }
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
        LLMObs.annotate(
            tags={
                "account_name": self._metadata.account_name,
                "user_id": self._metadata.user_id,
                "session_id": self._metadata.session_id,
                "agent_id": self._metadata.agent_id,
            }
        )

        # Update memory with the user's input
        asyncio.create_task(
            update_memory(
                user_id=self._metadata.user_id,  # type: ignore
                content=input.content,  # type: ignore
            )  # type: ignore
        )
        if (
            self._metadata.account_name == "pizzamyheart"
            or self._metadata.account_name == "proactiveailab-pizza"
        ):
            # TODO: migrate to memory tools once implemeted
            memories = await get_memory_context(user_id=self._metadata.user_id)  # type: ignore
            input.memories = memories

        output = await self._agent.arun(input)  # type: ignore

        return output
