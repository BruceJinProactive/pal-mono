from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CallInsightMetricAvailability(BaseModel):
    available: bool
    source: str | None = None
    note: str | None = None


class CallInsightSummary(BaseModel):
    total_calls: int
    avg_duration_seconds: float | None
    after_hours_calls: int | None
    spam_calls: int | None
    internal_test_calls: int
    new_callers: int
    repeat_callers: int
    transfer_requested_calls: int
    concurrent_calls: int
    transfer_answered_calls: int | None


class CallInsightRecord(BaseModel):
    call_id: str
    conversation_id: UUID
    account_id: UUID
    account_name: str
    project_id: UUID | None = None
    project_name: str | None = None
    caller_identifiers: list[str]
    started_at: datetime
    duration_seconds: float | None = None
    is_after_hours: bool | None = None
    is_spam: bool | None = None
    is_internal_test: bool
    is_new_caller: bool
    is_repeat_caller: bool
    transfer_requested: bool
    transfer_destination: str | None = None
    transfer_reason: str | None = None
    transfer_requested_at: datetime | None = None
    transferred_call_answered: bool | None = None
    has_concurrent_call: bool


class CallInsightsResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    summary: CallInsightSummary
    metric_availability: dict[str, CallInsightMetricAvailability]
    calls: list[CallInsightRecord]
