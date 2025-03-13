from pydantic import BaseModel


class Project(BaseModel):
    """Project Model"""

    id: str
    name: str
    raw_config: dict
    channel_identifiers: list[str]
    agent_id: str
