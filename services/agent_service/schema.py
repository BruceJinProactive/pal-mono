from dataclasses import dataclass


@dataclass
class AgentParams:
    name: str | None = None
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    raw_config: dict | None = None
