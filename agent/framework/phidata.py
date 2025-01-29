import phi.agent.agent

from agent.config import AgentConfig
from agent.input_output import Input, Output
from agent.knowledge import get_knowledge
from agent.memory import get_memory
from agent.model import get_model
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
            # Model
            provider=get_model(
                model_name=config.model.identifier, stream=config.model.stream
            ),
            # memory
            memory=get_memory(config.memory),
            # knowledge
            knowledge_base=get_knowledge(config.knowledge),
            # tools
            tools=[tool for tool in get_tools(config.tool)],
            # Phidata required
            add_chat_history_to_messages=False,
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
        return Output(content=content) if content is not None else Output(content="")
