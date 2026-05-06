"""Tests for vision_config_service camera configuration CRUD operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_camera_configuration import (
    CreateCameraConfigRequest,
    UpdateCameraConfigRequest,
)

MODULE = "services.vision_config_service._implementation"


def _make_config_mock(**overrides: object) -> MagicMock:
    c = MagicMock()
    c.id = overrides.get("id", uuid.uuid4())
    c.signal_source_id = overrides.get("signal_source_id", uuid.uuid4())
    c.project_id = overrides.get("project_id", uuid.uuid4())
    c.name = overrides.get("name", "Front Door Camera")
    c.llm_prompt = overrides.get("llm_prompt", "Analyze the image")
    c.llm_provider = overrides.get("llm_provider", "azure")
    c.llm_model = overrides.get("llm_model", "gpt-4o")
    c.processing_interval_seconds = overrides.get("processing_interval_seconds", 15)
    c.reference_images = overrides.get("reference_images", [])
    c.enabled = overrides.get("enabled", True)
    c.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    c.updated_at = overrides.get("updated_at", None)
    return c


class TestCreateCameraConfig:

    @pytest.mark.asyncio
    async def test_creates_config(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        signal_source_id = uuid.uuid4()

        request = CreateCameraConfigRequest(
            signal_source_id=signal_source_id,
            name="Front Door",
            llm_prompt="Check for activity",
        )
        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_signal_source.return_value = None
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                create_camera_config,
            )

            result = await create_camera_config(session, project_id, request)

            assert result.signal_source_id == signal_source_id
            repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_source_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        signal_source_id = uuid.uuid4()

        request = CreateCameraConfigRequest(
            signal_source_id=signal_source_id,
            name="Front Door",
            llm_prompt="Check for activity",
        )
        existing = _make_config_mock(signal_source_id=signal_source_id)

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_signal_source.return_value = existing
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                create_camera_config,
            )

            with pytest.raises(ValueError, match="already exists"):
                await create_camera_config(session, project_id, request)


class TestGetCameraConfig:

    @pytest.mark.asyncio
    async def test_returns_config(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import get_camera_config

            result = await get_camera_config(session, project_id, config_id)

            assert result.id == config_id

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import get_camera_config

            with pytest.raises(ValueError, match="not found"):
                await get_camera_config(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_wrong_project_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        other_project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=other_project_id)

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import get_camera_config

            with pytest.raises(ValueError, match="not found"):
                await get_camera_config(session, project_id, config_id)


class TestGetCameraConfigBySource:

    @pytest.mark.asyncio
    async def test_returns_config(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        signal_source_id = uuid.uuid4()
        config = _make_config_mock(
            project_id=project_id, signal_source_id=signal_source_id
        )

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_signal_source.return_value = config
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                get_camera_config_by_source,
            )

            result = await get_camera_config_by_source(
                session, project_id, signal_source_id
            )

            assert result.signal_source_id == signal_source_id

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_signal_source.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                get_camera_config_by_source,
            )

            with pytest.raises(ValueError, match="not found"):
                await get_camera_config_by_source(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_wrong_project_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        other_project_id = uuid.uuid4()
        signal_source_id = uuid.uuid4()
        config = _make_config_mock(
            project_id=other_project_id, signal_source_id=signal_source_id
        )

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_signal_source.return_value = config
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                get_camera_config_by_source,
            )

            with pytest.raises(ValueError, match="not found"):
                await get_camera_config_by_source(session, project_id, signal_source_id)


class TestListCameraConfigs:

    @pytest.mark.asyncio
    async def test_returns_all(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        configs = [
            _make_config_mock(project_id=project_id, name="Front Door"),
            _make_config_mock(project_id=project_id, name="Back Door"),
        ]

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.list_by_project.return_value = configs
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                list_camera_configs,
            )

            result = await list_camera_configs(session, project_id)

            assert result.total == 2

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.list_by_project.return_value = []
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                list_camera_configs,
            )

            result = await list_camera_configs(session, uuid.uuid4())

            assert result.total == 0


class TestUpdateCameraConfig:

    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)
        updated = _make_config_mock(
            id=config_id, project_id=project_id, name="Updated Name"
        )

        request = UpdateCameraConfigRequest(name="Updated Name")

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            repo.update.return_value = updated
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                update_camera_config,
            )

            result = await update_camera_config(session, project_id, config_id, request)

            assert result.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_updates_all_optional_fields(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)
        updated = _make_config_mock(
            id=config_id,
            project_id=project_id,
            llm_prompt="New prompt",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            processing_interval_seconds=30,
            reference_images=["img1.jpg"],
            enabled=False,
        )

        request = UpdateCameraConfigRequest(
            llm_prompt="New prompt",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            processing_interval_seconds=30,
            reference_images=["img1.jpg"],
            enabled=False,
        )

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            repo.update.return_value = updated
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                update_camera_config,
            )

            result = await update_camera_config(session, project_id, config_id, request)

            assert result.llm_prompt == "New prompt"
            assert result.enabled is False

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        request = UpdateCameraConfigRequest(name="X")

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                update_camera_config,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_camera_config(session, uuid.uuid4(), uuid.uuid4(), request)

    @pytest.mark.asyncio
    async def test_no_changes_returns_existing(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        request = UpdateCameraConfigRequest()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                update_camera_config,
            )

            result = await update_camera_config(session, project_id, config_id, request)

            assert result.id == config_id
            repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        request = UpdateCameraConfigRequest(name="New")

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            repo.update.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                update_camera_config,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_camera_config(session, project_id, config_id, request)


class TestDeleteCameraConfig:

    @pytest.mark.asyncio
    async def test_deletes_config(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            repo.delete.return_value = True
            mock_repo_cls.return_value = repo

            mapping_repo = AsyncMock()
            mapping_repo.delete_by_vision_config.return_value = 0
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                delete_camera_config,
            )

            result = await delete_camera_config(session, project_id, config_id)

            assert result is True
            mapping_repo.delete_by_vision_config.assert_called_once_with(config_id)

    @pytest.mark.asyncio
    async def test_deletes_config_with_existing_mappings(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = config
            repo.delete.return_value = True
            mock_repo_cls.return_value = repo

            mapping_repo = AsyncMock()
            mapping_repo.delete_by_vision_config.return_value = 3
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                delete_camera_config,
            )

            result = await delete_camera_config(session, project_id, config_id)

            assert result is True
            mapping_repo.delete_by_vision_config.assert_called_once_with(config_id)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_config_service._implementation import (
                delete_camera_config,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_camera_config(session, uuid.uuid4(), uuid.uuid4())
