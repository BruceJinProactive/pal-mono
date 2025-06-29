import asyncio
import datetime
import uuid
from typing import AsyncIterator, Optional

import agno.agent.agent
from agno.models.message import Message
from agno.models.openai.chat import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent
from pydantic import BaseModel, Field

import db
from agent.config import AgentConfig, StorageProvider
from agent.input_output import Input, Output
from agent.memory import MemoryProvider
from agent.memory._implementation import get_all_memories
from agent.storage._implementation import query_history_messages
from agent.tool import get_tools
from utils.dd import send_dd_histogram_metrics, trace_block
from utils.log import logger

MODEL_PROVIDER_MAP = {
    "openai": OpenAIChat,
}


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
        if config.storage_provider == StorageProvider.AGNO:
            storage = PostgresAgentStorage(
                table_name=f"{config.metadata.account_name}_storage_agno",
                db_url=db.db_url,
            )
            add_history_to_messages = True
            logger.debug(
                f"Agent: {config.metadata.agent_id} is using {config.storage_provider} Storage"
            )
        elif config.storage_provider == StorageProvider.PALSTORAGE:
            storage = None
            add_history_to_messages = False
            logger.debug(
                f"Agent: {config.metadata.agent_id} is using {config.storage_provider} Storage"
            )
        else:
            raise ValueError(f"Storeage: {config.storage_provider} is invalid")

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
                storage=storage,
                add_history_to_messages=add_history_to_messages,
                num_history_responses=10,
                response_model=(
                    ResponseModel if not config.stream else None
                ),  # NOTE: stream response model is not supported by AGNO
                additional_context=config.additional_context,
            )

        self._agent = agent
        self._storage_provider = config.storage_provider
        self._memory_config = config.memory
        self._user_id = config.metadata.user_id
        self._session_id = uuid.UUID(config.metadata.session_id)
        self._agent_id = config.metadata.agent_id
        self._account_name = config.metadata.account_name

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
                                "streaming:true",
                                "agent:agno",
                                f"agent_id:{self._agent_id}",
                                f"account_name:{self._account_name}",
                            ],
                        )

                        index = 0
                        async for chunk in result:
                            index += 1
                            if index == 1:
                                send_dd_histogram_metrics(
                                    "framework_agent.received_first_chunk",
                                    input.request_context.request_time,
                                    [
                                        "streaming:true",
                                        "agent:agno",
                                        f"agent_id:{self._agent_id}",
                                        f"account_name:{self._account_name}",
                                    ],
                                )

                            output_content += chunk.content
                            yield Output(
                                content=(
                                    chunk.content
                                    if hasattr(chunk, "content")
                                    else chunk
                                ),
                                documents=[],
                                images=[],
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
            model = OpenAIChat(id="gpt-4o")
        else:
            provider = model_config.provider.lower()
            model_cls = MODEL_PROVIDER_MAP.get(provider)
            if model_cls:
                try:
                    model = model_cls(id=model_config.identifier)
                except Exception as e:
                    logger.warning(
                        f"Failed to load model {provider}, fallback to gpt-4o: {e}"
                    )
                    model = OpenAIChat(id="gpt-4o")
            else:
                logger.warning(f"Unknown provider {provider}, fallback to gpt-4o")
                model = OpenAIChat(id="gpt-4o")
        return model

    async def _build_model_inputs(
        self, input: Input
    ) -> tuple[Optional[str], Optional[list[Message]]]:
        if self._storage_provider == StorageProvider.AGNO:
            return input.get_prompt(), None
        elif self._storage_provider == StorageProvider.PALSTORAGE:
            current_time = datetime.datetime.now(datetime.timezone.utc)

            if (
                self._memory_config.enabled
                and self._memory_config.provider == MemoryProvider.PROMPT
            ):
                # Run both operations concurrently - memory operation in thread pool to avoid blocking
                messages, mem_content = await asyncio.gather(
                    self.get_history_messages(input),
                    asyncio.to_thread(lambda: asyncio.run(get_all_memories(self._user_id))),  # type: ignore
                )
                if mem_content:
                    mem_message = Message(role="developer", content=mem_content)
                    messages.append(mem_message)
                    logger.debug(
                        f"[PalMemory]: Find user info from memory: {mem_content}"
                    )
                else:
                    logger.debug(
                        f"[PalMemory]: No user info from memory for user: {self._user_id}"
                    )
            else:
                messages = await self.get_history_messages(input)

            send_dd_histogram_metrics(
                "framework_agent.query_history_messages_time_spent",
                current_time,
                [
                    f"streaming:{str(input.stream).lower()}",
                    f"conversation_id:{self._session_id}",
                    "agent:agno",
                    f"agent_id:{self._agent_id}",
                    f"account_name:{self._account_name}",
                ],
            )

            return None, messages

        else:
            return None, None

    async def get_history_messages(self, input: Input) -> list[Message]:
        if self._storage_provider == StorageProvider.PALSTORAGE:
            history_messages = await query_history_messages(self._session_id, limit=100)
        else:
            raise ValueError(
                f"history_message doesn't apply to {self._storage_provider}"
            )

        messages = [
            Message(role=msg.role, content=msg.content) for msg in history_messages
        ]

        if len(messages) < 1:
            logger.error(
                "[PalStorage] Message history should contain at least 1 message"
            )
        else:
            if messages[-1].content != input.content:
                logger.error(
                    f"[PalStorage] The latest message: {messages[-1].content} should be the current user input: {input.content}"
                )
            else:
                messages = messages[:-1]
        messages.append(Message(role="user", content=input.get_prompt()))
        return messages
