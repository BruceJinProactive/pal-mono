from dataclasses import dataclass


@dataclass
class KnowledgeFile:
    name: str
    size: int  # in bytes
    created_at: str  # date the file was uploaded, e.g. 2025-04-29
