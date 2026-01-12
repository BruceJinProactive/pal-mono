from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class KnowledgeFile:
    name: str
    size: int  # in bytes
    created_at: str  # date the file was uploaded, e.g. 2025-04-29


@dataclass
class NamespaceInfo:
    namespace: str
    index_name: str
    project_id: UUID
    project_name: str
    account_id: UUID
    account_name: str
    tool_name: Optional[str] = None
    provider: Optional[str] = None
