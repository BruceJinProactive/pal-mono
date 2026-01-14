import uuid
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class FeedbackReaction(str, Enum):
    """Feedback Reactions"""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackTag(str, Enum):
    """Feedback Tags"""

    NOT_FACTUALLY_CORRECT = "not_factually_correct"
    WRONG_TONE_OF_VOICE = "wrong_tone_of_voice"
    MISSING_KEY_DETAILS = "missing_key_details"
    TOO_WORDY = "too_wordy"
    TOO_CONCISE = "too_concise"
    OTHER = "other"


class UpdateFeedbackRequest(BaseModel):
    """Update Feedback Request Model"""

    author_identifier: str | None = None
    reaction: FeedbackReaction | None = None
    tags: list[FeedbackTag] | None = None
    note: str | None = None


class CreateFeedbackRequest(UpdateFeedbackRequest):
    """Create Feedback Request Model"""

    message_id: UUID


class Feedback(BaseModel):
    """Feedback Model"""

    id: str
    timestamp: str
    message_id: str
    message_content: str

    author_identifier: str | None = None
    author_name: str | None = None
    reaction: str | None = None
    tags: list[str] | None = None
    note: str | None = None


class FeedbackDetail(BaseModel):
    feedback: Feedback
    conversation_id: uuid.UUID


class ListFeedbacksResponse(BaseModel):
    feedbacks: list[FeedbackDetail]
