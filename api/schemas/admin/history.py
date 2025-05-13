from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ChangeLogSummary(BaseModel):
    id: UUID
    account_id: UUID
    resource_type: str
    resource_id: str
    author: str
    action: str
    created_at: datetime


class ListChangeLogsResponse(BaseModel):
    changes: List[ChangeLogSummary]
    total_changes: int
    total_pages: int


class ChangeField(BaseModel):
    field: str
    old_value: Optional[str]
    new_value: Optional[str]


class ChangeLogDetails(BaseModel):
    info: ChangeLogSummary
    fields: list[ChangeField]
