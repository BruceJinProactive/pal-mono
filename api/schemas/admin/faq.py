from pydantic import BaseModel


class CreateFAQRequest(BaseModel):
    """Create FAQ Request Model"""

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


class ListFAQsResponse(BaseModel):
    """List FAQs Response Model"""

    faqs: list[FAQ]
    total: int
