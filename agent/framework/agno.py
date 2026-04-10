import asyncio
import datetime
import uuid
from typing import AsyncIterator, Optional

import agno.agent.agent
from agno.models.message import Message
from agno.run.response import (
    RunResponseContentEvent,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from ddtrace.llmobs.decorators import agent
from pydantic import BaseModel, Field

from agent.config import AgentConfig
from agent.framework.internal.filler_words_manager import FillerWordsManager
from agent.input_output import Input, Output
from agent.model import ModelOptions, build_agno_model
from agent.storage._implementation import query_history_messages
from agent.tool import get_tools
from utils.dd import safe_annotate, send_dd_histogram_metrics
from utils.log import logger
from utils.otel import trace_block


class ResponseModel(BaseModel):
    """Used as structured output response by agent."""

    content: str
    escalated: bool = Field(
        description="Whether the current message should be escalated to a human user.",
        default=False,
    )
    closing_conversation: bool = Field(
        description="Whether or not a conversation should be closed.", default=False
    )


PII_FIELDS = {
    "phone_number",
    "email",
    "address",
    "credit_card",
    "customer_name",
    "delivery_address",
}


def _sanitize_value(value: object) -> object:
    """Recursively sanitize a value, redacting PII fields in nested structures."""
    if isinstance(value, dict):
        return _sanitize_tool_args(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and len(value) > 200:
        return f"<truncated: {len(value)} chars>"
    return value


def _sanitize_tool_args(tool_args: dict | None) -> dict:
    """Sanitize tool arguments by redacting PII fields and truncating large values.

    Handles nested dicts and lists recursively to prevent PII leakage
    in nested structures (e.g., {"customer": {"email": "user@example.com"}}).
    """
    if tool_args is None:
        return {}

    sanitized = {}
    for key, value in tool_args.items():
        if key.lower() in PII_FIELDS:
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = _sanitize_value(value)
    return sanitized


def _sanitize_result(result: str | None, max_length: int = 1000) -> str | None:
    """Truncate and redact PII patterns from tool result strings."""
    if result is None:
        return None
    truncated = result[:max_length] if len(result) > max_length else result
    # Redact common PII patterns in result text
    for field in PII_FIELDS:
        # Simple key:value pattern matching in result strings
        if field in truncated.lower():
            # Don't attempt regex — just note PII may be present
            pass
    return truncated


class AgnoAgent:
    def __init__(self, config: AgentConfig):

        tools = [
            tool
            for tool in get_tools(
                config.tool,
                config.knowledge,
                user_id=config.metadata.user_id,
            )
        ]  # Construct tools based on configuration (knowledge tools are conditionally added)

        model = self._get_agent_model(config)

        with trace_block("Agno Core Agent Creation"):
            agent = agno.agent.agent.Agent(
                ### Persona ###
                name=config.persona.name,
                role=config.persona.role,
                description=config.persona.description,
                ### Metadata ###
                agent_id=config.metadata.agent_id,
                user_id=config.metadata.user_id,
                session_id=config.metadata.session_id,
                ### Model ###
                model=model,
                ### Memory ###
                # Use mem0 for memory
                ### Knowledge ###
                knowledge=None,
                ### Tools ###
                tools=tools,  # type: ignore
                ### Storage ### # Note: To be replaced by our own session and message tables
                response_model=(ResponseModel if not config.stream else None),
                additional_context=config.additional_context,
            )

        self._agent = agent
        self.config = config
        self.filler_manager = FillerWordsManager(
            agent_id=config.metadata.agent_id,
            account_name=config.metadata.account_name,
            chat_filler_words_percentage=config.feature_config.chat_filler_words_percentage,
            tool_calling_filler_words_percentage=config.feature_config.tool_calling_filler_words_percentage,
        )

    async def arun(self, input: Input) -> Output | AsyncIterator[Output]:
        """
        Run the agent with the given input.

        Args:
            input: The input to process with optional history_messages

        Returns:
            Output or AsyncIterator[Output]: The agent's response
        """
        # Handle streaming case
        if not input.stream:
            return await self._arun_with_workflow(input)

        return self._create_traced_stream_iterator(input)

    @agent(name="AgnoAgent")
    async def _arun_with_workflow(self, input: Input) -> Output:
        message, messages = await self._build_model_inputs(input)

        result = await self._agent.arun(
            message,
            messages=messages,
            stream=input.stream,
        )
        # Handle non-streaming case
        response_format = result.content

        if not isinstance(response_format, ResponseModel):
            logger.error(
                (
                    f"Error with getting proper response format:{response_format}\n"
                    f"response type: {type(response_format)}\n"
                    f"agent stream: {self._agent.stream}\n"
                    f"response model: {self._agent.response_model}"
                )
            )
            return Output(content="")

        content = response_format.content
        escalated = response_format.escalated
        closing_conversation = response_format.closing_conversation

        documents = []
        images = []

        return (
            Output(
                content=content,
                documents=documents,
                images=images,
                escalated=escalated,
                closing_conversation=closing_conversation,
            )
            if content is not None
            else Output(content="", documents=documents, images=images)
        )

    def _create_traced_stream_iterator(self, input: Input) -> AsyncIterator[Output]:
        @agent(name="AgnoAgent")
        async def stream_wrapper() -> AsyncIterator[Output]:
            safe_annotate(
                input_data=input,
                tags={
                    "streaming": True,
                },
            )

            output_content = ""
            message, messages = await self._build_model_inputs(input)

            send_dd_histogram_metrics(
                "framework_agent.start_streaming",
                input.request_context.request_time,
                [
                    "agent:agno",
                    f"agent_id:{self.config.metadata.agent_id}",
                    f"account_name:{self.config.metadata.account_name}",
                ],
            )

            result = await self._agent.arun(
                message,
                messages=messages,
                stream=input.stream,
            )

            try:
                send_dd_histogram_metrics(
                    "framework_agent.waiting_first_chunk",
                    input.request_context.request_time,
                    [
                        "agent:agno",
                        f"agent_id:{self.config.metadata.agent_id}",
                        f"account_name:{self.config.metadata.account_name}",
                    ],
                )
                # Output chat filler words if configured
                filler_words = self.filler_manager.get_chat_filler_for_input(
                    input.content
                )

                if filler_words:
                    filler_output = Output(
                        content=filler_words,
                        documents=[],
                        images=[],
                    )
                    output_content += filler_output.content
                    yield filler_output

                chunk_index = 0
                filler_timeout = 10.0  # Send additional filler words every 10 seconds
                received_first_content = (
                    False  # Track if we've received any real content
                )

                # Create async iterator from result
                result_iter = result.__aiter__()
                pending_task = None  # Track the task waiting for next chunk

                while True:
                    # Create or reuse task to get next chunk
                    if pending_task is None:
                        pending_task = asyncio.create_task(result_iter.__anext__())

                    # Only use timeout if we haven't received first content yet
                    if not received_first_content:
                        done, pending = await asyncio.wait(
                            {pending_task}, timeout=filler_timeout
                        )

                        if not done:
                            # Timeout occurred, send filler word but keep task running

                            # Get another filler word
                            additional_filler = (
                                self.filler_manager.get_chat_filler_for_input(
                                    input.content
                                )
                            )

                            if additional_filler:
                                filler_output = Output(
                                    content=additional_filler,
                                    documents=[],
                                    images=[],
                                )
                                output_content += filler_output.content
                                yield filler_output

                            # Continue waiting for the same task (don't cancel it)
                            continue

                    try:
                        # Get the chunk from the completed task
                        chunk = await pending_task
                        pending_task = None  # Reset for next iteration
                    except StopAsyncIteration:
                        # Stream finished
                        break

                    # Process the chunk
                    if isinstance(chunk, RunResponseContentEvent):
                        # Skip chunks without valid content
                        content = getattr(chunk, "content", None)
                        if not content:
                            continue

                        # Mark that we've received first content - no more filler words needed
                        received_first_content = True

                        chunk_index += 1
                        if chunk_index == 1:
                            send_dd_histogram_metrics(
                                "framework_agent.received_first_chunk",
                                input.request_context.request_time,
                                [
                                    "agent:agno",
                                    f"agent_id:{self.config.metadata.agent_id}",
                                    f"account_name:{self.config.metadata.account_name}",
                                ],
                            )

                        chunk_output = Output(
                            content=content,
                            documents=[],
                            images=[],
                        )
                        output_content += chunk_output.content
                        yield chunk_output

                    elif isinstance(chunk, ToolCallStartedEvent):
                        # Output filler words when tool execution starts
                        tool_name = (
                            chunk.tool.tool_name
                            if chunk.tool and chunk.tool.tool_name
                            else "unknown"
                        )
                        tool_filler_words = (
                            self.filler_manager.get_tool_calling_filler_for_input(
                                input.content, tool_name
                            )
                        )

                        if tool_filler_words:
                            tool_filler_output = Output(
                                content=tool_filler_words,
                                documents=[],
                                images=[],
                            )
                            output_content += tool_filler_output.content
                            yield tool_filler_output

                    elif isinstance(chunk, ToolCallCompletedEvent):
                        # Emit structured log on tool call completion
                        tool_name = (
                            chunk.tool.tool_name
                            if chunk.tool and chunk.tool.tool_name
                            else "unknown"
                        )
                        tool_call_error = (
                            chunk.tool.tool_call_error if chunk.tool else False
                        )
                        tool_args = chunk.tool.tool_args if chunk.tool else None
                        result = chunk.tool.result if chunk.tool else None

                        # Sanitize tool args to prevent PII leakage
                        sanitized_args = _sanitize_tool_args(tool_args)

                        # Sanitize and truncate result
                        truncated_result = _sanitize_result(result)

                        # Build structured log data
                        log_data = {
                            "tool_name": tool_name,
                            "tool_call_error": tool_call_error,
                            "tool_args": sanitized_args,
                            "result": truncated_result,
                            "conversation_id": self.config.metadata.session_id,
                            "account_name": self.config.metadata.account_name,
                            "agent_id": self.config.metadata.agent_id,
                        }

                        # Emit error-level log for failures, debug-level for successes
                        if tool_call_error:
                            logger.error(
                                f"Tool call failed: {tool_name}", extra=log_data
                            )
                        else:
                            logger.debug(
                                f"Tool call succeeded: {tool_name}", extra=log_data
                            )
            except asyncio.CancelledError:
                logger.debug("[AgnoAgent] Stream cancelled (client disconnect)")
                raise

            except Exception as e:
                logger.error(f"Error streaming output: {e}")
                error_output = Output(content="Error streaming output")
                output_content += error_output.content
                yield error_output

            safe_annotate(output_data=output_content)

        return stream_wrapper()

    def _get_agent_model(self, config: AgentConfig):
        model_config = config.model
        if not model_config:
            return build_agno_model(ModelOptions.GPT_4O)
        else:
            model_name = model_config.identifier
            for model_option in ModelOptions:
                if model_name == model_option.model_name:
                    return build_agno_model(model_option)
            logger.warning(f"Failed to load model {model_name}, fallback to gpt-4o.")
            return build_agno_model(ModelOptions.GPT_4O)

    async def _build_model_inputs(
        self, input: Input
    ) -> tuple[Optional[str], Optional[list[Message]]]:
        current_time = datetime.datetime.now(datetime.timezone.utc)

        messages = await self.get_history_messages(input)

        send_dd_histogram_metrics(
            "framework_agent.query_history_messages_time_spent",
            current_time,
            [
                f"streaming:{str(input.stream).lower()}",
                f"conversation_id:{self.config.metadata.session_id}",
                "agent:agno",
                f"agent_id:{self.config.metadata.agent_id}",
                f"account_name:{self.config.metadata.account_name}",
            ],
        )

        return None, messages

    async def get_history_messages(self, input: Input) -> list[Message]:
        history_messages = await query_history_messages(
            uuid.UUID(self.config.metadata.session_id), limit=100
        )

        messages = [
            Message(role=msg.role, content=msg.content) for msg in history_messages
        ]

        if len(messages) < 1:
            logger.error(
                "[AgnoAgent] Message history should contain at least 1 message"
            )
        else:
            if messages[-1].content != input.content:
                logger.warning(
                    f"[AgnoAgent] The latest message: {messages[-1].content} should be the current user input: {input.content}"
                )
            else:
                messages = messages[:-1]
        messages.append(Message(role="user", content=input.get_prompt()))
        return messages
