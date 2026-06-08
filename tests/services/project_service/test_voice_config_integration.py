"""Unit tests for voice config integration in project service.

Tests that the new VoiceConfigRepository is called correctly when creating/deleting projects.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.pal_repository.data_classes.voice_config import VoiceConfigData
from services.auth_types import UserContext, UserRole
from services.project_service import create_project_async, delete_project_async
from services.project_service.schema import ProjectParams


@pytest.mark.asyncio
class TestVoiceConfigIntegration:
    async def test_create_project_async_creates_voice_config(self) -> None:
        """Creating a project calls VoiceConfigRepository.create with correct data."""
        # Mock dependencies
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        params = ProjectParams(
            agent_id=uuid.uuid4(),
            display_name="Test Project",
            channel_identifiers=[],
        )

        # Mock account and agent
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"

        mock_agent = MagicMock()
        mock_agent.id = params.agent_id
        mock_agent.account_id = mock_account.id

        # Mock project
        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "test-project"
        mock_project.display_name = "Test Project"

        # Create a real mock VoiceConfigRepository instance that will be returned
        mock_voice_repo_instance = MagicMock()
        mock_voice_repo_instance.create = AsyncMock()

        with (
            patch(
                "services.project_service._implementation.account_service.get_account_async",
                return_value=mock_account,
            ),
            patch(
                "services.project_service._implementation.agent_service.get_agent_async",
                return_value=mock_agent,
            ),
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ) as mock_voice_repo_cls,
            patch("asyncio.get_event_loop"),
        ):
            # Setup mock repository instances
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project_by_name = AsyncMock(return_value=None)
            mock_project_repo.create_project = AsyncMock(return_value=mock_project)

            # Act
            result = await create_project_async(
                async_session=mock_session,
                context=context,
                account_name="test-account",
                project_name="test-project",
                params=params,
            )

            # Assert: Project was created
            assert result == mock_project
            mock_project_repo.get_project_by_name.assert_awaited_once_with(
                "test-project"
            )
            mock_project_repo.create_project.assert_called_once()

            # Assert: Voice config repository was initialized (line 748 coverage)
            mock_voice_repo_cls.assert_called_once_with(mock_session)

            # Assert: Voice config was created with correct data (lines 751, 761 coverage)
            mock_voice_repo_instance.create.assert_called_once()
            call_args = mock_voice_repo_instance.create.call_args
            voice_config_data = call_args[0][0]

            assert isinstance(voice_config_data, VoiceConfigData)
            assert voice_config_data.project_id == mock_project.id
            assert voice_config_data.language == "english"
            assert voice_config_data.voice_id == "da69d796-4603-4419-8a95-293bfc5679eb"
            assert "test-project" in voice_config_data.first_message
            assert voice_config_data.transfer_message == ""
            assert voice_config_data.speech_rate == "normal"
            assert voice_config_data.voice_model == "sonic-2"
            mock_session.refresh.assert_awaited_once_with(mock_project)

    async def test_create_project_async_refreshes_after_voice_config_commit(
        self,
    ) -> None:
        """Voice config creation may commit; returned project is refreshed."""
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        params = ProjectParams(
            agent_id=uuid.uuid4(),
            display_name="Test Project",
            channel_identifiers=[],
        )

        account_id = uuid.uuid4()

        class ExpiringAccount:
            expired = False

            @property
            def id(self) -> uuid.UUID:
                if self.expired:
                    raise AssertionError("account ORM attribute accessed after commit")
                return account_id

        mock_account = ExpiringAccount()

        mock_agent = MagicMock()
        mock_agent.id = params.agent_id
        mock_agent.account_id = account_id

        project_id = uuid.uuid4()

        class ExpiringProject:
            expired = False

            def _raise_if_expired(self) -> None:
                if self.expired:
                    raise AssertionError("project ORM attribute accessed after commit")

            def __getattribute__(self, name: str) -> object:
                guarded_names = {
                    "id",
                    "name",
                    "display_name",
                    "raw_config",
                    "config",
                    "channel_identifiers",
                    "store_hours",
                    "address",
                    "product_info",
                    "service_instruction",
                    "order_integration_id",
                    "timezone",
                    "transfer_message",
                    "reservation_link",
                    "ordering_link",
                    "call_forwarding_setup_completed",
                    "created_at",
                    "updated_at",
                    "account_id",
                    "agent_id",
                }
                if name in guarded_names:
                    self._raise_if_expired()
                return object.__getattribute__(self, name)

            def __init__(self) -> None:
                self.id = project_id
                self.name = "test-project"
                self.display_name = "Test Project"
                self.raw_config = {}
                self.channel_identifiers = []
                self.store_hours = None
                self.address = None
                self.product_info = None
                self.service_instruction = None
                self.order_integration_id = None
                self.timezone = "America/Toronto"
                self.transfer_message = None
                self.reservation_link = None
                self.ordering_link = None
                self.call_forwarding_setup_completed = False
                self.created_at = None
                self.updated_at = None
                self.account_id = account_id
                self.agent_id = params.agent_id

        mock_project = ExpiringProject()

        mock_voice_repo_instance = MagicMock()

        async def create_voice_config(_: VoiceConfigData) -> None:
            mock_project.expired = True
            mock_account.expired = True

        mock_voice_repo_instance.create = AsyncMock(side_effect=create_voice_config)

        with (
            patch(
                "services.project_service._implementation.account_service.get_account_async",
                return_value=mock_account,
            ),
            patch(
                "services.project_service._implementation.agent_service.get_agent_async",
                return_value=mock_agent,
            ),
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ),
            patch("asyncio.get_event_loop"),
        ):
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project_by_name = AsyncMock(return_value=None)
            mock_project_repo.create_project = AsyncMock(return_value=mock_project)

            await create_project_async(
                async_session=mock_session,
                context=context,
                account_name="test-account",
                project_name="test-project",
                params=params,
            )

            mock_session.refresh.assert_awaited_once_with(mock_project)

    async def test_create_project_async_uses_copy_name_when_name_exists(
        self,
    ) -> None:
        """Duplicating a project with the same name gets a unique project name."""
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        agent_id = uuid.uuid4()
        account_id = uuid.uuid4()
        params = ProjectParams(
            agent_id=agent_id,
            display_name="Test Project",
            channel_identifiers=[],
        )

        mock_account = MagicMock()
        mock_account.id = account_id
        mock_agent = MagicMock()
        mock_agent.id = agent_id
        mock_agent.account_id = account_id

        existing_project = MagicMock()
        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "test-project-copy"
        mock_project.display_name = "Test Project"

        mock_voice_repo_instance = MagicMock()
        mock_voice_repo_instance.create = AsyncMock()

        with (
            patch(
                "services.project_service._implementation.account_service.get_account_async",
                return_value=mock_account,
            ),
            patch(
                "services.project_service._implementation.agent_service.get_agent_async",
                return_value=mock_agent,
            ),
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ),
            patch("asyncio.get_event_loop"),
        ):
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project_by_name = AsyncMock(
                side_effect=[existing_project, None]
            )
            mock_project_repo.create_project = AsyncMock(return_value=mock_project)

            result = await create_project_async(
                async_session=mock_session,
                context=context,
                account_name="test-account",
                project_name="test-project",
                params=params,
            )

            assert result == mock_project
            assert params.name == "test-project-copy"
            assert params.channel_identifiers == ["api:test-project-copy"]
            assert mock_project_repo.get_project_by_name.await_args_list[0].args == (
                "test-project",
            )
            assert mock_project_repo.get_project_by_name.await_args_list[1].args == (
                "test-project-copy",
            )
            mock_project_repo.create_project.assert_awaited_once()
            create_args = mock_project_repo.create_project.await_args
            assert create_args is not None
            assert create_args.args[:2] == (account_id, "test-project-copy")
            assert create_args.kwargs["name"] == "test-project-copy"

    async def test_create_project_async_retries_when_copy_name_races(
        self,
    ) -> None:
        """A concurrent copy using the same name advances to the next suffix."""
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        agent_id = uuid.uuid4()
        account_id = uuid.uuid4()
        params = ProjectParams(
            agent_id=agent_id,
            display_name="Test Project",
            channel_identifiers=["voice:+15551234567"],
        )

        mock_account = MagicMock()
        mock_account.id = account_id
        mock_agent = MagicMock()
        mock_agent.id = agent_id
        mock_agent.account_id = account_id

        existing_project = MagicMock()
        mock_project = MagicMock()
        mock_project.id = uuid.uuid4()
        mock_project.name = "test-project-copy-2"
        mock_project.display_name = "Test Project"

        mock_voice_repo_instance = MagicMock()
        mock_voice_repo_instance.create = AsyncMock()

        with (
            patch(
                "services.project_service._implementation.account_service.get_account_async",
                return_value=mock_account,
            ),
            patch(
                "services.project_service._implementation.agent_service.get_agent_async",
                return_value=mock_agent,
            ),
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ),
            patch("asyncio.get_event_loop"),
        ):
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project_by_name = AsyncMock(
                side_effect=[
                    existing_project,
                    None,
                    existing_project,
                    existing_project,
                    None,
                ]
            )
            mock_project_repo.create_project = AsyncMock(
                side_effect=[
                    ValueError(
                        'Error creating project: duplicate key value violates unique constraint "projects_name_key"'
                    ),
                    mock_project,
                ]
            )

            result = await create_project_async(
                async_session=mock_session,
                context=context,
                account_name="test-account",
                project_name="test-project",
                params=params,
            )

            assert result == mock_project
            assert params.name == "test-project-copy-2"
            assert params.channel_identifiers == [
                "voice:+15551234567",
                "api:test-project-copy-2",
            ]
            create_awaits = mock_project_repo.create_project.await_args_list
            assert create_awaits[0].args[:2] == (
                account_id,
                "test-project-copy",
            )
            assert create_awaits[1].args[:2] == (
                account_id,
                "test-project-copy-2",
            )
            assert create_awaits[0].kwargs["name"] == "test-project-copy"
            assert create_awaits[1].kwargs["name"] == "test-project-copy-2"

    async def test_delete_project_async_deletes_voice_configs(self) -> None:
        """Deleting a project calls VoiceConfigRepository.delete_by_project_id."""
        # Mock dependencies
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        project_id = uuid.uuid4()

        # Mock project
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.account_id = uuid.uuid4()
        mock_project.channel_identifiers = []

        # Create a real mock VoiceConfigRepository instance
        mock_voice_repo_instance = MagicMock()
        mock_voice_repo_instance.delete_by_project_id = AsyncMock(return_value=2)

        with (
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ) as mock_voice_repo_cls,
            patch("asyncio.get_event_loop"),
        ):
            # Setup mock repository instances
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project = AsyncMock(return_value=mock_project)
            mock_project_repo.delete_project = AsyncMock()

            # Act
            await delete_project_async(
                async_session=mock_session,
                context=context,
                project_id=project_id,
            )

            # Assert: Voice config repository was initialized (line 817 coverage)
            mock_voice_repo_cls.assert_called_once_with(mock_session)

            # Assert: Voice configs were deleted (line 818 coverage)
            mock_voice_repo_instance.delete_by_project_id.assert_called_once_with(
                project_id
            )

            # Assert: Project was deleted
            mock_project_repo.delete_project.assert_called_once_with(project_id)

    async def test_delete_project_async_snapshots_project_before_commit(self) -> None:
        """Project data is captured before helper commits expire ORM attrs."""
        mock_session = AsyncMock()
        mock_session.bind.sync_engine = MagicMock()

        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        class ExpiringProject:
            expired = False

            def _raise_if_expired(self) -> None:
                if self.expired:
                    raise AssertionError("project ORM attribute accessed after commit")

            def __getattribute__(self, name: str) -> object:
                guarded_names = {
                    "id",
                    "name",
                    "display_name",
                    "raw_config",
                    "config",
                    "channel_identifiers",
                    "store_hours",
                    "address",
                    "product_info",
                    "service_instruction",
                    "order_integration_id",
                    "timezone",
                    "transfer_message",
                    "reservation_link",
                    "ordering_link",
                    "call_forwarding_setup_completed",
                    "created_at",
                    "updated_at",
                    "account_id",
                    "agent_id",
                }
                if name in guarded_names:
                    self._raise_if_expired()
                return object.__getattribute__(self, name)

            def __init__(self) -> None:
                self.id = project_id
                self.name = "test-project"
                self.display_name = "Test Project"
                self.raw_config = {}
                self.channel_identifiers = ["voice:+15551234567"]
                self.store_hours = None
                self.address = None
                self.product_info = None
                self.service_instruction = None
                self.order_integration_id = None
                self.timezone = "America/Toronto"
                self.transfer_message = None
                self.reservation_link = None
                self.ordering_link = None
                self.call_forwarding_setup_completed = False
                self.created_at = None
                self.updated_at = None
                self.account_id = account_id
                self.agent_id = agent_id

        mock_project = ExpiringProject()
        mock_voice_repo_instance = MagicMock()

        async def delete_voice_configs(_: uuid.UUID) -> int:
            mock_project.expired = True
            return 2

        mock_voice_repo_instance.delete_by_project_id = AsyncMock(
            side_effect=delete_voice_configs
        )

        with (
            patch(
                "services.project_service._implementation.ProjectRepositoryAsync"
            ) as mock_project_repo_cls,
            patch(
                "services.project_service._implementation.VoiceConfigRepository",
                return_value=mock_voice_repo_instance,
            ),
            patch("asyncio.get_event_loop"),
        ):
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project = AsyncMock(return_value=mock_project)
            mock_project_repo.delete_project = AsyncMock()

            await delete_project_async(
                async_session=mock_session,
                context=context,
                project_id=project_id,
            )

            mock_project_repo.delete_project.assert_called_once_with(project_id)

    async def test_delete_project_async_handles_nonexistent_project(self) -> None:
        """Deleting a non-existent project returns early without errors."""
        mock_session = AsyncMock()
        context = UserContext(
            username="test-user",
            email="test@example.com",
            groups=[],
            display_name="Test User",
            role=UserRole.Admin,
        )

        project_id = uuid.uuid4()

        with patch(
            "services.project_service._implementation.ProjectRepositoryAsync"
        ) as mock_project_repo_cls:
            mock_project_repo = mock_project_repo_cls.return_value
            mock_project_repo.get_project = AsyncMock(return_value=None)

            # Act & Assert: Should not raise an error
            await delete_project_async(
                async_session=mock_session,
                context=context,
                project_id=project_id,
            )

            # Assert: Project repo was queried but nothing deleted
            mock_project_repo.get_project.assert_called_once_with(project_id)
            mock_project_repo.delete_project.assert_not_called()
