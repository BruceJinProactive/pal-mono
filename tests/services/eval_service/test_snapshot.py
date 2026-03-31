"""Tests for services/eval_service/_snapshot.py."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
