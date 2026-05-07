"""Tests for internal vision observation API endpoint."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.routes.internal.vision import create_observation
from api.schemas.operations.vision_observation import (
    EntityObservation,
    GenerateObservationResponse,
)


class TestCreateObservation:
    """Tests for POST /internal/vision/observations."""

    @pytest.mark.asyncio
    async def test_missing_image_url_and_file_raises_400(self):
        session = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_observation(
                camera_config_id=uuid.uuid4(),
                image_url=None,
                image=None,
                session=session,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_config_not_found_raises_404(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            side_effect=ValueError(f"Camera configuration {config_id} not found"),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await create_observation(
                    camera_config_id=config_id,
                    image_url="test/image.jpg",
                    image=None,
                    session=session,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validation_error_raises_400(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            side_effect=ValueError("Camera configuration is disabled"),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await create_observation(
                    camera_config_id=config_id,
                    image_url="test/image.jpg",
                    image=None,
                    session=session,
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unexpected_error_raises_500(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM connection timeout"),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await create_observation(
                    camera_config_id=config_id,
                    image_url="test/image.jpg",
                    image=None,
                    session=session,
                )
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_success_with_image_url(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        expected_response = GenerateObservationResponse(
            camera_config_id=config_id,
            observed_at=datetime.now(timezone.utc),
            entity_observations=[
                EntityObservation(
                    entity_id=entity_id,
                    entity_name="door_1",
                    state="open",
                    confidence=0.95,
                )
            ],
            raw_llm_response={"door_1": {"state": "open", "confidence": 0.95}},
            token_usage={"prompt_tokens": 100, "completion_tokens": 20},
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ):
            result = await create_observation(
                camera_config_id=config_id,
                image_url="cameras/test/frame.jpg",
                image=None,
                session=session,
            )

            assert result.camera_config_id == config_id
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].state == "open"

    @pytest.mark.asyncio
    async def test_success_with_uploaded_image(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        mock_image = AsyncMock()
        mock_image.read = AsyncMock(return_value=b"fake-image-bytes")

        expected_response = GenerateObservationResponse(
            camera_config_id=config_id,
            observed_at=datetime.now(timezone.utc),
            entity_observations=[
                EntityObservation(
                    entity_id=entity_id,
                    entity_name="oven_1",
                    state="on",
                    confidence=0.88,
                )
            ],
            raw_llm_response={"oven_1": {"state": "on", "confidence": 0.88}},
            token_usage={},
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ) as mock_gen:
            result = await create_observation(
                camera_config_id=config_id,
                image_url=None,
                image=mock_image,
                session=session,
            )

            assert result.camera_config_id == config_id
            assert result.entity_observations[0].entity_name == "oven_1"
            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["image_bytes"] == b"fake-image-bytes"
            assert call_kwargs["image_url"] is None

    @pytest.mark.asyncio
    async def test_uploaded_image_takes_precedence(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_image = AsyncMock()
        mock_image.read = AsyncMock(return_value=b"uploaded-bytes")

        expected_response = GenerateObservationResponse(
            camera_config_id=config_id,
            observed_at=datetime.now(timezone.utc),
            entity_observations=[],
            raw_llm_response={},
            token_usage={},
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ) as mock_gen:
            await create_observation(
                camera_config_id=config_id,
                image_url="cameras/should-be-ignored.jpg",
                image=mock_image,
                session=session,
            )

            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["image_bytes"] == b"uploaded-bytes"
