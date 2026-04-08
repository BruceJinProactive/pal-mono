"""Tests for prompt traceability service — history logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._prompt_traceability import (
    get_conversation_history_with_prompts,
)


def _make_conversation(
    conv_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    agent_fingerprint: str | None = None,
    prompt_fingerprint: str | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    conv = MagicMock()
    conv.id = conv_id or uuid.uuid4()
    conv.project_id = project_id or uuid.uuid4()
    conv.agent_fingerprint = agent_fingerprint
    conv.prompt_fingerprint = prompt_fingerprint
    conv.created_at = created_at or datetime.now(timezone.utc)
    return conv


def _make_snapshot(
    fingerprint: str,
    system_prompt_hash: str,
    system_prompt_text: str,
) -> MagicMock:
    snap = MagicMock()
    snap.fingerprint = fingerprint
    snap.system_prompt_hash = system_prompt_hash
    snap.system_prompt_text = system_prompt_text
    return snap


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


class TestGetConversationHistoryWithPrompts:
    @patch(
        "services.eval_service._prompt_traceability.AgentConfigSnapshotRepositoryAsync"
    )
    @patch("services.eval_service._prompt_traceability.db")
    async def test_returns_prompt_text(
        self,
        mock_db: MagicMock,
        mock_snap_repo_cls: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        project_id = uuid.uuid4()
        conv = _make_conversation(
            project_id=project_id,
            agent_fingerprint="fp_a",
        )
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_by_project.return_value = [conv]
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        snap = _make_snapshot("fp_a", "hash_a", "You are helpful.")
        mock_snap_repo = AsyncMock()
        mock_snap_repo.get_by_fingerprint.return_value = snap
        mock_snap_repo_cls.return_value = mock_snap_repo

        result = await get_conversation_history_with_prompts(
            project_id, 10, mock_session
        )

        assert result["project_id"] == str(project_id)
        assert len(result["conversations"]) == 1
        assert result["conversations"][0]["prompt_text"] == "You are helpful."
        assert result["conversations"][0]["prompt_fingerprint"] == "hash_a"

    @patch(
        "services.eval_service._prompt_traceability.AgentConfigSnapshotRepositoryAsync"
    )
    @patch("services.eval_service._prompt_traceability.db")
    async def test_flags_prompt_changed(
        self,
        mock_db: MagicMock,
        mock_snap_repo_cls: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        project_id = uuid.uuid4()
        # Newest first (as returned by get_by_project with ORDER BY created_at DESC)
        conv_new = _make_conversation(
            project_id=project_id,
            agent_fingerprint="fp_b",
            created_at=datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
        )
        conv_old = _make_conversation(
            project_id=project_id,
            agent_fingerprint="fp_a",
            created_at=datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_by_project.return_value = [conv_new, conv_old]
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        snap_a = _make_snapshot("fp_a", "hash_a", "Original prompt.")
        snap_b = _make_snapshot("fp_b", "hash_b", "Updated prompt.")

        mock_snap_repo = AsyncMock()
        mock_snap_repo.get_by_fingerprint.side_effect = lambda fp: (
            snap_a if fp == "fp_a" else snap_b
        )
        mock_snap_repo_cls.return_value = mock_snap_repo

        result = await get_conversation_history_with_prompts(
            project_id, 10, mock_session
        )

        convos = result["conversations"]
        # Newest first in response
        assert convos[0]["prompt_changed"] is True
        assert convos[1]["prompt_changed"] is False

    @patch(
        "services.eval_service._prompt_traceability.AgentConfigSnapshotRepositoryAsync"
    )
    @patch("services.eval_service._prompt_traceability.db")
    async def test_handles_null_fingerprint(
        self,
        mock_db: MagicMock,
        mock_snap_repo_cls: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        project_id = uuid.uuid4()
        conv = _make_conversation(
            project_id=project_id,
            agent_fingerprint=None,
        )
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_by_project.return_value = [conv]
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        mock_snap_repo = AsyncMock()
        mock_snap_repo_cls.return_value = mock_snap_repo

        result = await get_conversation_history_with_prompts(
            project_id, 10, mock_session
        )

        assert len(result["conversations"]) == 1
        assert result["conversations"][0]["prompt_text"] is None
        assert result["conversations"][0]["prompt_changed"] is False

    @patch(
        "services.eval_service._prompt_traceability.AgentConfigSnapshotRepositoryAsync"
    )
    @patch("services.eval_service._prompt_traceability.db")
    async def test_same_prompt_not_flagged_as_changed(
        self,
        mock_db: MagicMock,
        mock_snap_repo_cls: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        project_id = uuid.uuid4()
        # Two conversations with the same prompt but different agent fingerprints
        # (e.g. model changed but prompt didn't)
        conv_new = _make_conversation(
            project_id=project_id,
            agent_fingerprint="fp_b",
            created_at=datetime(2026, 4, 8, 15, 0, tzinfo=timezone.utc),
        )
        conv_old = _make_conversation(
            project_id=project_id,
            agent_fingerprint="fp_a",
            created_at=datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_by_project.return_value = [conv_new, conv_old]
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        # Same prompt hash despite different agent fingerprints
        snap_a = _make_snapshot("fp_a", "same_hash", "Same prompt.")
        snap_b = _make_snapshot("fp_b", "same_hash", "Same prompt.")

        mock_snap_repo = AsyncMock()
        mock_snap_repo.get_by_fingerprint.side_effect = lambda fp: (
            snap_a if fp == "fp_a" else snap_b
        )
        mock_snap_repo_cls.return_value = mock_snap_repo

        result = await get_conversation_history_with_prompts(
            project_id, 10, mock_session
        )

        convos = result["conversations"]
        assert convos[0]["prompt_changed"] is False
        assert convos[1]["prompt_changed"] is False

    @patch(
        "services.eval_service._prompt_traceability.AgentConfigSnapshotRepositoryAsync"
    )
    @patch("services.eval_service._prompt_traceability.db")
    async def test_empty_project(
        self,
        mock_db: MagicMock,
        mock_snap_repo_cls: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        project_id = uuid.uuid4()
        mock_conv_repo = AsyncMock()
        mock_conv_repo.get_by_project.return_value = []
        mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

        mock_snap_repo = AsyncMock()
        mock_snap_repo_cls.return_value = mock_snap_repo

        result = await get_conversation_history_with_prompts(
            project_id, 10, mock_session
        )

        assert result["conversations"] == []
