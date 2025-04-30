from enum import Enum

from pydantic import BaseModel


class ResourceType(str, Enum):
    Agent = "agents"
    Project = "projects"


class ListKnowledgeFileResponse(BaseModel):
    files: list[str] = []
