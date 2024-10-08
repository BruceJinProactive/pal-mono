import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeedbackReaction(str, Enum):
    """Feedback Reactions"""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackTag(str, Enum):
    """ "Feedback Tags"""

    FACTUAL_ERROR = "factual_error"
    INSTRUCTION_ERROR = "instruction_error"


class Feedback(BaseModel):
    """Feedback Model"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str
    sender_email: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reaction: Optional[FeedbackReaction] = None
    tags: Optional[List[FeedbackTag]] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "sender_email": self.sender_email,
            "timestamp": self.timestamp.isoformat(),
            "reaction": self.reaction.value if self.reaction is not None else None,
            "tags": [tag.value for tag in self.tags] if self.tags is not None else None,
            "note": self.note,
        }
