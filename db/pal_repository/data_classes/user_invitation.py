from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class UserInvitationData:
    """Immutable snapshot of a user invitation.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    account_role: str
    invited_by: uuid.UUID
    invitation_token: str
    expires_at: datetime
    status: str
    created_at: datetime
    project_ids: tuple[uuid.UUID, ...] | None = None
    accepted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.project_ids is not None and not isinstance(self.project_ids, tuple):
            object.__setattr__(self, "project_ids", tuple(self.project_ids))
