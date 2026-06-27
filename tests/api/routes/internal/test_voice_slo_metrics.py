"""Tests for voice close SLO metric instrumentation."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.internal._voice import _background_tasks, end_voice_call


def _make_request() -> MagicMock:
    request = MagicMock()
    request.call_id = "call-123"
    request.caller_number = "+15551234567"
    request.dialed_number = "+15559876543"
    request.duration_seconds = 30.0
    request.close_reason = "customer-ended-call"
    request.conversation = []
    request.audio_recording_s3_uri = None
    request.metrics = None
    request.is_eval = False
    return request


def _make_conversation() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        channel=SimpleNamespace(value="voice"),
        is_test=False,
        customer_converted=None,
        agent_fingerprint=None,
        prompt_fingerprint=None,
        transfer_purpose=None,
        status=SimpleNamespace(value="ACTIVE"),
    )


def _make_analytics() -> dict[str, Any]:
    return {
        "ended_reason": SimpleNamespace(value="customer_ended"),
        "call_purpose": [SimpleNamespace(value="general_inquiry")],
        "user_satisfaction": SimpleNamespace(value="neutral"),
        "language": SimpleNamespace(value="english"),
        "transfer_reason_category": None,
        "transfer_agent_was_at_fault": None,
        "call_quality_label": SimpleNamespace(value="unknown_unclear"),
        "call_quality_reason_codes": [],
    }


async def _drain_voice_tasks() -> None:
    pending = [task for task in _background_tasks if not task.done()]
    if pending:
        await asyncio.wait(pending, timeout=2)
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_end_voice_call_records_success_metric() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    conversation = _make_conversation()
    phone_call = SimpleNamespace(id=uuid.uuid4())

    with (
        patch("api.routes.internal._voice.db") as mock_db,
        patch(
            "api.routes.internal._voice._get_default_analytics",
            return_value=_make_analytics(),
        ),
        patch("api.routes.internal._voice._persist_conversation_messages"),
        patch(
            "api.routes.internal._voice._should_track_call_usage",
            return_value=(False, "test_call"),
        ),
        patch(
            "api.routes.internal._voice._publish_livekit_evaluation_event",
            new_callable=AsyncMock,
        ),
        patch(
            "api.routes.internal._voice._record_voice_call_close_outcome"
        ) as mock_record,
        patch(
            "db.repositories.phone_call_repository.PhoneCallRepositoryAsync"
        ) as mock_phone_repo_cls,
    ):
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_conversation_by_call_id = AsyncMock(
            return_value=conversation
        )
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        mock_phone_repo = AsyncMock()
        mock_phone_repo.update_phone_call = AsyncMock(return_value=phone_call)
        mock_phone_repo_cls.return_value = mock_phone_repo

        result = await end_voice_call(_make_request(), session)

    await _drain_voice_tasks()

    assert result["status"] == "success"
    mock_record.assert_called_once()
    assert mock_record.call_args.args[:2] == ("success", "completed")


@pytest.mark.asyncio
async def test_end_voice_call_records_phone_call_missing_metric() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    conversation = _make_conversation()

    with (
        patch("api.routes.internal._voice.db") as mock_db,
        patch(
            "api.routes.internal._voice._get_default_analytics",
            return_value=_make_analytics(),
        ),
        patch("api.routes.internal._voice._persist_conversation_messages"),
        patch(
            "api.routes.internal._voice._should_track_call_usage",
            return_value=(False, "test_call"),
        ),
        patch(
            "api.routes.internal._voice._publish_livekit_evaluation_event",
            new_callable=AsyncMock,
        ),
        patch(
            "api.routes.internal._voice._record_voice_call_close_outcome"
        ) as mock_record,
        patch(
            "db.repositories.phone_call_repository.PhoneCallRepositoryAsync"
        ) as mock_phone_repo_cls,
    ):
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_conversation_by_call_id = AsyncMock(
            return_value=conversation
        )
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        mock_phone_repo = AsyncMock()
        mock_phone_repo.update_phone_call = AsyncMock(return_value=None)
        mock_phone_repo_cls.return_value = mock_phone_repo

        result = await end_voice_call(_make_request(), session)

    await _drain_voice_tasks()

    assert result["status"] == "success"
    mock_record.assert_called_once()
    assert mock_record.call_args.args[:2] == ("failure", "phone_call_missing")


@pytest.mark.asyncio
async def test_end_voice_call_records_conversation_not_found_metric() -> None:
    session = AsyncMock()

    with (
        patch("api.routes.internal._voice.db") as mock_db,
        patch(
            "api.routes.internal._voice._record_voice_call_close_outcome"
        ) as mock_record,
    ):
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_conversation_by_call_id = AsyncMock(return_value=None)
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        result = await end_voice_call(_make_request(), session)

    assert result["status"] == "error"
    mock_record.assert_called_once()
    assert mock_record.call_args.args[:2] == ("failure", "conversation_not_found")


@pytest.mark.asyncio
async def test_end_voice_call_records_db_close_failure_metric() -> None:
    session = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    conversation = _make_conversation()

    with (
        patch("api.routes.internal._voice.db") as mock_db,
        patch(
            "api.routes.internal._voice._get_default_analytics",
            return_value=_make_analytics(),
        ),
        patch("api.routes.internal._voice._persist_conversation_messages"),
        patch(
            "api.routes.internal._voice._record_voice_call_close_outcome"
        ) as mock_record,
        patch(
            "db.repositories.phone_call_repository.PhoneCallRepositoryAsync"
        ) as mock_phone_repo_cls,
    ):
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_conversation_by_call_id = AsyncMock(
            return_value=conversation
        )
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        mock_phone_repo = AsyncMock()
        mock_phone_repo.update_phone_call = AsyncMock(
            side_effect=RuntimeError("db unavailable")
        )
        mock_phone_repo_cls.return_value = mock_phone_repo

        result = await end_voice_call(_make_request(), session)

    assert result["status"] == "error"
    session.rollback.assert_awaited_once()
    mock_record.assert_called_once()
    assert mock_record.call_args.args[:2] == ("failure", "db_close_failed")
