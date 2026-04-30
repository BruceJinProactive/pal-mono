"""Tests for vision_config_service camera-entity mapping operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_camera_configuration import (
    AssignEntityRequest,
    UpdateCameraEntityRequest,
)

MODULE = "services.vision_config_service._implementation"


def _make_config_mock(**overrides: object) -> MagicMock:
    c = MagicMock()
    c.id = overrides.get("id", uuid.uuid4())
    c.signal_source_id = overrides.get("signal_source_id", uuid.uuid4())
    c.project_id = overrides.get("project_id", uuid.uuid4())
    c.name = overrides.get("name", "Front Door Camera")
    c.llm_prompt = overrides.get("llm_prompt", "Analyze")
    c.llm_provider = overrides.get("llm_provider", "azure")
    c.llm_model = overrides.get("llm_model", "gpt-4o")
    c.processing_interval_seconds = overrides.get("processing_interval_seconds", 15)
    c.reference_images = overrides.get("reference_images", [])
    c.enabled = overrides.get("enabled", True)
    c.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    c.updated_at = overrides.get("updated_at", None)
    return c


def _make_entity_mock(**overrides: object) -> MagicMock:
    e = MagicMock()
    e.id = overrides.get("id", uuid.uuid4())
    e.project_id = overrides.get("project_id", uuid.uuid4())
    e.entity_type_id = overrides.get("entity_type_id", uuid.uuid4())
    e.name = overrides.get("name", "Oven 1")
    e.is_active = overrides.get("is_active", True)
    e.entity_metadata = overrides.get("entity_metadata", {})
    e.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    e.current_state_id = overrides.get("current_state_id", None)
    e.current_state_since = overrides.get("current_state_since", None)
    e.updated_at = overrides.get("updated_at", None)
    return e


def _make_mapping_mock(**overrides: object) -> MagicMock:
    m = MagicMock()
    m.id = overrides.get("id", uuid.uuid4())
    m.camera_config_id = overrides.get("camera_config_id", uuid.uuid4())
    m.entity_id = overrides.get("entity_id", uuid.uuid4())
    m.roi_hint = overrides.get("roi_hint", None)
    m.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return m


class TestAssignEntityToCamera:

    @pytest.mark.asyncio
    async def test_assigns_successfully(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        config = _make_config_mock(id=config_id, project_id=project_id)
        entity = _make_entity_mock(id=entity_id, project_id=project_id)
        request = AssignEntityRequest(entity_id=entity_id, roi_hint={"x": 10})

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            mock_entity_cls.return_value = entity_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = None
            mapping_repo.create.return_value = None
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                assign_entity_to_camera,
            )

            result = await assign_entity_to_camera(
                session, project_id, config_id, request
            )

            assert result.camera_config_id == config_id
            mapping_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_config_not_found_raises(self) -> None:
        session = AsyncMock()
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls:
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = None
            mock_config_cls.return_value = config_repo

            from services.vision_config_service._implementation import (
                assign_entity_to_camera,
            )

            with pytest.raises(ValueError, match="not found"):
                await assign_entity_to_camera(
                    session, uuid.uuid4(), uuid.uuid4(), request
                )

    @pytest.mark.asyncio
    async def test_entity_not_found_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = None
            mock_entity_cls.return_value = entity_repo

            from services.vision_config_service._implementation import (
                assign_entity_to_camera,
            )

            with pytest.raises(ValueError, match="not found"):
                await assign_entity_to_camera(session, project_id, config_id, request)

    @pytest.mark.asyncio
    async def test_duplicate_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        config = _make_config_mock(id=config_id, project_id=project_id)
        entity = _make_entity_mock(id=entity_id, project_id=project_id)
        existing = _make_mapping_mock(camera_config_id=config_id, entity_id=entity_id)
        request = AssignEntityRequest(entity_id=entity_id)

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            mock_entity_cls.return_value = entity_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = existing
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                assign_entity_to_camera,
            )

            with pytest.raises(ValueError, match="already assigned"):
                await assign_entity_to_camera(session, project_id, config_id, request)

    @pytest.mark.asyncio
    async def test_wrong_project_config_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        other_project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=other_project_id)
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls:
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            from services.vision_config_service._implementation import (
                assign_entity_to_camera,
            )

            with pytest.raises(ValueError, match="not found"):
                await assign_entity_to_camera(session, project_id, config_id, request)


class TestUnassignEntityFromCamera:

    @pytest.mark.asyncio
    async def test_unassigns_successfully(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        mapping_id = uuid.uuid4()

        config = _make_config_mock(id=config_id, project_id=project_id)
        existing = _make_mapping_mock(
            id=mapping_id, camera_config_id=config_id, entity_id=entity_id
        )

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = existing
            mapping_repo.delete.return_value = True
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                unassign_entity_from_camera,
            )

            result = await unassign_entity_from_camera(
                session, project_id, config_id, entity_id
            )

            assert result is True
            mapping_repo.delete.assert_awaited_once_with(mapping_id)

    @pytest.mark.asyncio
    async def test_config_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls:
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = None
            mock_config_cls.return_value = config_repo

            from services.vision_config_service._implementation import (
                unassign_entity_from_camera,
            )

            with pytest.raises(ValueError, match="not found"):
                await unassign_entity_from_camera(
                    session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                )

    @pytest.mark.asyncio
    async def test_mapping_not_found_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = None
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                unassign_entity_from_camera,
            )

            with pytest.raises(ValueError, match="not assigned"):
                await unassign_entity_from_camera(
                    session, project_id, config_id, uuid.uuid4()
                )


class TestListCameraEntities:

    @pytest.mark.asyncio
    async def test_returns_all(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)
        mappings = [
            _make_mapping_mock(camera_config_id=config_id),
            _make_mapping_mock(camera_config_id=config_id),
        ]

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.list_by_camera.return_value = mappings
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                list_camera_entities,
            )

            result = await list_camera_entities(session, project_id, config_id)

            assert result.total == 2

    @pytest.mark.asyncio
    async def test_config_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls:
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = None
            mock_config_cls.return_value = config_repo

            from services.vision_config_service._implementation import (
                list_camera_entities,
            )

            with pytest.raises(ValueError, match="not found"):
                await list_camera_entities(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.list_by_camera.return_value = []
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                list_camera_entities,
            )

            result = await list_camera_entities(session, project_id, config_id)

            assert result.total == 0


class TestListCamerasForEntity:

    @pytest.mark.asyncio
    async def test_returns_all(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)
        mappings = [_make_mapping_mock(entity_id=entity_id)]

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            mock_entity_cls.return_value = entity_repo

            mapping_repo = AsyncMock()
            mapping_repo.list_by_entity.return_value = mappings
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                list_cameras_for_entity,
            )

            result = await list_cameras_for_entity(session, project_id, entity_id)

            assert result.total == 1

    @pytest.mark.asyncio
    async def test_entity_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls:
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = None
            mock_entity_cls.return_value = entity_repo

            from services.vision_config_service._implementation import (
                list_cameras_for_entity,
            )

            with pytest.raises(ValueError, match="not found"):
                await list_cameras_for_entity(session, uuid.uuid4(), uuid.uuid4())


class TestUpdateCameraEntity:

    @pytest.mark.asyncio
    async def test_updates_roi_hint(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        mapping_id = uuid.uuid4()

        config = _make_config_mock(id=config_id, project_id=project_id)
        existing = _make_mapping_mock(
            id=mapping_id, camera_config_id=config_id, entity_id=entity_id
        )
        updated = _make_mapping_mock(
            id=mapping_id,
            camera_config_id=config_id,
            entity_id=entity_id,
            roi_hint={"x": 50, "y": 60},
        )
        request = UpdateCameraEntityRequest(roi_hint={"x": 50, "y": 60})

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = existing
            mapping_repo.update.return_value = updated
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                update_camera_entity,
            )

            result = await update_camera_entity(
                session, project_id, config_id, entity_id, request
            )

            assert result.roi_hint == {"x": 50, "y": 60}

    @pytest.mark.asyncio
    async def test_config_not_found_raises(self) -> None:
        session = AsyncMock()
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls:
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = None
            mock_config_cls.return_value = config_repo

            from services.vision_config_service._implementation import (
                update_camera_entity,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_camera_entity(
                    session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), request
                )

    @pytest.mark.asyncio
    async def test_mapping_not_found_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        config = _make_config_mock(id=config_id, project_id=project_id)
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = None
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                update_camera_entity,
            )

            with pytest.raises(ValueError, match="not assigned"):
                await update_camera_entity(
                    session, project_id, config_id, uuid.uuid4(), request
                )

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        config = _make_config_mock(id=config_id, project_id=project_id)
        existing = _make_mapping_mock(camera_config_id=config_id, entity_id=entity_id)
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with (
            patch(f"{MODULE}.VisionCameraConfigurationRepository") as mock_config_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            config_repo = AsyncMock()
            config_repo.get_by_id.return_value = config
            mock_config_cls.return_value = config_repo

            mapping_repo = AsyncMock()
            mapping_repo.get_by_camera_and_entity.return_value = existing
            mapping_repo.update.return_value = None
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_config_service._implementation import (
                update_camera_entity,
            )

            with pytest.raises(ValueError, match="not assigned"):
                await update_camera_entity(
                    session, project_id, config_id, entity_id, request
                )
