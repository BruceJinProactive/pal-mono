from typing import Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    error_code: str
    error_message: str
    details: Optional[dict] = None
