import asyncio
import os

# AsyncIterator from typing is for type hint only, not for runtime check
from collections.abc import AsyncIterator as _AsyncIterator
from typing import AsyncIterator

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow

from agent.config import AgentConfig, AgentFramework
from agent.framework import AgnoAgent
from agent.framework.pal_simple_agent import PalSimpleAgent
from agent.guardrails import check_input_bedrock
from agent.input_output import Input, Output
from agent.memory import update_memory
from utils.dd import send_dd_histogram_metrics, traced


class Agent:
    """
    The Agent class is responsible for initializing and running
    with the provided configuration.
    """

    @traced("Pal Agent Initialization")
    def __init__(self, config: AgentConfig):
        """
        Initializes the Agent with the given configuration.

        Args:
            config (AgentConfig): The configuration for the agent.

        Raises:
            ValueError: If the framework specified in the configuration is not
                supported.
        """
        framework = (
            config.metadata.framework
            if isinstance(config.metadata.framework, AgentFramework)
            else AgentFramework.AGNO
        )

        match framework:
            case AgentFramework.AGNO:
                self._agent = AgnoAgent(config)
            case AgentFramework.PAL_SIMPLE:
                self._agent = PalSimpleAgent(config)

        self._metadata = config.metadata

        # Set up Datadog LLM Observability
        LLMObs.enable(
            ml_app="pal",
            agentless_enabled=True,
        )

    async def arun(self, input: Input) -> Output | AsyncIterator[Output]:
        """
        Runs the agent asynchronously with the given input.

        Args:
            input (Input): The input data for the agent.

        Returns:
            Output | AsyncIterator[Output]: The output data from the agent.
            If input.stream is True, returns an AsyncIterator[Output].
            If input.stream is False, returns a single Output.
        """

        # For non-streaming case, use the standard workflow decorator
        if not input.stream:
            return await self._arun_with_workflow(input)

        # For streaming case, use a wrapper that maintains the workflow span
        return self._create_traced_stream_iterator(input)

    @workflow(name="Pal Agent Processing")
    async def _arun_with_workflow(self, input: Input) -> Output:
        """Internal method for non-streaming responses with workflow tracing"""
        LLMObs.annotate(
            tags={
                "account_name": self._metadata.account_name,
                "user_id": self._metadata.user_id,
                "session_id": self._metadata.session_id,
                "agent_id": self._metadata.agent_id,
                "streaming": False,
            }
        )

        # Update memory with the user's input
        self._update_memory(input.content)

        if os.getenv("AWS_BEDROCK_GUARDRAIL_ID", ""):
            safe = check_input_bedrock(prompt=input.content)
            if not safe:
                return Output(
                    content="We cannot process your input. Please try again with a different input."
                )

        output = await self._agent.arun(input)  # type: ignore
        if isinstance(output, _AsyncIterator):
            # This should never happen in non-streaming mode
            LLMObs.annotate(
                tags={"error": "Non-streaming result received in non-streaming mode"}
            )
            raise TypeError(
                "Expected an single Output in non-streaming mode, but got a AsyncIterator."
            )

        return output

    def _create_traced_stream_iterator(self, input: Input) -> AsyncIterator[Output]:
        """
        Creates an AsyncIterator that maintains the workflow span throughout its lifecycle.
        This ensures the entire streaming process is captured in the Datadog trace.
        """

        async def stream_wrapper() -> AsyncIterator[Output]:
            # Apply workflow decorator to a generator function to trace the entire stream lifecycle
            @workflow(name="Pal Agent Processing")
            async def process_stream() -> AsyncIterator[Output]:
                LLMObs.annotate(
                    input_data=input,
                    tags={
                        "account_name": self._metadata.account_name,
                        "user_id": self._metadata.user_id,
                        "session_id": self._metadata.session_id,
                        "agent_id": self._metadata.agent_id,
                        "streaming": True,
                    },
                )

                # Update memory with the user's input
                self._update_memory(input.content)

                try:
                    output_stream = await self._agent.arun(input)  # type: ignore
                    if not isinstance(output_stream, _AsyncIterator):
                        LLMObs.annotate(
                            tags={
                                "error": "Non-streaming result received in streaming mode"
                            }
                        )
                        raise TypeError(
                            "Expected an AsyncIterator in streaming mode, but got a single Output."
                        )

                    # Process each chunk within the same workflow span
                    chunk_count = 0
                    output_content = ""
                    send_dd_histogram_metrics(
                        "agent.waiting_first_chunk",
                        input.request_context.request_time,
                        [
                            "streaming:true",
                            f"agent_id:{self._metadata.agent_id}",
                            f"account_name:{self._metadata.account_name}",
                        ],
                    )

                    async for chunk in output_stream:
                        chunk_count += 1
                        if chunk_count == 1:
                            LLMObs.annotate(tags={"first_chunk_received": True})
                            send_dd_histogram_metrics(
                                "agent.received_first_chunk",
                                input.request_context.request_time,
                                [
                                    "streaming:true",
                                    f"agent_id:{self._metadata.agent_id}",
                                    f"account_name:{self._metadata.account_name}",
                                ],
                            )

                        output_content += chunk.content
                        yield chunk

                    LLMObs.annotate(
                        output_data=output_content, tags={"total_chunks": chunk_count}
                    )

                except Exception as e:
                    yield Output(content=f"Error in streaming response: {str(e)}")

            # Call the decorated function and return its iterator
            async for item in process_stream():
                yield item

        # Return the wrapped streaming iterator
        return stream_wrapper()

    def _update_memory(self, content: str):
        def run_detached(coro):
            def runner():
                asyncio.run(coro)

            asyncio.get_running_loop().run_in_executor(None, runner)

        run_detached(
            update_memory(
                user_id=self._metadata.user_id,  # type: ignore
                content=content,  # type: ignore
            )
        )
