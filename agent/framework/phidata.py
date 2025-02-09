import phi.agent.agent
from phi.model.openai.chat import OpenAIChat
from phi.storage.agent.postgres import PgAgentStorage

import db
from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.knowledge import get_knowledge
from agent.tool import get_tools


class PhiDataAgent:
    def __init__(self, config: AgentConfig):
        agent = phi.agent.agent.Agent(
            # persona
            name=config.persona.name,
            role=config.persona.role,
            description=config.persona.description,
            # metadata
            agent_id=config.metadata.agent_id,
            user_id=config.metadata.user_id,
            session_id=config.metadata.session_id,
            # model
            provider=OpenAIChat(id="gpt-4o"),
            # memory
            # Use mem0 for memory
            # knowledge
            knowledge_base=get_knowledge(config.knowledge),
            search_knowledge=config.knowledge.enabled,
            # tools
            tools=[tool for tool in get_tools(config.tool)],
            # storage
            storage=PgAgentStorage(
                table_name=f"{config.metadata.account_name}_storage",
                db_url=db.db_url,
            ),
            # Phidata required
            add_chat_history_to_messages=False,
            num_history_responses=0,
            output_model=None,
            debug_mode=True,
        )

        self._agent = agent

    def run(self, input: Input) -> Output:
        content = self._agent.run(input.get_prompt()).content
        return Output(content=content) if content is not None else Output(content="")

    async def arun(self, input: Input) -> Output:
        result = await self._agent.arun(input.get_prompt())
        content = result.content

        documents = []
        images = []

        extra_data = result.extra_data
        if extra_data and extra_data.context and extra_data.context[0].docs:
            res_references = extra_data.context[0].docs
            for reference in res_references:
                ref_type = None
                metadata = reference["meta_data"]

                if "file_type" in metadata:
                    ref_type = metadata["file_type"]

                if ref_type and ref_type.startswith("image"):
                    images.append(metadata["file_path"])
                else:
                    documents.append(metadata["file_path"])

        return (
            Output(content=content, documents=documents, images=images)
            if content is not None
            else Output(content="", documents=documents, images=images)
        )
