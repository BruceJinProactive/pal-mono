from enum import Enum

from pydantic import BaseModel


class ResourceType(str, Enum):
    Agent = "agents"
    Project = "projects"


class KnowledgeFile(BaseModel):
    name: str
    size_bytes: int = 0
    created_at: str = "unknown"


class ListKnowledgeFileResponse(BaseModel):
    files: list[KnowledgeFile] = []
    total_files: int = 0
    total_pages: int = 0
