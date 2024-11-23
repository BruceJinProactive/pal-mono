from pydantic import BaseModel

from api.schemas.admin.feedback import Feedback


class GetMessageResponse(BaseModel):
    """Get Message Response Model"""

    id: str
    timestamp: str
    conversation_id: str

    body: dict
    feedback: list[Feedback]
