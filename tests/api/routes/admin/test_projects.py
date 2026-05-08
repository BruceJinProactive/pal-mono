"""Tests for admin project routes with voice config and subscription handling."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._projects import create_project, delete_project
from api.schemas.admin.project import CreateProjectRequest
from db.pal_repository.data_classes.voice_config import VoiceConfigData
from services.auth_types import UserContext, UserRole


@pytest.fixture
def mock_context():
    return UserContext(
        username=str(uuid.uuid4()),
        email="test@example.com",
        groups=[],
        display_name="Test User",
        role=UserRole.Admin,
    )


@pytest.fixture
def mock_async_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
class TestCreateProjectSubscriptionHandling:
    """Test subscription handling in create_project.

    Note: The internal wrapper function (_add_project_to_subscription) creates
    SyncSessionLocal inside the thread and is difficult to unit test. Full coverage
    requires integration tests with a real database.
    """

    async def test_with_subscription_calls_run_in_threadpool(
        self, mock_context, mock_async_session
    ):
        """Test that subscription_id triggers run_in_threadpool with correct IDs."""
        project_id = uuid.uuid4()
        subscription_id = uuid.uuid4()

        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
            subscription_id=subscription_id,
        )

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.name = "test-project"

        mock_voice_repo = MagicMock()
        mock_voice_repo.list_by_project_id = AsyncMock(return_value=[])
        mock_voice_repo.create = AsyncMock()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                new_callable=AsyncMock,
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch(
                "api.routes.admin._projects.run_in_threadpool", new_callable=AsyncMock
            ) as mock_threadpool,
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            # Verify threadpool was called with wrapper function and IDs
            mock_threadpool.assert_called_once()
            call_args = mock_threadpool.call_args[0]
            assert callable(call_args[0])  # Wrapper function
            assert call_args[1] == project_id  # project_id
            assert call_args[2] == subscription_id  # subscription_id

    async def test_without_subscription_skips_threadpool(
        self, mock_context, mock_async_session
    ):
        """Test that no subscription_id skips run_in_threadpool."""
        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
            subscription_id=None,
        )

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()

        mock_voice_repo = MagicMock()
        mock_voice_repo.list_by_project_id = AsyncMock(return_value=[])
        mock_voice_repo.create = AsyncMock()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch("api.routes.admin._projects.run_in_threadpool") as mock_threadpool,
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            mock_threadpool.assert_not_called()

    async def test_subscription_value_error_raises_http_400(
        self, mock_context, mock_async_session
    ):
        """Test ValueError in subscription raises HTTP 400."""
        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
        )

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew"
            ) as mock_voice_cls,
            patch(
                "api.routes.admin._projects.run_in_threadpool",
                side_effect=ValueError("Invalid subscription"),
            ),
        ):
            mock_voice_cls.return_value.list_by_project_id = AsyncMock(return_value=[])

            with pytest.raises(HTTPException) as exc_info:
                await create_project(create_request, mock_context, mock_async_session)

            assert exc_info.value.status_code == 400
            assert "failed to add to subscription" in exc_info.value.detail

    async def test_subscription_runtime_error_raises_http_500(
        self, mock_context, mock_async_session
    ):
        """Test RuntimeError in subscription raises HTTP 500."""
        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
        )

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew"
            ) as mock_voice_cls,
            patch(
                "api.routes.admin._projects.run_in_threadpool",
                side_effect=RuntimeError("Database error"),
            ),
        ):
            mock_voice_cls.return_value.list_by_project_id = AsyncMock(return_value=[])

            with pytest.raises(HTTPException) as exc_info:
                await create_project(create_request, mock_context, mock_async_session)

            assert exc_info.value.status_code == 500
            assert "internal error" in exc_info.value.detail.lower()


@pytest.mark.asyncio
class TestCreateProjectVoiceConfig:
    """Test voice config creation in create_project."""

    async def test_creates_default_voice_config_when_none_exist(
        self, mock_context, mock_async_session
    ):
        """Test default voice config is created when project has none."""
        project_id = uuid.uuid4()

        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
        )

        mock_project = MagicMock()
        mock_project.id = project_id

        mock_voice_repo = MagicMock()
        mock_voice_repo.list_by_project_id = AsyncMock(return_value=[])
        mock_voice_repo.create = AsyncMock()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            mock_voice_repo.list_by_project_id.assert_called_once_with(project_id)
            mock_voice_repo.create.assert_called_once()

            voice_config_data = mock_voice_repo.create.call_args[0][0]
            assert isinstance(voice_config_data, VoiceConfigData)
            assert voice_config_data.project_id == project_id
            assert voice_config_data.language == "english"
            assert "test-project" in voice_config_data.first_message

    async def test_skips_voice_config_when_already_exists(
        self, mock_context, mock_async_session
    ):
        """Test voice config creation is skipped when configs exist."""
        create_request = CreateProjectRequest(
            account_name="test-account",
            name="test-project",
            display_name="Test Project",
            agent_id=uuid.uuid4(),
        )

        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()

        mock_voice_repo = MagicMock()
        # Return existing config
        mock_voice_repo.list_by_project_id = AsyncMock(return_value=[MagicMock()])
        mock_voice_repo.create = AsyncMock()

        with (
            patch(
                "api.routes.admin._projects.project_service.create_project_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            mock_voice_repo.list_by_project_id.assert_called_once()
            mock_voice_repo.create.assert_not_called()


@pytest.mark.asyncio
class TestDeleteProjectSubscriptionHandling:
    """Test subscription handling in delete_project.

    Note: The internal wrapper function (_remove_project_from_subscription) creates
    SyncSessionLocal inside the thread and is difficult to unit test. Full coverage
    requires integration tests with a real database.
    """

    async def test_calls_run_in_threadpool_with_correct_ids(
        self, mock_context, mock_async_session
    ):
        """Verify subscription removal calls threadpool with correct IDs."""
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.account_id = account_id
        mock_project.name = "test-project"

        mock_voice_repo = MagicMock()
        mock_voice_repo.delete_by_project_id = AsyncMock(return_value=2)

        with (
            patch(
                "api.routes.admin._projects.project_service.get_project_by_id_async",
                return_value=mock_project,
            ),
            patch("api.routes.admin._projects.project_service.delete_project_async"),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch(
                "api.routes.admin._projects.run_in_threadpool", new_callable=AsyncMock
            ) as mock_threadpool,
        ):
            await delete_project(project_id, mock_context, mock_async_session)

            # Verify threadpool was called with wrapper and IDs
            mock_threadpool.assert_called_once()
            call_args = mock_threadpool.call_args[0]
            assert callable(call_args[0])  # Wrapper function
            assert call_args[1] == account_id  # account_id
            assert call_args[2] == project_id  # project_id

    async def test_delete_nonexistent_project_returns_early(
        self, mock_context, mock_async_session
    ):
        """Test deleting non-existent project returns None."""
        project_id = uuid.uuid4()

        with patch(
            "api.routes.admin._projects.project_service.get_project_by_id_async",
            return_value=None,
        ):
            result = await delete_project(project_id, mock_context, mock_async_session)

            assert result is None
            mock_async_session.commit.assert_not_called()

    async def test_delete_project_error_triggers_rollback(
        self, mock_context, mock_async_session
    ):
        """Test error during deletion triggers rollback."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.account_id = uuid.uuid4()
        mock_project.name = "test-project"

        with (
            patch(
                "api.routes.admin._projects.project_service.get_project_by_id_async",
                return_value=mock_project,
            ),
            patch(
                "api.routes.admin._projects.run_in_threadpool",
                side_effect=Exception("Database error"),
            ),
            pytest.raises(Exception),
        ):
            await delete_project(project_id, mock_context, mock_async_session)

        mock_async_session.rollback.assert_called_once()

    async def test_delete_removes_voice_configs(self, mock_context, mock_async_session):
        """Test voice configs are deleted."""
        project_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.account_id = uuid.uuid4()
        mock_project.name = "test-project"

        mock_voice_repo = MagicMock()
        mock_voice_repo.delete_by_project_id = AsyncMock(return_value=3)

        with (
            patch(
                "api.routes.admin._projects.project_service.get_project_by_id_async",
                return_value=mock_project,
            ),
            patch("api.routes.admin._projects.project_service.delete_project_async"),
            patch(
                "api.routes.admin._projects.VoiceConfigRepositoryNew",
                return_value=mock_voice_repo,
            ),
            patch(
                "api.routes.admin._projects.run_in_threadpool", new_callable=AsyncMock
            ),
        ):
            await delete_project(project_id, mock_context, mock_async_session)

            mock_voice_repo.delete_by_project_id.assert_called_once_with(project_id)
            mock_async_session.commit.assert_called_once()
