from dataclasses import dataclass


@dataclass
class AgentParams:
    name: str | None
    description: str | None
    communication_style: str | None
    interaction_guidelines: str | None
    raw_config: dict | None
