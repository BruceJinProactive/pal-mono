from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType


@dataclass(frozen=True)
class ActiveUsersRow:
    """Immutable result row from active users analytics query.

    Group fields are optional — present only when group_by is specified.
    """

    active_users: int
    conversations: int
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    date: date | None = None


@dataclass(frozen=True)
class TurnsSummaryRow:
    """Immutable result row from turns summary analytics query."""

    low_turns: int
    high_turns: int
    total_convs: int
    total_turns: int
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    date: date | None = None


@dataclass(frozen=True)
class CallsTimeSummaryRow:
    """Immutable result row from calls time summary analytics query."""

    total_calls: int
    avg_duration: float | None
    avg_turn_latency: float | None
    short_calls: int
    long_calls: int
    transfer_calls: int
    transfer_rate: float | None
    positive_calls: int
    neutral_calls: int
    negative_calls: int
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    date: date | None = None


@dataclass(frozen=True)
class CallsInfoSummaryRow:
    """Immutable result row from calls info summary analytics query.

    Purpose and language counts are stored as immutable mappings since the
    fields are dynamically generated from enum values.
    """

    purpose_counts: Mapping[str, int]
    language_counts: Mapping[str, int]
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    date: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "purpose_counts",
            MappingProxyType(dict(self.purpose_counts)),
        )
        object.__setattr__(
            self,
            "language_counts",
            MappingProxyType(dict(self.language_counts)),
        )


@dataclass(frozen=True)
class ConversionSummaryRow:
    """Immutable result row from conversion summary analytics query."""

    total_conversations: int
    conversations_with_orders: int
    paid_orders: int
    total_subtotal: Decimal
    paid_total: Decimal
    total_reservations: int
    total_waitlists: int
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    date: date | None = None
