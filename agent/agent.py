import asyncio
import os

# AsyncIterator from typing is for type hint only, not for runtime check
from collections.abc import AsyncIterator as _AsyncIterator
from typing import AsyncIterator

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow

from agent.config import AgentConfig
from agent.framework import AgnoAgent
from agent.guardrails import check_input_bedrock
from agent.input_output import Input, Output
from agent.memory import update_memory
from utils.dd import is_testing_mode, safe_annotate, send_dd_histogram_metrics, traced


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
        """
        # Default to AgnoAgent
        self._agent = AgnoAgent(config)

        self._metadata = config.metadata

        # Set up Datadog LLM Observability (skip for testing requests)
        if not is_testing_mode():
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
        safe_annotate(
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

        # Start agent task
        agent_task = asyncio.create_task(self._agent.arun(input))  # type: ignore

        # Run guardrail check if enabled
        guardrail_id = os.getenv("AWS_BEDROCK_GUARDRAIL_ID", "")
        if guardrail_id:
            guardrail_task = asyncio.create_task(
                asyncio.to_thread(check_input_bedrock, input.content)
            )
            safe = await guardrail_task
            if not safe:
                return Output(
                    content="We cannot process your input. Please try again with a different input."
                )

        output = await agent_task

        if isinstance(output, _AsyncIterator):
            # This should never happen in non-streaming mode
            safe_annotate(
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
                safe_annotate(
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
                    send_dd_histogram_metrics(
                        "agent.start_streaming",
                        input.request_context.request_time,
                        [
                            f"agent_id:{self._metadata.agent_id}",
                            f"account_name:{self._metadata.account_name}",
                        ],
                    )
                    output_stream = await self._agent.arun(input)  # type: ignore
                    if not isinstance(output_stream, _AsyncIterator):
                        safe_annotate(
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
                            f"agent_id:{self._metadata.agent_id}",
                            f"account_name:{self._metadata.account_name}",
                        ],
                    )

                    async for chunk in output_stream:
                        chunk_count += 1
                        if chunk_count == 1:
                            safe_annotate(tags={"first_chunk_received": True})
                            send_dd_histogram_metrics(
                                "agent.received_first_chunk",
                                input.request_context.request_time,
                                [
                                    f"agent_id:{self._metadata.agent_id}",
                                    f"account_name:{self._metadata.account_name}",
                                ],
                            )

                        output_content += chunk.content
                        yield chunk

                    safe_annotate(
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
