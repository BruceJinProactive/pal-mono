"""Tests for services/eval_service/_snapshot.py."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.eval_service._snapshot import (
    _compute_config_diff,
    _compute_prompt_diff,
    compute_snapshot_diff,
)

SNAPSHOT_MODULE = "services.eval_service._snapshot"


@pytest.fixture
def snapshot_kwargs() -> dict:
    return {
        "fingerprint": "aabbccddeeff001122334455",
        "agent_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "config_dict": {"persona": {"name": "TestBot"}},
        "prompt_hash": "1122334455aabbcc",
        "prompt_text": "You are a helpful restaurant assistant.",
    }


class TestUpsertAgentConfigSnapshot:
    @pytest.mark.asyncio
    async def test_creates_snapshot_on_new_fingerprint(
        self, snapshot_kwargs: dict
    ) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_or_create.return_value = (MagicMock(), True)

        with (
            patch(f"{SNAPSHOT_MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(
                f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
                return_value=mock_repo,
            ),
            patch(f"{SNAPSHOT_MODULE}.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from services.eval_service._snapshot import upsert_agent_config_snapshot

            await upsert_agent_config_snapshot(**snapshot_kwargs)

        mock_repo.get_or_create.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        # Should log "Created"
        assert any("Created" in str(c) for c in mock_logger.info.call_args_list)

    @pytest.mark.asyncio
    async def test_updates_last_seen_on_existing_fingerprint(
        self, snapshot_kwargs: dict
    ) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_or_create.return_value = (MagicMock(), False)

        with (
            patch(f"{SNAPSHOT_MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(
                f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
                return_value=mock_repo,
            ),
            patch(f"{SNAPSHOT_MODULE}.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from services.eval_service._snapshot import upsert_agent_config_snapshot

            await upsert_agent_config_snapshot(**snapshot_kwargs)

        # Should log "Updated last_seen_at"
        assert any(
            "Updated last_seen_at" in str(c) for c in mock_logger.info.call_args_list
        )

    @pytest.mark.asyncio
    async def test_swallows_db_errors(self, snapshot_kwargs: dict) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_or_create.side_effect = RuntimeError("db connection failed")

        with (
            patch(f"{SNAPSHOT_MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(
                f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
                return_value=mock_repo,
            ),
            patch(f"{SNAPSHOT_MODULE}.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from services.eval_service._snapshot import upsert_agent_config_snapshot

            # Must NOT raise
            await upsert_agent_config_snapshot(**snapshot_kwargs)

        mock_logger.exception.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_unexpected_errors(self, snapshot_kwargs: dict) -> None:
        with (
            patch(f"{SNAPSHOT_MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(f"{SNAPSHOT_MODULE}.logger") as mock_logger,
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(
                side_effect=TypeError("unexpected")
            )
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            from services.eval_service._snapshot import upsert_agent_config_snapshot

            # Must NOT raise
            await upsert_agent_config_snapshot(**snapshot_kwargs)

        mock_logger.exception.assert_called_once()


class TestComputePromptDiff:
    def test_identical_text_returns_empty(self) -> None:
        assert _compute_prompt_diff("hello", "hello") == []

    def test_different_text_returns_replace_block(self) -> None:
        result = _compute_prompt_diff("old prompt", "new prompt")
        assert len(result) == 1
        assert result[0]["type"] == "replace"
        assert result[0]["removed"] == ["old prompt"]
        assert result[0]["added"] == ["new prompt"]

    def test_multiline_diff_groups_changes(self) -> None:
        from_text = "line1\nline2\nline3"
        to_text = "line1\nchanged\nline3"
        result = _compute_prompt_diff(from_text, to_text)
        assert len(result) == 1
        assert result[0]["type"] == "replace"
        assert result[0]["removed"] == ["line2"]
        assert result[0]["added"] == ["changed"]

    def test_deleted_lines_produce_delete_block(self) -> None:
        from_text = "line1\nline2\nline3"
        to_text = "line1\nline3"
        result = _compute_prompt_diff(from_text, to_text)
        assert len(result) == 1
        assert result[0]["type"] == "delete"
        assert result[0]["removed"] == ["line2"]
        assert result[0]["added"] == []

    def test_inserted_lines_produce_insert_block(self) -> None:
        from_text = "line1\nline3"
        to_text = "line1\nline2\nline3"
        result = _compute_prompt_diff(from_text, to_text)
        assert len(result) == 1
        assert result[0]["type"] == "insert"
        assert result[0]["removed"] == []
        assert result[0]["added"] == ["line2"]


class TestComputeConfigDiff:
    def test_identical_config_returns_empty(self) -> None:
        config: dict[str, Any] = {"model": "gpt-4", "temperature": 0.7}
        assert _compute_config_diff(config, config) == []

    def test_changed_value(self) -> None:
        old: dict[str, Any] = {"model": "gpt-4"}
        new: dict[str, Any] = {"model": "gpt-4o"}
        result = _compute_config_diff(old, new)
        assert len(result) == 1
        assert result[0] == {"path": "model", "from": "gpt-4", "to": "gpt-4o"}

    def test_added_key(self) -> None:
        old: dict[str, Any] = {"model": "gpt-4"}
        new: dict[str, Any] = {"model": "gpt-4", "temperature": 0.7}
        result = _compute_config_diff(old, new)
        assert len(result) == 1
        assert result[0] == {"path": "temperature", "from": None, "to": 0.7}

    def test_removed_key(self) -> None:
        old: dict[str, Any] = {"model": "gpt-4", "temperature": 0.7}
        new: dict[str, Any] = {"model": "gpt-4"}
        result = _compute_config_diff(old, new)
        assert len(result) == 1
        assert result[0] == {"path": "temperature", "from": 0.7, "to": None}

    def test_nested_change_uses_dot_path(self) -> None:
        old: dict[str, Any] = {"persona": {"name": "Bot", "tone": "friendly"}}
        new: dict[str, Any] = {"persona": {"name": "Agent", "tone": "friendly"}}
        result = _compute_config_diff(old, new)
        assert len(result) == 1
        assert result[0] == {"path": "persona.name", "from": "Bot", "to": "Agent"}

    def test_multiple_changes_sorted_by_path(self) -> None:
        old: dict[str, Any] = {"b": 1, "a": 2}
        new: dict[str, Any] = {"b": 10, "a": 20}
        result = _compute_config_diff(old, new)
        assert len(result) == 2
        assert result[0]["path"] == "a"
        assert result[1]["path"] == "b"


class TestComputeSnapshotDiff:
    @pytest.mark.asyncio
    async def test_raises_when_from_fingerprint_not_found(self) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_by_fingerprint.return_value = None

        with patch(
            f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
            return_value=mock_repo,
        ):
            with pytest.raises(ValueError, match="from_fingerprint"):
                await compute_snapshot_diff("from_fingerprint", "bbb", mock_session)

    @pytest.mark.asyncio
    async def test_raises_when_to_fingerprint_not_found(self) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        from_snap = MagicMock()
        mock_repo.get_by_fingerprint.side_effect = [from_snap, None]

        with patch(
            f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
            return_value=mock_repo,
        ):
            with pytest.raises(ValueError, match="to_fingerprint"):
                await compute_snapshot_diff("aaa", "to_fingerprint", mock_session)

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()

        from_snap = MagicMock()
        from_snap.system_prompt_hash = "hash_a"
        from_snap.system_prompt_text = "old prompt"
        from_snap.config_snapshot = {"model": "gpt-4"}

        to_snap = MagicMock()
        to_snap.system_prompt_hash = "hash_b"
        to_snap.system_prompt_text = "new prompt"
        to_snap.config_snapshot = {"model": "gpt-4o"}

        mock_repo.get_by_fingerprint.side_effect = [from_snap, to_snap]

        with patch(
            f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
            return_value=mock_repo,
        ):
            result = await compute_snapshot_diff("fp_a", "fp_b", mock_session)

        assert result["from_fingerprint"] == "fp_a"
        assert result["to_fingerprint"] == "fp_b"
        assert result["prompt_changed"] is True
        assert result["config_changed"] is True
        assert len(result["prompt_diff"]) == 1
        assert result["prompt_diff"][0]["type"] == "replace"
        assert result["prompt_diff"][0]["removed"] == ["old prompt"]
        assert result["prompt_diff"][0]["added"] == ["new prompt"]
        assert result["config_diff"] == [
            {"path": "model", "from": "gpt-4", "to": "gpt-4o"}
        ]

    @pytest.mark.asyncio
    async def test_identical_snapshots_returns_no_changes(self) -> None:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()

        snap = MagicMock()
        snap.system_prompt_hash = "same_hash"
        snap.system_prompt_text = "same prompt"
        snap.config_snapshot = {"model": "gpt-4"}

        mock_repo.get_by_fingerprint.side_effect = [snap, snap]

        with patch(
            f"{SNAPSHOT_MODULE}.AgentConfigSnapshotRepositoryAsync",
            return_value=mock_repo,
        ):
            result = await compute_snapshot_diff("fp_a", "fp_a", mock_session)

        assert result["prompt_changed"] is False
        assert result["config_changed"] is False
        assert result["prompt_diff"] == []
        assert result["config_diff"] == []
