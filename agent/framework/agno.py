import asyncio
import datetime
import time
import uuid
from typing import AsyncIterator, Optional

import agno.agent.agent
from agno.models.message import Message
from agno.run.response import RunResponseContentEvent
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent
from pydantic import BaseModel, Field

from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.memory import MemoryProvider
from agent.memory._implementation import get_all_memories
from agent.storage._implementation import query_history_messages
from agent.tool import get_tools
from services.llm_service import build_agno_model
from services.llm_service.schema import ModelOptions
from utils.dd import send_dd_histogram_metrics, trace_block
from utils.log import logger


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


class AgnoAgent:
    def __init__(self, config: AgentConfig):

        tools = [
            tool
            for tool in get_tools(
                config.tool,
                config.knowledge,
                config.memory,
                user_id=config.metadata.user_id,
            )
        ]  # Construct tools based on configuration (memory and knowledge tools are conditionally added)

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
        with trace_block("Agno Core Agent Processing"):

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
        async def stream_wrapper() -> AsyncIterator[Output]:
            @agent(name="AgnoAgent")
            async def process_stream() -> AsyncIterator[Output]:
                LLMObs.annotate(
                    input_data=input,
                    tags={
                        "streaming": True,
                    },
                )

                output_content = ""
                with trace_block("Agno Core Agent Processing"):
                    message, messages = await self._build_model_inputs(input)
                    logger.debug(
                        f"[AgnoAgent] start getting called at {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                        extra={
                            "agent_id": self.config.metadata.agent_id,
                            "account_name": self.config.metadata.account_name,
                        },
                    )
                    send_dd_histogram_metrics(
                        "framework_agent.start_streaming",
                        input.request_context.request_time,
                        [
                            "streaming:true",
                            "agent:agno",
                            f"agent_id:{self.config.metadata.agent_id}",
                            f"account_name:{self.config.metadata.account_name}",
                        ],
                    )

                    agent_model_info = self._agent.model
                    with LLMObs.llm(
                        model_name=(
                            agent_model_info.name if agent_model_info else "custom"
                        ),
                        model_provider=(
                            agent_model_info.provider if agent_model_info else "custom"
                        ),
                    ):
                        result = await self._agent.arun(
                            message,
                            messages=messages,
                            stream=input.stream,
                        )

                    logger.debug(
                        f"[AgnoAgent] called with {len(messages) if messages else 'None'} messages, streaming={input.stream}, return_type:{type(result)} at {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                        extra={
                            "agent_id": self.config.metadata.agent_id,
                            "account_name": self.config.metadata.account_name,
                        },
                    )

                    try:
                        send_dd_histogram_metrics(
                            "framework_agent.waiting_first_chunk",
                            input.request_context.request_time,
                            [
                                "streaming:true",
                                "agent:agno",
                                f"agent_id:{self.config.metadata.agent_id}",
                                f"account_name:{self.config.metadata.account_name}",
                            ],
                        )
                        logger.debug(
                            f"[AgnoAgent] waiting_first_chunk {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                            extra={
                                "agent_id": self.config.metadata.agent_id,
                                "account_name": self.config.metadata.account_name,
                            },
                        )

                        chunk_index = 0
                        async for chunk in result:
                            if isinstance(chunk, RunResponseContentEvent):
                                # Skip chunks without valid content
                                content = getattr(chunk, "content", None)
                                if not content:
                                    logger.debug(
                                        "[AgnoAgent] skipping chunk with empty/None content",
                                        extra={
                                            "agent_id": self.config.metadata.agent_id,
                                            "account_name": self.config.metadata.account_name,
                                            "chunk": chunk,
                                        },
                                    )
                                    continue

                                chunk_index += 1
                                if chunk_index == 1:
                                    send_dd_histogram_metrics(
                                        "framework_agent.received_first_chunk",
                                        input.request_context.request_time,
                                        [
                                            "streaming:true",
                                            "agent:agno",
                                            f"agent_id:{self.config.metadata.agent_id}",
                                            f"account_name:{self.config.metadata.account_name}",
                                        ],
                                    )
                                    logger.debug(
                                        f"[AgnoAgent] received_first_chunk {(time.time() - input.request_context.request_time.timestamp()) * 1000:.1f}ms",
                                        extra={
                                            "agent_id": self.config.metadata.agent_id,
                                            "account_name": self.config.metadata.account_name,
                                            "chunk": chunk,
                                        },
                                    )

                                output_content += content
                                yield Output(
                                    content=content,
                                    documents=[],
                                    images=[],
                                )
                            else:
                                logger.debug(
                                    f"[AgnoAgent] received non ResponseContent type chunk: {type(chunk)}",
                                    extra={
                                        "agent_id": self.config.metadata.agent_id,
                                        "account_name": self.config.metadata.account_name,
                                        "chunk": chunk,
                                    },
                                )

                    except Exception as e:
                        logger.error(f"Error streaming output: {e}")
                        yield Output(content="Error streaming output")
                LLMObs.annotate(output_data=output_content)

            async for item in process_stream():
                yield item

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

        if (
            self.config.memory.enabled
            and self.config.memory.provider == MemoryProvider.PROMPT
        ):
            # Run both operations concurrently - memory operation in thread pool to avoid blocking
            messages, mem_content = await asyncio.gather(
                self.get_history_messages(input),
                asyncio.to_thread(lambda: asyncio.run(get_all_memories(self.config.metadata.user_id))),  # type: ignore
            )
            if mem_content:
                mem_message = Message(role="developer", content=mem_content)
                messages.append(mem_message)
                logger.debug(f"[PalMemory]: Find user info from memory: {mem_content}")
            else:
                logger.debug(
                    f"[PalMemory]: No user info from memory for user: {self.config.metadata.user_id}"
                )
        else:
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
                logger.error(
                    f"[AgnoAgent] The latest message: {messages[-1].content} should be the current user input: {input.content}"
                )
            else:
                messages = messages[:-1]
        messages.append(Message(role="user", content=input.get_prompt()))
        return messages
