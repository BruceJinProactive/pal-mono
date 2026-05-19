"""Tests for vision observation service implementation."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.vision_observation_service._implementation import (
    _build_entity_state_schema,
    _build_system_prompt,
    _extract_camera_name_from_s3_key,
    _format_roi_hint,
    generate_observation,
)


class TestBuildEntityStateSchema:
    """Tests for dynamic JSON schema generation from entities."""

    def test_single_entity(self):
        entities = [
            {"name": "front_door", "state_names": ["open", "closed"]},
        ]
        schema = _build_entity_state_schema(entities)

        assert schema["type"] == "object"
        assert "front_door" in schema["properties"]
        assert schema["properties"]["front_door"]["properties"]["state"]["enum"] == [
            "open",
            "closed",
        ]
        assert schema["properties"]["front_door"]["properties"]["confidence"] == {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        }
        assert set(schema["required"]) == {"front_door", "image_relevant"}
        assert schema["properties"]["image_relevant"] == {"type": "boolean"}
        assert schema["additionalProperties"] is False

    def test_multiple_entities(self):
        entities = [
            {"name": "door_a", "state_names": ["open", "closed"]},
            {"name": "light_1", "state_names": ["on", "off", "dimmed"]},
        ]
        schema = _build_entity_state_schema(entities)

        assert set(schema["required"]) == {"door_a", "light_1", "image_relevant"}
        assert len(schema["properties"]) == 3
        assert schema["properties"]["light_1"]["properties"]["state"]["enum"] == [
            "on",
            "off",
            "dimmed",
        ]

    def test_empty_entities(self):
        schema = _build_entity_state_schema([])
        assert schema["type"] == "object"
        assert schema["properties"] == {"image_relevant": {"type": "boolean"}}
        assert schema["required"] == ["image_relevant"]


class TestFormatRoiHint:
    """Tests for ROI hint formatting."""

    def test_none_input(self):
        assert _format_roi_hint(None) is None

    def test_empty_dict(self):
        assert _format_roi_hint({}) is None

    def test_with_coordinates(self):
        roi: dict[str, object] = {
            "x": 411,
            "y": 249,
            "width": 207,
            "height": 234,
        }
        result = _format_roi_hint(roi)
        assert result == "[411, 249, 207, 234]"

    def test_with_w_h_keys(self):
        roi: dict[str, object] = {"x": 100, "y": 200, "w": 300, "h": 400}
        result = _format_roi_hint(roi)
        assert result == "[100, 200, 300, 400]"

    def test_with_missing_keys(self):
        roi: dict[str, object] = {"x": 500, "label": "zone-1"}
        result = _format_roi_hint(roi)
        assert result is None


class TestExtractCameraNameFromS3Key:
    """Tests for camera name extraction from S3 key."""

    def test_valid_cameras_path(self):
        assert (
            _extract_camera_name_from_s3_key("cameras/my-camera/frame.jpg")
            == "my-camera"
        )

    def test_valid_cameras_path_deeper(self):
        assert (
            _extract_camera_name_from_s3_key("cameras/kitchen-cam/2026/05/13/frame.jpg")
            == "kitchen-cam"
        )

    def test_leading_slash(self):
        assert (
            _extract_camera_name_from_s3_key("/cameras/lobby-cam/img.png")
            == "lobby-cam"
        )

    def test_non_cameras_prefix(self):
        assert _extract_camera_name_from_s3_key("uploads/my-camera/frame.jpg") is None

    def test_too_few_parts(self):
        assert _extract_camera_name_from_s3_key("cameras") is None

    def test_empty_string(self):
        assert _extract_camera_name_from_s3_key("") is None


class TestBuildSystemPrompt:
    """Tests for system prompt generation."""

    def test_includes_entity_types(self):
        entity_type_defs = {
            "door": {
                "display_name": "Door",
                "state_names": ["open", "closed"],
                "state_criteria": {"open": "Door is visibly open"},
            },
        }
        entities = [
            {
                "name": "front_door",
                "type_name": "door",
                "state_names": ["open", "closed"],
                "roi_hint": None,
            },
        ]
        prompt = _build_system_prompt("", entity_type_defs, entities)

        assert "Door" in prompt
        assert "States (pick one):" in prompt
        assert '"open" (Door is visibly open)' in prompt
        assert '"closed"' in prompt

    def test_includes_user_context(self):
        prompt = _build_system_prompt(
            "This is a restaurant kitchen camera",
            {"oven": {"display_name": "Oven", "state_names": ["on", "off"]}},
            [
                {
                    "name": "oven_1",
                    "type_name": "oven",
                    "state_names": ["on", "off"],
                    "roi_hint": None,
                }
            ],
        )
        assert "This is a restaurant kitchen camera" in prompt
        assert "Context:" in prompt

    def test_empty_user_prompt_no_context_section(self):
        prompt = _build_system_prompt(
            "",
            {"light": {"display_name": "Light", "state_names": ["on", "off"]}},
            [
                {
                    "name": "light_1",
                    "type_name": "light",
                    "state_names": ["on", "off"],
                    "roi_hint": None,
                }
            ],
        )
        assert "Context:" not in prompt

    def test_includes_roi_hint(self):
        roi = {"x": 100, "y": 200, "width": 300, "height": 400}
        entities = [
            {
                "name": "door_1",
                "type_name": "door",
                "state_names": ["open", "closed"],
                "roi_hint": roi,
            },
        ]
        prompt = _build_system_prompt(
            "",
            {"door": {"display_name": "Door", "state_names": ["open", "closed"]}},
            entities,
        )
        assert "ROI: [100, 200, 300, 400]" in prompt

    def test_includes_entity_names(self):
        entities = [
            {
                "name": "parking_lot_gate",
                "type_name": "gate",
                "state_names": ["open", "closed"],
                "roi_hint": None,
            },
        ]
        prompt = _build_system_prompt(
            "",
            {"gate": {"display_name": "Gate", "state_names": ["open", "closed"]}},
            entities,
        )
        assert '"parking_lot_gate"' in prompt
        assert "Gate" in prompt

    def test_groups_entities_by_type(self):
        entity_type_defs = {
            "lane": {
                "display_name": "Drive-Through Lane",
                "state_names": ["occupied", "empty"],
                "state_criteria": {
                    "occupied": "vehicle present",
                    "empty": "no vehicle",
                },
            },
        }
        entities = [
            {
                "name": "Lane 1",
                "type_name": "lane",
                "state_names": ["occupied", "empty"],
                "roi_hint": {"x": 100, "y": 0, "width": 200, "height": 1000},
            },
            {
                "name": "Lane 2",
                "type_name": "lane",
                "state_names": ["occupied", "empty"],
                "roi_hint": {"x": 400, "y": 0, "width": 200, "height": 1000},
            },
        ]
        prompt = _build_system_prompt("", entity_type_defs, entities)

        assert prompt.count("States (pick one):") == 1
        assert '"Lane 1"' in prompt
        assert '"Lane 2"' in prompt
        assert "ROI: [100, 0, 200, 1000]" in prompt
        assert "ROI: [400, 0, 200, 1000]" in prompt


class TestGenerateObservation:
    """Tests for the main generate_observation function."""

    @pytest.mark.asyncio
    async def test_config_not_found_returns_none(self):
        session = AsyncMock()

        with patch(
            "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
        ) as mock_config_repo_cls:
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=None
            )
            mock_config_repo_cls.return_value.get_by_name = AsyncMock(return_value=None)

            result = await generate_observation(session, uuid.uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_fallback_to_name_lookup_from_image_url(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.enabled = True
        mock_config.llm_prompt = "test"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "door_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = None

        mock_state_def = MagicMock()
        mock_state_def.id = uuid.uuid4()
        mock_state_def.name = "open"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        llm_result = {
            "result": {"door_1": {"state": "open", "confidence": 0.9}},
            "token_usage": {},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        fake_image_bytes = b"fake-s3-image"

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
            patch(
                "services.vision_observation_service._implementation._fetch_s3_bytes",
                AsyncMock(return_value=fake_image_bytes),
            ),
            patch(
                "services.vision_observation_service._implementation.create_monitoring_llm_provider",
                return_value=mock_llm_provider,
            ),
            patch(
                "services.vision_observation_service._implementation.asyncio.to_thread",
                side_effect=_sync_to_thread,
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=None
            )
            mock_config_repo_cls.return_value.get_by_name = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_entity_repo_cls.return_value.update = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            camera_id = uuid.uuid4()
            result = await generate_observation(
                session, camera_id, image_url="cameras/my-kitchen-cam/frame.jpg"
            )

            assert result is not None
            assert result.camera_id == camera_id
            assert len(result.entity_observations) == 1
            mock_config_repo_cls.return_value.get_by_name.assert_awaited_once_with(
                "my-kitchen-cam"
            )

    @pytest.mark.asyncio
    async def test_config_disabled_returns_none(self):
        session = AsyncMock()
        mock_config = MagicMock()
        mock_config.enabled = False

        with patch(
            "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
        ) as mock_config_repo_cls:
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )

            result = await generate_observation(session, uuid.uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_no_entities_assigned_returns_none(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[]
            )

            result = await generate_observation(session, config_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_no_active_entities_returns_none(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True

        mock_mapping = MagicMock()
        mock_mapping.entity_id = uuid.uuid4()
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.is_active = False

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ),
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )

            result = await generate_observation(session, config_id)
            assert result is None

    @pytest.mark.asyncio
    async def test_no_image_provided_raises(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "test"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "test_entity"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id

        mock_state_def = MagicMock()
        mock_state_def.name = "open"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            with pytest.raises(ValueError, match="Either image_url or image file"):
                await generate_observation(session, config_id)

    @pytest.mark.asyncio
    async def test_empty_image_bytes_raises(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "test"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "test_entity"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id

        mock_state_def = MagicMock()
        mock_state_def.name = "open"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            with pytest.raises(ValueError, match="empty"):
                await generate_observation(session, config_id, image_bytes=b"")

    @pytest.mark.asyncio
    async def test_successful_observation_with_image_bytes(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "Kitchen camera"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}

        state_id_on = uuid.uuid4()
        state_id_off = uuid.uuid4()

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "oven_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = state_id_off

        mock_state_def_on = MagicMock()
        mock_state_def_on.id = state_id_on
        mock_state_def_on.name = "on"
        mock_state_def_off = MagicMock()
        mock_state_def_off.id = state_id_off
        mock_state_def_off.name = "off"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "oven"
        mock_entity_type.display_name = "Oven"

        llm_result = {
            "result": {"oven_1": {"state": "on", "confidence": 0.95}},
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
            patch(
                "services.vision_observation_service._implementation.create_monitoring_llm_provider",
                return_value=mock_llm_provider,
            ),
            patch(
                "services.vision_observation_service._implementation.asyncio.to_thread",
                side_effect=_sync_to_thread,
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_entity_repo_cls.return_value.update = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def_on, mock_state_def_off]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            result = await generate_observation(
                session, config_id, image_bytes=b"fake-image-data"
            )

            assert result is not None
            assert result.camera_id == config_id
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].entity_name == "oven_1"
            assert result.entity_observations[0].state == "on"
            assert result.entity_observations[0].state_id == state_id_on
            assert result.entity_observations[0].confidence == 0.95
            assert result.entity_observations[0].entity_id == entity_id
            assert result.raw_llm_response == {
                "oven_1": {"state": "on", "confidence": 0.95}
            }
            assert result.token_usage == {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "observed": True,
                "image_relevant": True,
            }
            mock_entity_repo_cls.return_value.update.assert_awaited_once_with(
                entity_id,
                current_state_id=state_id_on,
                current_state_since=result.observed_at,
            )

    @pytest.mark.asyncio
    async def test_successful_observation_with_image_url(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = ""
        mock_config.llm_provider = "google"
        mock_config.llm_model = "gemini-2.0-flash"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        state_id_open = uuid.uuid4()
        state_id_closed = uuid.uuid4()

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "door_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = state_id_open

        mock_state_def = MagicMock()
        mock_state_def.id = state_id_open
        mock_state_def.name = "open"
        mock_state_def_closed = MagicMock()
        mock_state_def_closed.id = state_id_closed
        mock_state_def_closed.name = "closed"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        llm_result = {
            "result": {"door_1": {"state": "closed", "confidence": 0.88}},
            "token_usage": {"prompt_tokens": 80, "completion_tokens": 15},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        fake_image_bytes = b"fake-s3-image-content"

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
            patch(
                "services.vision_observation_service._implementation._fetch_s3_bytes",
                AsyncMock(return_value=fake_image_bytes),
            ),
            patch(
                "services.vision_observation_service._implementation.create_monitoring_llm_provider",
                return_value=mock_llm_provider,
            ),
            patch(
                "services.vision_observation_service._implementation.asyncio.to_thread",
                side_effect=_sync_to_thread,
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_entity_repo_cls.return_value.update = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def, mock_state_def_closed]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            result = await generate_observation(
                session, config_id, image_url="cameras/test/frame.jpg"
            )

            assert result is not None
            assert result.camera_id == config_id
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].state == "closed"
            assert result.entity_observations[0].state_id == state_id_closed
            assert result.entity_observations[0].confidence == 0.88

    @pytest.mark.asyncio
    async def test_reference_images_loaded(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "test"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = [
            {"url": "ref/img1.jpg", "description": "Reference 1"},
            {"url": "ref/img2.jpg", "description": "Reference 2"},
        ]

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "entity_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = None

        mock_state_def = MagicMock()
        mock_state_def.id = uuid.uuid4()
        mock_state_def.name = "normal"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "zone"
        mock_entity_type.display_name = "Zone"

        llm_result = {
            "result": {"entity_1": {"state": "normal", "confidence": 0.9}},
            "token_usage": {},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        ref_image_bytes = b"reference-image-bytes"

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
            patch(
                "services.vision_observation_service._implementation._fetch_s3_bytes",
                AsyncMock(return_value=ref_image_bytes),
            ),
            patch(
                "services.vision_observation_service._implementation.create_monitoring_llm_provider",
                return_value=mock_llm_provider,
            ),
            patch(
                "services.vision_observation_service._implementation.asyncio.to_thread",
                side_effect=_sync_to_thread,
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_entity_repo_cls.return_value.update = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            result = await generate_observation(
                session, config_id, image_bytes=b"camera-frame"
            )

            assert result is not None
            assert result.camera_id == config_id
            assert len(result.entity_observations) == 1

    @pytest.mark.asyncio
    async def test_unknown_entity_in_response_skipped(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = ""
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "light_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = None

        mock_state_def = MagicMock()
        mock_state_def.id = uuid.uuid4()
        mock_state_def.name = "on"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "light"
        mock_entity_type.display_name = "Light"

        llm_result = {
            "result": {
                "light_1": {"state": "on", "confidence": 0.99},
                "unknown_entity": {"state": "active", "confidence": 0.5},
            },
            "token_usage": {},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityRepository"
            ) as mock_entity_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionEntityTypeRepository"
            ) as mock_type_repo_cls,
            patch("services.vision_observation_service._implementation.init_s3"),
            patch(
                "services.vision_observation_service._implementation.create_monitoring_llm_provider",
                return_value=mock_llm_provider,
            ),
            patch(
                "services.vision_observation_service._implementation.asyncio.to_thread",
                side_effect=_sync_to_thread,
            ),
        ):
            mock_config_repo_cls.return_value.get_by_signal_source = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_entity_repo_cls.return_value.update = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )

            result = await generate_observation(
                session, config_id, image_bytes=b"frame-data"
            )

            assert result is not None
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].entity_name == "light_1"


async def _sync_to_thread(func, *args, **kwargs):
    """Mock for asyncio.to_thread that calls the function synchronously."""
    return func(*args, **kwargs)
