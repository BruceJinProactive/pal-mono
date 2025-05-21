from typing import AsyncIterator

import agno.agent.agent
from agno.models.openai.chat import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent
from pydantic import BaseModel, Field

import db
from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.tool import get_tools
from utils.dd import trace_block
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
        storage = PostgresAgentStorage(
            table_name=f"{config.metadata.account_name}_storage_agno",
            db_url=db.db_url,
        )

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
                add_history_to_messages=True,
                num_history_responses=10,
                response_model=(
                    ResponseModel if not config.stream else None
                ),  # NOTE: stream response model is not supported by AGNO
                additional_context=config.additional_context,
            )

        self._agent = agent

    async def arun(self, input: Input) -> Output | AsyncIterator[Output]:
        # Handle streaming case
        if not input.stream:
            return await self._arun_with_workflow(input)

        return self._create_traced_stream_iterator(input)

    @agent(name="AgnoAgent")
    async def _arun_with_workflow(self, input: Input) -> Output:
        with trace_block("Agno Core Agent Processing"):
            result = await self._agent.arun(input.get_prompt(), stream=input.stream)

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
                    result = await self._agent.arun(
                        input.get_prompt(), stream=input.stream
                    )
                    try:
                        async for chunk in result:
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
