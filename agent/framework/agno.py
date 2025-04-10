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
        agent = agno.agent.agent.Agent(
            # persona
            name=config.persona.name,
            role=config.persona.role,
            description=config.persona.description,
            ### Metadata ###
            agent_id=config.metadata.agent_id,
            user_id=config.metadata.user_id,
            session_id=config.metadata.session_id,
            # model
            model=OpenAIChat(id="gpt-4o"),
            # memory
            # Use mem0 for memory
            ### Knowledge ###
            # knowledge_base=get_knowledge(config.knowledge), # NOTE: use our own search tool
            knowledge=None,
            # search_knowledge=config.knowledge.enabled,
            ### Tools ###
            tools=[
                tool for tool in get_tools(config.tool, config.knowledge)
            ],  # construct search knowledge tool
            # storage
            storage=PostgresAgentStorage(
                table_name=f"{config.metadata.account_name}_storage_agno",
                db_url=db.db_url,
            ),
            add_history_to_messages=True,
            num_history_responses=10,
            response_model=ResponseModel,
            additional_context=config.additional_context,
        )

        self._agent = agent

    @agent
    async def arun(self, input: Input) -> Output:
        result = await self._agent.arun(input.get_prompt())

        response_format = result.content

        if not isinstance(response_format, ResponseModel):
            logger.error(
                f"Error with getting proper response format: {response_format}"
            )
            return Output(content="")

        content = response_format.content
        escalated = response_format.escalated
        closing_conversation = response_format.closing_conversation

        logger.info(f"Current Session ID: {self._agent.session_id}")

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
