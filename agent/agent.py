import asyncio
import os
import time

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow

from agent.config import AgentConfig, AgentFramework
from agent.framework import AgnoAgent
from agent.guardrails import check_input_bedrock
from agent.input_output import Input, Output
from agent.memory import get_memory_context, update_memory
from utils.log import logger


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
        logger.info(f"{config.metadata.user_id}: Agent.__init__")
        commit_start = time.perf_counter()
        self._agent = AgnoAgent(config)
        logger.info(
            f"{config.metadata.user_id}: Agent.__init__ Done, Took {time.perf_counter() - commit_start:.4f}s"
        )
        self._metadata = config.metadata

        logger.info(f"{config.metadata.user_id}: Datadog LLM Observability")
        commit_start = time.perf_counter()
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
        logger.info(
            f"{config.metadata.user_id}: Datadog LLM Observability done, Took {time.perf_counter() - commit_start:.4f}s"
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
        logger.info(f"{input.sender_identifier}: Running LLMObs")
        commit_start = time.perf_counter()
        LLMObs.annotate(
            tags={
                "account_name": self._metadata.account_name,
                "user_id": self._metadata.user_id,
                "session_id": self._metadata.session_id,
                "agent_id": self._metadata.agent_id,
            }
        )
        logger.info(
            f"{input.sender_identifier}: Running LLMObs Done, Took {time.perf_counter() - commit_start:.4f}s"
        )
        # Update memory with the user's input
        asyncio.create_task(
            update_memory(
                user_id=self._metadata.user_id,  # type: ignore
                content=input.content,  # type: ignore
            )  # type: ignore
        )
        logger.info(f"{input.sender_identifier}: get_memory_context")
        commit_start = time.perf_counter()
        testing_accounts = ["proactiveailab", "palona"]
        if self._metadata.account_name not in testing_accounts:
            # TODO: migrate to memory tools once implemeted
            memories = await get_memory_context(user_id=self._metadata.user_id)  # type: ignore
            input.memories = memories
        logger.info(
            f"{input.sender_identifier}: get_memory_context done, Took {time.perf_counter() - commit_start:.4f}s"
        )
        # Enable guardrails solely for LAT environment
        if (
            os.getenv("RUNTIME_ENV", "NA") in ["lat", "stg"]
            and not self._agent._agent.is_streamable  # ISSUE: a temporary fix to avoid guardrails for streaming agents to reudce latency latency
        ):
            safe = check_input_bedrock(input.content)
            if not safe:
                return Output(
                    content="We cannot process your input. Please try again with a different input."
                )
        logger.info(f"{input.sender_identifier}: self._agent.arun")
        commit_start = time.perf_counter()
        output = await self._agent.arun(input)  # type: ignore
        logger.info(
            f"{input.sender_identifier}: self._agent.arun done, Took {time.perf_counter() - commit_start:.4f}s"
        )
        return output
