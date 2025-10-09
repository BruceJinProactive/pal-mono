from typing import Optional

from pydantic import BaseModel


class CreateFAQRequest(BaseModel):
    """Create FAQ Request Model"""

    question: str
    answer: str


class UpdateFAQRequest(BaseModel):
    """Update FAQ Request Model"""

    question: Optional[str] = None
    answer: Optional[str] = None


class FAQ(BaseModel):
    """FAQ Model"""

    id: str
    account_id: str
    question: str
    answer: str
    created_at: str
    updated_at: str


class ListFAQsResponse(BaseModel):
    """List FAQs Response Model"""

    faqs: list[FAQ]
    total: int
