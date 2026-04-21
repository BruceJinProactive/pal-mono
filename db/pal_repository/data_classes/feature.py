from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeatureData:
    """Immutable snapshot of a feature flag.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    feature: str
    identifier_type: str
    identifier: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
