"""Tests for internal vision observation API endpoint."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.internal.vision import create_observation, get_configuration_prompt
from api.schemas.operations.vision_observation import (
    EntityObservation,
    GenerateObservationResponse,
)
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.vision_observation_service._implementation import (
    ConfigurationPromptResult,
)


class TestCreateObservation:
    """Tests for POST /internal/vision/observations."""

    @pytest.mark.asyncio
    async def test_missing_image_url_and_file_raises_400(self):
        session = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_observation(
                camera_id=uuid.uuid4(),
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
                    camera_id=config_id,
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
                    camera_id=config_id,
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
                    camera_id=config_id,
                    image_url="test/image.jpg",
                    image=None,
                    session=session,
                )
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_unprocessable_image_skip_response_does_not_raise_http_error(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        observed_at = datetime(2026, 2, 12, 16, 52, 25, tzinfo=timezone.utc)

        expected_response = GenerateObservationResponse(
            camera_id=config_id,
            observed_at=observed_at,
            entity_observations=[],
            raw_llm_response={
                "error": "Unable to process input image",
                "skip_reason": "unprocessable_image",
            },
            token_usage={
                "observed": False,
                "image_relevant": False,
                "skip_reason": "unprocessable_image",
            },
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ):
            result = await create_observation(
                camera_id=config_id,
                image_url="test/image.jpg",
                image=None,
                session=session,
            )

            assert result.entity_observations == []
            assert result.token_usage["skip_reason"] == "unprocessable_image"

    @pytest.mark.asyncio
    async def test_success_with_image_url(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        expected_response = GenerateObservationResponse(
            camera_id=config_id,
            observed_at=datetime.now(timezone.utc),
            entity_observations=[
                EntityObservation(
                    entity_id=entity_id,
                    entity_name="door_1",
                    camera_id=config_id,
                    state="open",
                )
            ],
            raw_llm_response={"door_1": {"state": "open"}},
            token_usage={"prompt_tokens": 100, "completion_tokens": 20},
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ):
            result = await create_observation(
                camera_id=config_id,
                image_url="cameras/test/frame.jpg",
                image=None,
                session=session,
            )

            assert result.camera_id == config_id
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].state == "open"

    @pytest.mark.asyncio
    async def test_success_with_uploaded_image(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        mock_image = AsyncMock()
        mock_image.read = AsyncMock(return_value=b"fake-image-bytes")
        observed_at = datetime(2026, 2, 12, 16, 52, 25, tzinfo=timezone.utc)

        expected_response = GenerateObservationResponse(
            camera_id=config_id,
            observed_at=observed_at,
            entity_observations=[
                EntityObservation(
                    entity_id=entity_id,
                    entity_name="oven_1",
                    camera_id=config_id,
                    state="on",
                )
            ],
            raw_llm_response={"oven_1": {"state": "on"}},
            token_usage={},
        )

        with patch(
            "services.vision_observation_service.generate_observation",
            new_callable=AsyncMock,
            return_value=expected_response,
        ) as mock_gen:
            result = await create_observation(
                camera_id=config_id,
                image_url=None,
                image=mock_image,
                observed_at=observed_at,
                session=session,
            )

            assert result.camera_id == config_id
            assert result.entity_observations[0].entity_name == "oven_1"
            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["image_bytes"] == b"fake-image-bytes"
            assert call_kwargs["image_url"] is None
            assert call_kwargs["observed_at"] == observed_at

    @pytest.mark.asyncio
    async def test_uploaded_image_takes_precedence(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_image = AsyncMock()
        mock_image.read = AsyncMock(return_value=b"uploaded-bytes")

        expected_response = GenerateObservationResponse(
            camera_id=config_id,
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
                camera_id=config_id,
                image_url="cameras/should-be-ignored.jpg",
                image=mock_image,
                session=session,
            )

            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["image_bytes"] == b"uploaded-bytes"


class TestGetConfigurationPrompt:
    """Tests for GET /internal/vision/.../prompt."""

    @pytest.mark.asyncio
    async def test_config_not_found_raises_404(self):
        session = AsyncMock()

        with patch(
            "services.vision_observation_service.get_configuration_prompt",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_configuration_prompt(
                    config_id=uuid.uuid4(),
                    session=session,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_no_test_events(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        prompt_result = ConfigurationPromptResult(
            llm_provider="google",
            llm_model="gemini-2.0-flash",
            system_prompt="You are a monitoring assistant...",
            structured_output={"type": "object", "properties": {}},
            entities_with_states=[
                {
                    "name": "door_1",
                    "roi_hint": {"x": 10, "y": 20, "width": 100, "height": 200},
                },
                {"name": "door_2", "roi_hint": None},
            ],
        )

        with (
            patch(
                "services.vision_observation_service.get_configuration_prompt",
                new_callable=AsyncMock,
                return_value=prompt_result,
            ),
            patch(
                "api.routes.internal.vision.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
            patch("api.routes.internal.vision.VisionEntityRepository"),
            patch("api.routes.internal.vision.VisionEntityStateDefinitionRepository"),
        ):
            mock_event_repo_cls.return_value.list_test_events_by_config = AsyncMock(
                return_value=[]
            )

            result = await get_configuration_prompt(
                config_id=config_id,
                session=session,
            )

            assert result.config_id == config_id
            assert result.llm_provider == "google"
            assert result.llm_model == "gemini-2.0-flash"
            assert len(result.entity_roi_hints) == 2
            assert result.entity_roi_hints[0].entity_name == "door_1"
            assert result.entity_roi_hints[0].roi_hint == {
                "x": 10,
                "y": 20,
                "width": 100,
                "height": 200,
            }
            assert result.entity_roi_hints[1].entity_name == "door_2"
            assert result.entity_roi_hints[1].roi_hint is None
            assert result.test_events == []

    @pytest.mark.asyncio
    async def test_success_with_test_events_grouped(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        state_id = uuid.uuid4()

        prompt_result = ConfigurationPromptResult(
            llm_provider="azure",
            llm_model="gpt-4o",
            system_prompt="prompt",
            structured_output={"type": "object", "properties": {}},
            entities_with_states=[],
        )

        test_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity_id,
            new_state_id=state_id,
            observed_at=datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
            event_metadata={"is_test": True, "test_group": "group-a"},
            camera_config_id=config_id,
            frame_s3_key="s3://bucket/frames/test-frame.jpg",
        )

        mock_entity = MagicMock()
        mock_entity.name = "main_gate"

        mock_state_def = MagicMock()
        mock_state_def.name = "open"

        with (
            patch(
                "services.vision_observation_service.get_configuration_prompt",
                new_callable=AsyncMock,
                return_value=prompt_result,
            ),
            patch(
                "api.routes.internal.vision.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
            patch(
                "api.routes.internal.vision.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "api.routes.internal.vision.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "api.routes.internal.vision.map_uri_to_s3_url",
                return_value="https://s3.amazonaws.com/bucket/presigned-url",
            ),
        ):
            mock_event_repo_cls.return_value.list_test_events_by_config = AsyncMock(
                return_value=[test_event]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_state_def
            )

            result = await get_configuration_prompt(
                config_id=config_id,
                session=session,
            )

            assert len(result.test_events) == 1
            assert result.test_events[0].test_group == "group-a"
            assert len(result.test_events[0].events) == 1
            event_info = result.test_events[0].events[0]
            assert event_info.entity_name == "main_gate"
            assert event_info.new_state_name == "open"
            assert (
                event_info.frame_url == "https://s3.amazonaws.com/bucket/presigned-url"
            )

    @pytest.mark.asyncio
    async def test_frame_url_graceful_on_presign_failure(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        state_id = uuid.uuid4()

        prompt_result = ConfigurationPromptResult(
            llm_provider="azure",
            llm_model="gpt-4o",
            system_prompt="prompt",
            structured_output={"type": "object", "properties": {}},
            entities_with_states=[],
        )

        test_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity_id,
            new_state_id=state_id,
            observed_at=datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc),
            event_metadata={"is_test": True, "test_group": "group-b"},
            camera_config_id=config_id,
            frame_s3_key="s3://bucket/frames/bad-frame.jpg",
        )

        mock_entity = MagicMock()
        mock_entity.name = "counter"

        mock_state_def = MagicMock()
        mock_state_def.name = "dirty"

        with (
            patch(
                "services.vision_observation_service.get_configuration_prompt",
                new_callable=AsyncMock,
                return_value=prompt_result,
            ),
            patch(
                "api.routes.internal.vision.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
            patch(
                "api.routes.internal.vision.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "api.routes.internal.vision.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "api.routes.internal.vision.map_uri_to_s3_url",
                side_effect=Exception("S3 presign failed"),
            ),
        ):
            mock_event_repo_cls.return_value.list_test_events_by_config = AsyncMock(
                return_value=[test_event]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_state_def
            )

            result = await get_configuration_prompt(
                config_id=config_id,
                session=session,
            )

            event_info = result.test_events[0].events[0]
            assert event_info.frame_url is None
