"""Tests for db.repositories.phone_call_repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.phone_call_repository import PhoneCallRepositoryAsync
from db.tables.types import CallEndedReason, CallLanguage, CallPurpose, UserSatisfaction


@pytest.mark.asyncio
async def test_update_phone_call_sets_transfer_reason_fields() -> None:
    session = AsyncMock()
    phone_call = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = phone_call
    session.execute.return_value = result

    repo = PhoneCallRepositoryAsync(session)

    updated = await repo.update_phone_call(
        call_id="call-123",
        ended_reason=CallEndedReason.assistant_forwarded,
        call_purpose=[CallPurpose.ordering],
        user_satisfaction=UserSatisfaction.negative,
        language=CallLanguage.english,
        transfer_reason_category="tool_failure_order",
        transfer_agent_was_at_fault=True,
    )

    assert updated is phone_call
    assert phone_call.ended_reason is CallEndedReason.assistant_forwarded
    assert phone_call.call_purpose == [CallPurpose.ordering]
    assert phone_call.user_satisfaction is UserSatisfaction.negative
    assert phone_call.language is CallLanguage.english
    assert phone_call.transfer_reason_category == "tool_failure_order"
    assert phone_call.transfer_agent_was_at_fault is True
    session.flush.assert_awaited_once()
