"""Tests for api.routes.operation._vision_camera_configs handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_camera_configuration import (
    CameraConfigResponse,
    CreateCameraConfigRequest,
    ListCameraConfigsResponse,
    UpdateCameraConfigRequest,
)

MODULE = "api.routes.operation._vision_camera_configs"
SERVICE_MODULE = "services.vision_config_service._implementation"


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
        "structured_observations_enabled": False,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "updated_at": None,
    }
    defaults.update(overrides)
    return CameraConfigResponse.model_validate(defaults)


class TestCreateCameraConfig:

    @pytest.mark.asyncio
    async def test_success_without_images(self) -> None:
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
            result = await create_camera_config(session, project_id, request, [], [])

        assert result.name == "Front Door"

    @pytest.mark.asyncio
    async def test_success_with_reference_images(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Front Door",
            llm_prompt="Analyze",
        )
        initial_response = _make_response(id=config_id, project_id=project_id)
        uploaded_images = [
            {
                "url": "vision/ref/img1.jpg",
                "description": "desc1",
            }
        ]
        updated_response = _make_response(
            id=config_id, project_id=project_id, reference_images=uploaded_images
        )

        mock_image = AsyncMock()
        mock_image.filename = "test.jpg"
        mock_image.read = AsyncMock(return_value=b"fake-image-data")

        with (
            patch(
                f"{MODULE}.vision_config_service.create_camera_config",
                new_callable=AsyncMock,
                return_value=initial_response,
            ),
            patch(
                f"{MODULE}.vision_config_service.upload_reference_images",
                new_callable=AsyncMock,
                return_value=uploaded_images,
            ),
            patch(
                f"{MODULE}.vision_config_service.update_camera_config",
                new_callable=AsyncMock,
                return_value=updated_response,
            ),
        ):
            result = await create_camera_config(
                session, project_id, request, [mock_image], ["desc1"]
            )

        assert result.reference_images == uploaded_images

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
                await create_camera_config(session, uuid.uuid4(), request, [], [])
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
                await create_camera_config(session, uuid.uuid4(), request, [], [])
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_update_failure_after_upload_cleans_up_s3(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Front Door",
            llm_prompt="Analyze",
        )
        initial_response = _make_response(id=config_id, project_id=project_id)
        uploaded_images = [
            {
                "url": "vision/ref/img1.jpg",
                "description": "desc1",
            }
        ]

        mock_image = AsyncMock()
        mock_image.filename = "test.jpg"
        mock_image.read = AsyncMock(return_value=b"fake-image-data")

        with (
            patch(
                f"{MODULE}.vision_config_service.create_camera_config",
                new_callable=AsyncMock,
                return_value=initial_response,
            ),
            patch(
                f"{MODULE}.vision_config_service.upload_reference_images",
                new_callable=AsyncMock,
                return_value=uploaded_images,
            ),
            patch(
                f"{MODULE}.vision_config_service.update_camera_config",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db error"),
            ),
            patch(
                f"{MODULE}.vision_config_service.cleanup_reference_images",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_camera_config(
                    session, project_id, request, [mock_image], ["desc1"]
                )
            assert exc_info.value.status_code == 500
            session.rollback.assert_called_once()
            mock_cleanup.assert_called_once_with(["vision/ref/img1.jpg"])


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


class TestCreateCameraConfigValueErrorWithUploadedFiles:

    @pytest.mark.asyncio
    async def test_value_error_after_upload_cleans_up(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Cam",
            llm_prompt="Analyze",
        )
        initial_response = _make_response(id=config_id, project_id=project_id)
        uploaded_images = [{"url": "vision/ref/img.jpg", "description": "d"}]

        mock_image = AsyncMock()
        mock_image.filename = "test.jpg"
        mock_image.read = AsyncMock(return_value=b"data")

        with (
            patch(
                f"{MODULE}.vision_config_service.create_camera_config",
                new_callable=AsyncMock,
                return_value=initial_response,
            ),
            patch(
                f"{MODULE}.vision_config_service.upload_reference_images",
                new_callable=AsyncMock,
                return_value=uploaded_images,
            ),
            patch(
                f"{MODULE}.vision_config_service.update_camera_config",
                new_callable=AsyncMock,
                side_effect=ValueError("bad data"),
            ),
            patch(
                f"{MODULE}.vision_config_service.cleanup_reference_images",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_camera_config(
                    session, project_id, request, [mock_image], ["d"]
                )
            assert exc_info.value.status_code == 400
            mock_cleanup.assert_called_once_with(["vision/ref/img.jpg"])

    @pytest.mark.asyncio
    async def test_http_exception_after_upload_cleans_up(self) -> None:
        from api.routes.operation._vision_camera_configs import create_camera_config

        session = AsyncMock()
        project_id = uuid.uuid4()
        config_id = uuid.uuid4()
        request = CreateCameraConfigRequest(
            signal_source_id=uuid.uuid4(),
            name="Cam",
            llm_prompt="Analyze",
        )
        initial_response = _make_response(id=config_id, project_id=project_id)
        uploaded_images = [{"url": "vision/ref/img.jpg", "description": "d"}]

        mock_image = AsyncMock()
        mock_image.filename = "test.jpg"
        mock_image.read = AsyncMock(return_value=b"data")

        with (
            patch(
                f"{MODULE}.vision_config_service.create_camera_config",
                new_callable=AsyncMock,
                return_value=initial_response,
            ),
            patch(
                f"{MODULE}.vision_config_service.upload_reference_images",
                new_callable=AsyncMock,
                return_value=uploaded_images,
            ),
            patch(
                f"{MODULE}.vision_config_service.update_camera_config",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=409, detail="conflict"),
            ),
            patch(
                f"{MODULE}.vision_config_service.cleanup_reference_images",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_camera_config(
                    session, project_id, request, [mock_image], ["d"]
                )
            assert exc_info.value.status_code == 409
            mock_cleanup.assert_called_once_with(["vision/ref/img.jpg"])


class TestPresignReferenceImages:

    @pytest.mark.asyncio
    async def test_presigns_urls(self) -> None:
        from services.vision_config_service._implementation import (
            _presign_reference_images,
        )

        images = [{"url": "vision/ref/img.jpg", "description": "test"}]

        with patch(
            f"{SERVICE_MODULE}.map_uri_to_s3_url",
            return_value="https://s3.example.com/presigned",
        ):
            result = await _presign_reference_images(images)

        assert result[0]["url"] == "https://s3.example.com/presigned"
        assert result[0]["description"] == "test"

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        from services.vision_config_service._implementation import (
            _presign_reference_images,
        )

        result = await _presign_reference_images([])
        assert result == []

    @pytest.mark.asyncio
    async def test_presign_failure_preserves_original_url(self) -> None:
        from services.vision_config_service._implementation import (
            _presign_reference_images,
        )

        images = [{"url": "vision/ref/img.jpg", "description": "test"}]

        with patch(
            f"{SERVICE_MODULE}.map_uri_to_s3_url",
            side_effect=RuntimeError("S3 down"),
        ):
            result = await _presign_reference_images(images)

        assert result[0]["url"] == "vision/ref/img.jpg"

    @pytest.mark.asyncio
    async def test_presign_empty_result_preserves_original(self) -> None:
        from services.vision_config_service._implementation import (
            _presign_reference_images,
        )

        images = [{"url": "vision/ref/img.jpg", "description": "test"}]

        with patch(
            f"{SERVICE_MODULE}.map_uri_to_s3_url",
            return_value="",
        ):
            result = await _presign_reference_images(images)

        assert result[0]["url"] == "vision/ref/img.jpg"

    @pytest.mark.asyncio
    async def test_non_dict_items_skipped(self) -> None:
        from services.vision_config_service._implementation import (
            _presign_reference_images,
        )

        images: list[object] = ["not-a-dict", 42]
        result = await _presign_reference_images(images)
        assert result == ["not-a-dict", 42]


class TestUploadReferenceImages:

    @pytest.mark.asyncio
    async def test_successful_upload(self) -> None:
        from services.vision_config_service._implementation import (
            upload_reference_images,
        )

        mock_image = AsyncMock()
        mock_image.filename = "photo.png"
        mock_image.read = AsyncMock(return_value=b"image-bytes")

        mock_response = MagicMock()
        mock_response.url = "https://s3/path"

        with patch(
            f"{SERVICE_MODULE}.write_asset",
            return_value=mock_response,
        ):
            result = await upload_reference_images(
                images=[mock_image],
                descriptions=["A clean kitchen"],
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
            )

        assert len(result) == 1
        assert result[0]["description"] == "A clean kitchen"
        assert "vision/reference_images/" in result[0]["url"]

    @pytest.mark.asyncio
    async def test_missing_filename_returns_400(self) -> None:
        from services.vision_config_service._implementation import (
            upload_reference_images,
        )

        mock_image = AsyncMock()
        mock_image.filename = ""
        mock_image.read = AsyncMock(return_value=b"data")

        with pytest.raises(HTTPException) as exc_info:
            await upload_reference_images(
                images=[mock_image],
                descriptions=["desc"],
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_description_returns_400(self) -> None:
        from services.vision_config_service._implementation import (
            upload_reference_images,
        )

        mock_image = AsyncMock()
        mock_image.filename = "img.jpg"
        mock_image.read = AsyncMock(return_value=b"data")

        with pytest.raises(HTTPException) as exc_info:
            await upload_reference_images(
                images=[mock_image],
                descriptions=[""],
                project_id=uuid.uuid4(),
                config_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_s3_failure_returns_500(self) -> None:
        from services.vision_config_service._implementation import (
            upload_reference_images,
        )

        mock_image = AsyncMock()
        mock_image.filename = "img.jpg"
        mock_image.read = AsyncMock(return_value=b"data")

        with patch(
            f"{SERVICE_MODULE}.write_asset",
            side_effect=RuntimeError("S3 connection failed"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await upload_reference_images(
                    images=[mock_image],
                    descriptions=["valid desc"],
                    project_id=uuid.uuid4(),
                    config_id=uuid.uuid4(),
                )
            assert exc_info.value.status_code == 500


class TestCleanupReferenceImages:

    @pytest.mark.asyncio
    async def test_deletes_files(self) -> None:
        from services.vision_config_service._implementation import (
            cleanup_reference_images,
        )

        with patch(
            f"{SERVICE_MODULE}.delete_asset",
            return_value=True,
        ) as mock_delete:
            await cleanup_reference_images(["path/a.jpg", "path/b.jpg"])

        assert mock_delete.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_list_does_nothing(self) -> None:
        from services.vision_config_service._implementation import (
            cleanup_reference_images,
        )

        with patch(f"{SERVICE_MODULE}.delete_asset") as mock_delete:
            await cleanup_reference_images([])

        mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        from services.vision_config_service._implementation import (
            cleanup_reference_images,
        )

        with patch(
            f"{SERVICE_MODULE}.delete_asset",
            side_effect=RuntimeError("S3 error"),
        ):
            await cleanup_reference_images(["path/a.jpg"])
