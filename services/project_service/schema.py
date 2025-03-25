import uuid
from dataclasses import dataclass


@dataclass
class ProjectParams:
    display_name: str | None = None
    agent_id: uuid.UUID | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None
