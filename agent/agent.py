from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent

from agent.config import AgentConfig
from agent.framework import Framework, PhiDataAgent
from agent.input_output import Input, Output


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

        # Set up Datadog LLM Observability
        LLMObs.enable(
            ml_app=config.metadata.account_name,
            agentless_enabled=True,
        )

    @agent
    def run(self, input: Input) -> Output:
        """
        Runs the agent synchronously with the given input.

        Args:
            input (Input): The input data for the agent.

        Returns:
            Output: The output data from the agent.
        """
        return self._agent.run(input)

    @agent
    async def arun(self, input: Input) -> Output:
        """
        Runs the agent asynchronously with the given input.

        Args:
            input (Input): The input data for the agent.

        Returns:
            Output: The output data from the agent.
        """
        return await self._agent.arun(input)
