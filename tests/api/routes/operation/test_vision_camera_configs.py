"""Tests for api.routes.operation._vision_camera_configs handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_camera_configuration import (
    CameraConfigResponse,
    CreateCameraConfigRequest,
    ListCameraConfigsResponse,
    UpdateCameraConfigRequest,
)

MODULE = "api.routes.operation._vision_camera_configs"


def _make_response(**overrides: object) -> CameraConfigResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "signal_source_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "name": "Front Door",
        "llm_prompt": "Analyze",
        "llm_provider": "azure",
        "llm_model": "gpt-4o",
        "processing_interval_seconds": 15,
        "reference_images": [],
        "enabled": True,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "updated_at": None,
    }
    defaults.update(overrides)
    return CameraConfigResponse(**defaults)  # type: ignore[arg-type]


class TestCreateCameraConfig:

    @pytest.mark.asyncio
    async def test_success_commits_and_returns(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Front Door",
            llm_prompt="Analyze",
        )
        expected = _make_response(project_id=project_id)

        with patch(
            f"{MODULE}.vision_config_service.create_camera_config",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await create_camera_config(session, project_id, request)

        assert result.name == "Front Door"

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="X",
            llm_prompt="Y",
        )

        with patch(
            f"{MODULE}.vision_config_service.create_camera_config",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_camera_config(session, uuid.uuid4(), request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="X",
            llm_prompt="Y",
        )

        with patch(
            f"{MODULE}.vision_config_service.create_camera_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_camera_config(session, uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestGetCameraConfig:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_camera_configs import get_camera_config

        session = AsyncMock()
        config_id = uuid.uuid4()
        expected = _make_response(id=config_id)

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_camera_config(session, uuid.uuid4(), config_id)

        assert result.id == config_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import get_camera_config

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_camera_config(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import get_camera_config

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_camera_config(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestGetCameraConfigBySource:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            get_camera_config_by_source,
        )

        session = AsyncMock()
        signal_source_id = uuid.uuid4()
        expected = _make_response(signal_source_id=signal_source_id)

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config_by_source",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_camera_config_by_source(
                session, uuid.uuid4(), signal_source_id
            )

        assert result.signal_source_id == signal_source_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            get_camera_config_by_source,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config_by_source",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_camera_config_by_source(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import (
            get_camera_config_by_source,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.get_camera_config_by_source",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_camera_config_by_source(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestListCameraConfigs:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_camera_configs import list_camera_configs

        session = AsyncMock()
        expected = ListCameraConfigsResponse(items=[], total=0)

        with patch(
            f"{MODULE}.vision_config_service.list_camera_configs",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await list_camera_configs(session, uuid.uuid4())

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import list_camera_configs

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.list_camera_configs",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_camera_configs(session, uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestUpdateCameraConfig:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_config

        session = AsyncMock()
        config_id = uuid.uuid4()
        request = UpdateCameraConfigRequest(name="New Name")
        expected = _make_response(id=config_id, name="New Name")

        with patch(
            f"{MODULE}.vision_config_service.update_camera_config",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_camera_config(
                session, uuid.uuid4(), config_id, request
            )

        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_config

        session = AsyncMock()
        request = UpdateCameraConfigRequest(name="X")

        with patch(
            f"{MODULE}.vision_config_service.update_camera_config",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_camera_config(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import update_camera_config

        session = AsyncMock()
        request = UpdateCameraConfigRequest(name="X")

        with patch(
            f"{MODULE}.vision_config_service.update_camera_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_camera_config(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestDeleteCameraConfig:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_camera_configs import delete_camera_config

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.delete_camera_config",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await delete_camera_config(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_camera_configs import delete_camera_config

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.delete_camera_config",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_camera_config(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_camera_configs import delete_camera_config

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_config_service.delete_camera_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_camera_config(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500
