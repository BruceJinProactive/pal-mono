from pydantic import BaseModel


class Project(BaseModel):
    """Project Model"""

    id: str
    name: str
    display_name: str | None
    raw_config: dict
    channel_identifiers: list[str]
    agent_id: str
