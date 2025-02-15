import agno.agent.agent
from agno.models.openai.chat import OpenAIChat
from agno.storage.agent.postgres import PostgresAgentStorage
from ddtrace.llmobs.decorators import agent

import db
from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.tool import get_tools


class AgnoAgent:
    def __init__(self, config: AgentConfig):
        agent = agno.agent.agent.Agent(
            # persona
            name=config.persona.name,
            role=config.persona.role,
            description=config.persona.description,
            # metadata
            agent_id=config.metadata.agent_id,
            user_id=config.metadata.user_id,
            session_id=config.metadata.session_id,
            # model
            model=OpenAIChat(id="gpt-4o"),
            # memory
            # Use mem0 for memory
            # knowledge
            # knowledge_base=get_knowledge(config.knowledge), # NOTE: use our own search tool
            knowledge=None,
            # search_knowledge=config.knowledge.enabled,
            # tools
            tools=[
                tool for tool in get_tools(config.tool, config.knowledge)
            ],  # construct search knowledge tool
            # storage
            storage=PostgresAgentStorage(
                table_name=f"{config.metadata.account_name}_storage_agno",
                db_url=db.db_url,
            ),
            add_history_to_messages=True,
            num_history_responses=5,
            response_model=None,
            debug_mode=True,
        )

        self._agent = agent

    @agent
    async def arun(self, input: Input) -> Output:
        result = await self._agent.arun(input.get_prompt())
        content = result.content

        documents = []
        images = []

        return (
            Output(content=content, documents=documents, images=images)
            if content is not None
            else Output(content="", documents=documents, images=images)
        )
