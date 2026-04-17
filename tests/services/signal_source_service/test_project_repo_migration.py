"""Tests verifying ProjectRepository (pal_repository) is used in signal_source_service."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.pal_repository.data_classes.project import ProjectData

MODULE = "services.signal_source_service._implementation"


def _make_project_data(**overrides: object) -> ProjectData:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "test-project",
        "account_id": uuid.uuid4(),
        "agent_id": uuid.uuid4(),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return ProjectData(**defaults)  # type: ignore[arg-type]


def _make_source_mock(**overrides: object) -> MagicMock:
    source = MagicMock()
    source.id = overrides.get("id", uuid.uuid4())
    source.account_id = overrides.get("account_id", uuid.uuid4())
    source.project_id = overrides.get("project_id", uuid.uuid4())
    return source


class TestCreateSourceUsesProjectRepository:
    """create_source uses ProjectRepository.get_by_id."""

    @pytest.mark.asyncio
    async def test_project_not_found_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync"),
            patch(f"{MODULE}.SignalFeedRepositoryAsync"),
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.signal_source_service._implementation import create_source

            request = MagicMock()
            request.config.camera_id = "cam-1"
            request.config.model_dump.return_value = {}
            request.name = "Test Source"
            request.description = "desc"

            with pytest.raises(ValueError, match="not found"):
                await create_source(session, project_id, request)

            repo.get_by_id.assert_awaited_once_with(project_id)

    @pytest.mark.asyncio
    async def test_create_source_uses_account_id(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        project = _make_project_data(id=project_id, account_id=account_id)

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync") as mock_source_cls,
            patch(f"{MODULE}.SignalFeedRepositoryAsync") as mock_feed_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = project
            mock_repo_cls.return_value = repo

            source_repo = AsyncMock()
            source_repo.camera_id_exists.return_value = False
            created = MagicMock()
            created.id = uuid.uuid4()
            source_repo.create.return_value = created
            mock_source_cls.return_value = source_repo

            feed_repo = AsyncMock()
            mock_feed_cls.return_value = feed_repo

            from services.signal_source_service._implementation import create_source

            request = MagicMock()
            request.config.camera_id = "cam-1"
            request.config.model_dump.return_value = {"camera_id": "cam-1"}
            request.name = "Test Source"
            request.description = "desc"

            result = await create_source(session, project_id, request)

            assert result == created
            # Verify SignalSource was created with correct account_id
            source_repo.create.assert_awaited_once()
            created_arg = source_repo.create.call_args[0][0]
            assert created_arg.account_id == account_id


class TestGetSourcesUsesProjectRepository:
    """get_sources uses ProjectRepository.get_by_id."""

    @pytest.mark.asyncio
    async def test_project_not_found_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync"),
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.signal_source_service._implementation import get_sources

            with pytest.raises(ValueError, match="not found"):
                await get_sources(session, project_id)

    @pytest.mark.asyncio
    async def test_returns_sources_for_project(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        project = _make_project_data(id=project_id, account_id=account_id)

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync") as mock_source_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = project
            mock_repo_cls.return_value = repo

            source_repo = AsyncMock()
            expected = [MagicMock()]
            source_repo.get_by_account.return_value = expected
            mock_source_cls.return_value = source_repo

            from services.signal_source_service._implementation import get_sources

            result = await get_sources(session, project_id)

            assert result == expected
            source_repo.get_by_account.assert_awaited_once_with(account_id, project_id)


class TestGetSourceUsesProjectRepository:
    """get_source uses ProjectRepository.get_by_id."""

    @pytest.mark.asyncio
    async def test_project_not_found_returns_none(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        source_id = uuid.uuid4()

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync") as mock_source_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo
            source_repo = AsyncMock()
            mock_source_cls.return_value = source_repo

            from services.signal_source_service._implementation import get_source

            result = await get_source(session, project_id, source_id)

            assert result is None
            repo.get_by_id.assert_awaited_once_with(project_id)
            source_repo.get_by_id.assert_not_awaited()


class TestUpdateSourceUsesProjectRepository:
    """update_source uses ProjectRepository.get_by_id."""

    @pytest.mark.asyncio
    async def test_project_not_found_returns_none(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        source_id = uuid.uuid4()

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync") as mock_source_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo
            source_repo = AsyncMock()
            mock_source_cls.return_value = source_repo

            from services.signal_source_service._implementation import update_source

            request = MagicMock()
            result = await update_source(session, project_id, source_id, request)

            assert result is None
            repo.get_by_id.assert_awaited_once_with(project_id)
            source_repo.get_by_id.assert_not_awaited()


class TestDeleteSourceUsesProjectRepository:
    """delete_source uses ProjectRepository.get_by_id."""

    @pytest.mark.asyncio
    async def test_project_not_found_returns_false(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        source_id = uuid.uuid4()

        with (
            patch(f"{MODULE}.ProjectRepository") as mock_repo_cls,
            patch(f"{MODULE}.SignalSourceRepositoryAsync") as mock_source_cls,
            patch(f"{MODULE}.SignalFeedRepositoryAsync"),
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo
            source_repo = AsyncMock()
            mock_source_cls.return_value = source_repo

            from services.signal_source_service._implementation import delete_source

            result = await delete_source(session, project_id, source_id)

            assert result is False
            repo.get_by_id.assert_awaited_once_with(project_id)
            source_repo.get_by_id.assert_not_awaited()
