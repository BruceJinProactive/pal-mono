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
def mock_context() -> UserContext:
    return UserContext(
        username=str(uuid.uuid4()),
        email="test@example.com",
        groups=[],
        display_name="Test User",
        role=UserRole.Admin,
    )


@pytest.fixture
def mock_async_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
class TestCreateProjectSubscriptionHandling:
    """Test subscription handling in create_project.

    The route delegates subscription writes to async pal-repository-backed service
    helpers so it does not need a threadpool bridge.
    """

    async def test_with_subscription_calls_async_subscription_service(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
        """Test that subscription_id triggers the async subscription helper."""
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
                "api.routes.admin._projects.subscription_service.create_project_subscription_data_async",
                new_callable=AsyncMock,
            ) as mock_create_project_subscription,
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            mock_create_project_subscription.assert_awaited_once_with(
                mock_async_session,
                mock_project,
                subscription_id,
                "test-account",
            )

    async def test_without_subscription_skips_subscription_service(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
        """Test that no subscription_id skips subscription writes."""
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
            patch(
                "api.routes.admin._projects.subscription_service.create_project_subscription_data_async",
                new_callable=AsyncMock,
            ) as mock_create_project_subscription,
            patch("api.routes.admin._projects.build_project", return_value={}),
        ):
            await create_project(create_request, mock_context, mock_async_session)

            mock_create_project_subscription.assert_not_awaited()

    async def test_subscription_value_error_raises_http_400(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
                "api.routes.admin._projects.subscription_service.create_project_subscription_data_async",
                new_callable=AsyncMock,
                side_effect=ValueError("Invalid subscription"),
            ),
        ):
            mock_voice_cls.return_value.list_by_project_id = AsyncMock(return_value=[])

            with pytest.raises(HTTPException) as exc_info:
                await create_project(create_request, mock_context, mock_async_session)

            assert exc_info.value.status_code == 400
            assert "failed to add to subscription" in exc_info.value.detail

    async def test_subscription_runtime_error_raises_http_500(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
                "api.routes.admin._projects.subscription_service.create_project_subscription_data_async",
                new_callable=AsyncMock,
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
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
            mock_async_session.refresh.assert_awaited_once_with(mock_project)

            voice_config_data = mock_voice_repo.create.call_args[0][0]
            assert isinstance(voice_config_data, VoiceConfigData)
            assert voice_config_data.project_id == project_id
            assert voice_config_data.language == "english"
            assert "test-project" in voice_config_data.first_message

    async def test_skips_voice_config_when_already_exists(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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

    The route delegates subscription cleanup to async pal-repository-backed service
    helpers so it does not need a threadpool bridge.
    """

    async def test_calls_async_subscription_cleanup_with_correct_ids(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
        """Verify subscription removal calls async helpers with correct IDs."""
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        subscription_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.account_id = account_id
        mock_project.name = "test-project"
        mock_project.account = MagicMock()

        mock_current_subscription = MagicMock()
        mock_current_subscription.external_id = subscription_id

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
                "api.routes.admin._projects.subscription_service.get_current_subscription_data_async",
                new_callable=AsyncMock,
                return_value=mock_current_subscription,
            ) as mock_get_current_subscription,
            patch(
                "api.routes.admin._projects.subscription_service.remove_project_subscription_data_async",
                new_callable=AsyncMock,
            ) as mock_remove_project_subscription,
        ):
            await delete_project(project_id, mock_context, mock_async_session)

            mock_get_current_subscription.assert_awaited_once_with(
                mock_async_session,
                mock_project.account,
            )
            mock_remove_project_subscription.assert_awaited_once_with(
                mock_async_session,
                account_id,
                project_id,
                subscription_id,
            )

    async def test_delete_nonexistent_project_returns_early(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
                "api.routes.admin._projects.subscription_service.get_current_subscription_data_async",
                new_callable=AsyncMock,
                side_effect=Exception("Database error"),
            ),
            pytest.raises(Exception),
        ):
            await delete_project(project_id, mock_context, mock_async_session)

        mock_async_session.rollback.assert_called_once()

    async def test_delete_removes_voice_configs(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
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
                "api.routes.admin._projects.subscription_service.get_current_subscription_data_async",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await delete_project(project_id, mock_context, mock_async_session)

            mock_voice_repo.delete_by_project_id.assert_called_once_with(project_id)
            mock_async_session.commit.assert_called_once()

    async def test_delete_uses_project_snapshot_after_voice_config_commit(
        self, mock_context: UserContext, mock_async_session: AsyncMock
    ) -> None:
        """Deleting voice configs may expire ORM attrs; route uses snapshots."""
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()

        class ExpiringProject:
            expired = False

            def __init__(self) -> None:
                self.account = None

            def _raise_if_expired(self) -> None:
                if self.expired:
                    raise AssertionError("project ORM attribute accessed after commit")

            @property
            def id(self) -> uuid.UUID:
                self._raise_if_expired()
                return project_id

            @property
            def account_id(self) -> uuid.UUID:
                self._raise_if_expired()
                return account_id

            @property
            def name(self) -> str:
                self._raise_if_expired()
                return "test-project"

        mock_project = ExpiringProject()

        mock_voice_repo = MagicMock()

        async def delete_voice_configs(_: uuid.UUID) -> int:
            mock_project.expired = True
            return 3

        mock_voice_repo.delete_by_project_id = AsyncMock(
            side_effect=delete_voice_configs
        )

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
        ):
            await delete_project(project_id, mock_context, mock_async_session)

            mock_voice_repo.delete_by_project_id.assert_called_once_with(project_id)
            mock_async_session.commit.assert_called_once()
