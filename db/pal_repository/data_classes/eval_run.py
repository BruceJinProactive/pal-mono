from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EvalRunData:
    """Immutable snapshot of an eval run.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    account_id: uuid.UUID
    driver_mode: str
    status: str
    triggered_by: str
    scenario_count: int
    passed_count: int
    failed_count: int
    created_at: datetime
    agent_fingerprint: str | None = None
    overall_score: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    updated_at: datetime | None = None
