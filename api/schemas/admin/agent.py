from typing import List

from pydantic import BaseModel


class Agent(BaseModel):
    """Agent Model"""

    id: str
    name: str
    description: str | None
    communication_style: str | None
    interaction_guidelines: str | None
    raw_config: dict
    created_at: int  # timestamp in seconds and UTC tz
    updated_at: int  # timestamp in seconds and UTC tz
    projects: list[str]


class ListAgentsResponse(BaseModel):
    """List Agents Response"""

    agents: List[Agent]
