from uuid import UUID

from pydantic import BaseModel


class CreateFAQRequest(BaseModel):
    """Create FAQ Request Model"""

    account_id: UUID
    question: str
    answer: str


class FAQ(BaseModel):
    """FAQ Model"""

    id: str
    account_id: str
    question: str
    answer: str
    created_at: str
    updated_at: str
