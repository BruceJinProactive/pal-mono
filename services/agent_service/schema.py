from dataclasses import dataclass

from db.tables.agents import AgentType


@dataclass
class AgentParams:
    name: str | None = None
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
    agent_type: AgentType | None = None
