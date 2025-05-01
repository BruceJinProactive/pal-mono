import agno.agent.agent
from agno.models.openai.chat import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from ddtrace.llmobs.decorators import agent
from pydantic import BaseModel, Field

import db
from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.tool import get_tools
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

        model = OpenAIChat(id="gpt-4o")

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
            stream=config.stream,
        )

        self._agent = agent

    @agent
    async def arun(self, input: Input) -> Output:
        result = await self._agent.arun(
            input.get_prompt(), stream=self._agent.is_streamable
        )
        if self._agent.is_streamable:
            return result
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
