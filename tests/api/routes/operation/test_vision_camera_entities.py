"""Tests for api.routes.operation._vision_camera_configs camera-entity handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_camera_configuration import (
    AssignEntityRequest,
    CameraEntityResponse,
    ListCameraEntitiesResponse,
    UpdateCameraEntityRequest,
)

MODULE = "api.routes.operation._vision_camera_configs"


def _make_mapping_response(**overrides: object) -> CameraEntityResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "camera_config_id": uuid.uuid4(),
        "entity_id": uuid.uuid4(),
        "roi_hint": None,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return CameraEntityResponse(**defaults)  # type: ignore[arg-type]


class TestAssignEntityToCamera:

    @pytest.mark.asyncio
    async def test_success_commits_and_returns(self) -> None:
        from api.routes.operation._vision_camera_configs import assign_entity_to_camera

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        request = AssignEntityRequest(entity_id=entity_id, roi_hint={"x": 10})
        expected = _make_mapping_response(
            camera_config_id=config_id, entity_id=entity_id
        )

        with patch(
            f"{MODULE}.vision_config_service.assign_entity_to_camera",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await assign_entity_to_camera(
                session, project_id, config_id, request
            )

        assert result.entity_id == entity_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import assign_entity_to_camera

        session = AsyncMock()
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_config_service.assign_entity_to_camera",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await assign_entity_to_camera(
                    session, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_returns_400(self) -> None:
        from api.routes.operation._vision_camera_configs import assign_entity_to_camera

        session = AsyncMock()
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_config_service.assign_entity_to_camera",
            new_callable=AsyncMock,
            side_effect=ValueError("already assigned"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await assign_entity_to_camera(
                    session, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import assign_entity_to_camera

        session = AsyncMock()
        request = AssignEntityRequest(entity_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_config_service.assign_entity_to_camera",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await assign_entity_to_camera(
                    session, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 500


class TestUnassignEntityFromCamera:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            unassign_entity_from_camera,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.unassign_entity_from_camera",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await unassign_entity_from_camera(
                session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            )

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            unassign_entity_from_camera,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.unassign_entity_from_camera",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await unassign_entity_from_camera(
                    session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_not_assigned_returns_400(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            unassign_entity_from_camera,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.unassign_entity_from_camera",
            new_callable=AsyncMock,
            side_effect=ValueError("not assigned to camera"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await unassign_entity_from_camera(
                    session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            unassign_entity_from_camera,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.unassign_entity_from_camera",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await unassign_entity_from_camera(
                    session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 500


class TestListCameraEntities:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_camera_configs import list_camera_entities

        session = AsyncMock()
        expected = ListCameraEntitiesResponse(items=[], total=0)

        with patch(
            f"{MODULE}.vision_config_service.list_camera_entities",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await list_camera_entities(session, uuid.uuid4(), uuid.uuid4())

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import list_camera_entities

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.list_camera_entities",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_camera_entities(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import list_camera_entities

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.list_camera_entities",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_camera_entities(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestListCamerasForEntity:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_camera_configs import list_cameras_for_entity

        session = AsyncMock()
        expected = ListCameraEntitiesResponse(items=[], total=0)

        with patch(
            f"{MODULE}.vision_config_service.list_cameras_for_entity",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await list_cameras_for_entity(session, uuid.uuid4(), uuid.uuid4())

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import list_cameras_for_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.list_cameras_for_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_cameras_for_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import list_cameras_for_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.list_cameras_for_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_cameras_for_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestUpdateCameraEntity:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_entity

        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        request = UpdateCameraEntityRequest(roi_hint={"x": 50})
        expected = _make_mapping_response(
            camera_config_id=config_id, entity_id=entity_id, roi_hint={"x": 50}
        )

        with patch(
            f"{MODULE}.vision_config_service.update_camera_entity",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_camera_entity(
                session, uuid.uuid4(), config_id, entity_id, request
            )

        assert result.roi_hint == {"x": 50}

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_entity

        session = AsyncMock()
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with patch(
            f"{MODULE}.vision_config_service.update_camera_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_camera_entity(
                    session,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                    request,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_not_assigned_returns_400(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_entity

        session = AsyncMock()
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with patch(
            f"{MODULE}.vision_config_service.update_camera_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not assigned to camera"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_camera_entity(
                    session,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                    request,
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_entity

        session = AsyncMock()
        request = UpdateCameraEntityRequest(roi_hint={"x": 1})

        with patch(
            f"{MODULE}.vision_config_service.update_camera_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_camera_entity(
                    session,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    uuid.uuid4(),
                    request,
                )
            assert exc_info.value.status_code == 500
