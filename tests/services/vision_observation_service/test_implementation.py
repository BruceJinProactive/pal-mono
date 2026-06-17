"""Tests for vision observation service implementation."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.vision_observation_service._implementation import (
    _build_entity_state_schema,
    _build_system_prompt,
    _extract_camera_name_from_s3_key,
    _format_roi_hint,
    _is_legacy_observation,
    _state_definition_type,
    generate_observation,
    get_configuration_prompt,
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

    def test_entity_states_grouped_by_definition_type(self):
        entities = [
            {
                "name": "table_1",
                "state_definition_groups": {
                    "cleanliness": {
                        "state_names": ["clean", "dirty"],
                        "state_criteria": {},
                    },
                    "occupation": {
                        "state_names": ["occupied", "empty"],
                        "state_criteria": {},
                    },
                },
            },
        ]
        schema = _build_entity_state_schema(entities)

        table_schema = schema["properties"]["table_1"]
        assert set(table_schema["required"]) == {"cleanliness", "occupation"}
        assert table_schema["properties"]["cleanliness"]["properties"]["state"][
            "enum"
        ] == ["clean", "dirty"]
        assert table_schema["properties"]["occupation"]["properties"]["state"][
            "enum"
        ] == ["occupied", "empty"]


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


class TestLegacyObservationParsing:

    def test_top_level_state_without_marker_is_not_legacy(self):
        assert _is_legacy_observation({"state": "clean", "confidence": 0.9}) is False

    def test_explicit_legacy_marker_is_legacy(self):
        assert (
            _is_legacy_observation(
                {"definition_type": "state", "state": "clean", "confidence": 0.9}
            )
            is True
        )


class TestStateDefinitionType:

    def test_missing_or_blank_definition_type_returns_none(self):
        missing_type = MagicMock()
        missing_type.definition_type = None
        blank_type = MagicMock()
        blank_type.definition_type = "  "

        assert _state_definition_type(missing_type) is None
        assert _state_definition_type(blank_type) is None


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

    def test_groups_state_options_by_definition_type(self):
        state_definition_groups = {
            "cleanliness": {
                "state_names": ["clean", "dirty"],
                "state_criteria": {"dirty": "dishes or trash are visible"},
            },
            "occupation": {
                "state_names": ["occupied", "empty"],
                "state_criteria": {"occupied": "a customer is seated"},
            },
        }
        entity_type_defs = {
            "table": {
                "display_name": "Table",
                "state_definition_groups": state_definition_groups,
            },
        }
        entities = [
            {
                "name": "Table 1",
                "type_name": "table",
                "state_definition_groups": state_definition_groups,
                "state_names": ["clean", "dirty", "occupied", "empty"],
                "roi_hint": None,
            },
        ]

        prompt = _build_system_prompt("", entity_type_defs, entities)

        assert "State definition types (pick one state in each type):" in prompt
        assert (
            '- cleanliness: "clean" | "dirty" (dishes or trash are visible)' in prompt
        )
        assert '- occupation: "occupied" (a customer is seated) | "empty"' in prompt


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
        mock_state_def.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        llm_result = {
            "result": {"door_1": {"cleanliness": {"state": "open", "confidence": 0.9}}},
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
            patch(
                "services.vision_observation_service._implementation.logger.warning"
            ) as mock_warning,
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
            image_url = "cameras/my-kitchen-cam/frame.jpg"
            result = await generate_observation(session, camera_id, image_url=image_url)

            assert result is not None
            assert result.camera_id == camera_id
            assert len(result.entity_observations) == 1
            mock_config_repo_cls.return_value.get_by_name.assert_awaited_once_with(
                "my-kitchen-cam"
            )
            mock_warning.assert_any_call(
                "[Vision Observation] Image filename does not include UTC capture "
                "timestamp; falling back to processing time",
                extra={
                    "camera_id": str(camera_id),
                    "config_id": str(config_id),
                    "image_url": image_url,
                    "expected_format": "snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS.jpg",
                },
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
        mock_state_def.definition_type = "cleanliness"

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
        mock_state_def.definition_type = "cleanliness"

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
        mock_entity.entity_metadata = {}

        mock_state_def_on = MagicMock()
        mock_state_def_on.id = state_id_on
        mock_state_def_on.name = "on"
        mock_state_def_on.definition_type = "cleanliness"
        mock_state_def_off = MagicMock()
        mock_state_def_off.id = state_id_off
        mock_state_def_off.name = "off"
        mock_state_def_off.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "oven"
        mock_entity_type.display_name = "Oven"

        llm_result = {
            "result": {"oven_1": {"cleanliness": {"state": "on", "confidence": 0.95}}},
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result
        image_url = (
            "security/cameras/account/project/chica-cam-08/videos/"
            "2026-02-13/2026-02-12_16-51-55.mkv"
        )
        observed_at = datetime(2026, 2, 12, 16, 52, 25, tzinfo=timezone.utc)

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
            patch(
                "services.vision_observation_service._implementation.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
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

            async def update_entity(
                entity_id_arg: uuid.UUID, **kwargs: object
            ) -> MagicMock:
                assert entity_id_arg == entity_id
                for key, value in kwargs.items():
                    setattr(mock_entity, key, value)
                return mock_entity

            mock_entity_repo_cls.return_value.update = AsyncMock(
                side_effect=update_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[mock_state_def_on, mock_state_def_off]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )
            mock_event_repo_cls.return_value.create = AsyncMock()

            result = await generate_observation(
                session,
                config_id,
                image_url=image_url,
                image_bytes=b"fake-image-data",
                observed_at=observed_at,
            )

            assert result is not None
            assert result.camera_id == config_id
            assert result.observed_at == observed_at
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].entity_name == "oven_1"
            assert result.entity_observations[0].state == "on"
            assert result.entity_observations[0].state_id == state_id_on
            assert result.entity_observations[0].confidence == 0.95
            assert result.entity_observations[0].entity_id == entity_id
            assert result.raw_llm_response == {
                "oven_1": {"cleanliness": {"state": "on", "confidence": 0.95}}
            }
            assert result.token_usage == {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "observed": True,
                "image_relevant": True,
            }
            update_args = mock_entity_repo_cls.return_value.update.await_args
            assert update_args is not None
            update_kwargs = update_args.kwargs
            assert update_kwargs["current_state_id"] == state_id_on
            assert update_kwargs["current_state_since"] == result.observed_at
            assert update_kwargs["entity_metadata"] == {
                "current_states": {
                    "cleanliness": {
                        "state_definition_id": str(state_id_on),
                        "state": "on",
                        "current_state_since": result.observed_at.isoformat(),
                        "observed_at": result.observed_at.isoformat(),
                        "confidence": 0.95,
                    }
                }
            }
            event_create_args = mock_event_repo_cls.return_value.create.await_args
            assert event_create_args is not None
            event = event_create_args.args[0]
            assert event.observed_at == observed_at
            assert event.frame_s3_key == image_url

    @pytest.mark.asyncio
    async def test_observation_skips_when_current_metadata_matches(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_id_on = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "Kitchen camera"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "oven_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = state_id_on
        mock_entity.current_state_since = None
        mock_entity.entity_metadata = {
            "current_states": {
                "cleanliness": {
                    "state_definition_id": str(state_id_on),
                    "state": "on",
                    "current_state_since": "2026-06-01T12:00:00+00:00",
                    "observed_at": "2026-06-01T12:00:00+00:00",
                }
            }
        }

        mock_state_def_on = MagicMock()
        mock_state_def_on.id = state_id_on
        mock_state_def_on.name = "on"
        mock_state_def_on.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "oven"
        mock_entity_type.display_name = "Oven"

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = {
            "result": {"oven_1": {"cleanliness": {"state": "on", "confidence": 0.95}}},
            "token_usage": {},
        }

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
            patch(
                "services.vision_observation_service._implementation.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
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
                return_value=[mock_state_def_on]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )
            mock_event_repo_cls.return_value.create = AsyncMock()

            await generate_observation(session, config_id, image_bytes=b"frame")

            mock_entity_repo_cls.return_value.update.assert_not_awaited()
            mock_event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_observation_backfills_missing_metadata_without_event(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_id_on = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "Kitchen camera"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        current_state_since = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "oven_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = state_id_on
        mock_entity.current_state_since = current_state_since
        mock_entity.entity_metadata = {}

        mock_state_def_on = MagicMock()
        mock_state_def_on.id = state_id_on
        mock_state_def_on.name = "on"
        mock_state_def_on.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "oven"
        mock_entity_type.display_name = "Oven"

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = {
            "result": {"oven_1": {"cleanliness": {"state": "on", "confidence": 0.95}}},
            "token_usage": {},
        }

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
            patch(
                "services.vision_observation_service._implementation.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
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
                return_value=[mock_state_def_on]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )
            mock_event_repo_cls.return_value.create = AsyncMock()

            await generate_observation(session, config_id, image_bytes=b"frame")

            update_args = mock_entity_repo_cls.return_value.update.await_args
            assert update_args is not None
            update_kwargs = update_args.kwargs
            assert update_kwargs["entity_metadata"]["current_states"]["cleanliness"][
                "state_definition_id"
            ] == str(state_id_on)
            mock_event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_observation_uses_active_state_definitions_grouped_by_type(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.llm_prompt = "Watch tables"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "table_1"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id
        mock_entity.current_state_id = None
        mock_entity.entity_metadata = {}

        clean_id = uuid.uuid4()
        occupied_id = uuid.uuid4()
        clean_state = MagicMock()
        clean_state.id = clean_id
        clean_state.name = "clean"
        clean_state.definition_type = "cleanliness"
        occupied_state = MagicMock()
        occupied_state.id = occupied_id
        occupied_state.name = "occupied"
        occupied_state.definition_type = "occupation"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "table"
        mock_entity_type.display_name = "Table"

        llm_result = {
            "result": {
                "table_1": {
                    "cleanliness": {"state": "clean", "confidence": 0.9},
                    "occupation": {"state": "occupied", "confidence": 0.8},
                },
                "image_relevant": True,
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
            patch(
                "services.vision_observation_service._implementation.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
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

            async def update_entity(
                entity_id_arg: uuid.UUID, **kwargs: object
            ) -> MagicMock:
                assert entity_id_arg == entity_id
                for key, value in kwargs.items():
                    setattr(mock_entity, key, value)
                return mock_entity

            mock_entity_repo_cls.return_value.update = AsyncMock(
                side_effect=update_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[clean_state, occupied_state]
            )
            mock_type_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity_type
            )
            mock_event_repo_cls.return_value.create = AsyncMock()

            result = await generate_observation(
                session, config_id, image_bytes=b"frame-data"
            )

            assert result is not None
            assert [
                (obs.definition_type, obs.state, obs.state_id, obs.confidence)
                for obs in result.entity_observations
            ] == [
                ("cleanliness", "clean", clean_id, 0.9),
                ("occupation", "occupied", occupied_id, 0.8),
            ]
            mock_sd_repo_cls.return_value.list_by_entity_type.assert_awaited_once_with(
                entity_type_id, is_active=True
            )
            assert mock_entity_repo_cls.return_value.update.await_count == 2
            assert mock_entity.entity_metadata == {
                "current_states": {
                    "cleanliness": {
                        "state_definition_id": str(clean_id),
                        "state": "clean",
                        "current_state_since": result.observed_at.isoformat(),
                        "observed_at": result.observed_at.isoformat(),
                        "confidence": 0.9,
                    },
                    "occupation": {
                        "state_definition_id": str(occupied_id),
                        "state": "occupied",
                        "current_state_since": result.observed_at.isoformat(),
                        "observed_at": result.observed_at.isoformat(),
                        "confidence": 0.8,
                    },
                }
            }
            assert mock_event_repo_cls.return_value.create.await_count == 2
            event_definition_types = [
                call.args[0].event_metadata["definition_type"]
                for call in mock_event_repo_cls.return_value.create.await_args_list
            ]
            assert event_definition_types == ["cleanliness", "occupation"]

    @pytest.mark.asyncio
    async def test_successful_observation_with_image_url(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
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
        mock_entity.current_state_since = None
        mock_entity.entity_metadata = {}

        mock_state_def = MagicMock()
        mock_state_def.id = state_id_open
        mock_state_def.name = "open"
        mock_state_def.definition_type = "cleanliness"
        mock_state_def_closed = MagicMock()
        mock_state_def_closed.id = state_id_closed
        mock_state_def_closed.name = "closed"
        mock_state_def_closed.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "door"
        mock_entity_type.display_name = "Door"

        llm_result = {
            "result": {
                "door_1": {"cleanliness": {"state": "closed", "confidence": 0.88}}
            },
            "token_usage": {"prompt_tokens": 80, "completion_tokens": 15},
        }

        mock_llm_provider = MagicMock()
        mock_llm_provider.analyze_image.return_value = llm_result

        fake_image_bytes = b"fake-s3-image-content"
        image_url = (
            "security/cameras/account/project/chica-cam-08/images/"
            "2026-06-09/2026-06-09_18-51-35.jpg"
        )
        expected_observed_at = datetime(2026, 6, 9, 18, 51, 35, tzinfo=timezone.utc)

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
            patch(
                "services.vision_observation_service._implementation.VisionStateChangeEventRepository"
            ) as mock_event_repo_cls,
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
            mock_event_repo_cls.return_value.create = AsyncMock()

            result = await generate_observation(session, config_id, image_url=image_url)

            assert result is not None
            assert result.camera_id == config_id
            assert result.observed_at == expected_observed_at
            assert len(result.entity_observations) == 1
            assert result.entity_observations[0].state == "closed"
            assert result.entity_observations[0].state_id == state_id_closed
            assert result.entity_observations[0].confidence == 0.88
            event_create_args = mock_event_repo_cls.return_value.create.await_args
            assert event_create_args is not None
            event = event_create_args.args[0]
            assert event.observed_at == expected_observed_at
            assert event.frame_s3_key == image_url

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
        mock_state_def.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "zone"
        mock_entity_type.display_name = "Zone"

        llm_result = {
            "result": {
                "entity_1": {"cleanliness": {"state": "normal", "confidence": 0.9}}
            },
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
        mock_state_def.definition_type = "cleanliness"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "light"
        mock_entity_type.display_name = "Light"

        llm_result = {
            "result": {
                "light_1": {"cleanliness": {"state": "on", "confidence": 0.99}},
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


class TestGetConfigurationPrompt:
    """Tests for getting the full system prompt for a camera configuration."""

    @pytest.mark.asyncio
    async def test_config_not_found_returns_none(self):
        session = AsyncMock()

        with patch(
            "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
        ) as mock_config_repo_cls:
            mock_config_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)

            result = await get_configuration_prompt(session, uuid.uuid4())
            assert result is None

    @pytest.mark.asyncio
    async def test_no_entities_returns_prompt_with_user_context(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.llm_prompt = "Monitor the parking lot"
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = [
            {"url": "vision/ref/img1.jpg", "description": "Empty lot"},
        ]

        with (
            patch(
                "services.vision_observation_service._implementation.VisionCameraConfigurationRepository"
            ) as mock_config_repo_cls,
            patch(
                "services.vision_observation_service._implementation.VisionCameraEntityRepository"
            ) as mock_mapping_repo_cls,
        ):
            mock_config_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[]
            )

            result = await get_configuration_prompt(session, config_id)
            assert result is not None
            assert result.llm_provider == "azure"
            assert result.llm_model == "gpt-4o"
            assert "Monitor the parking lot" in result.system_prompt
            assert result.structured_output["type"] == "object"
            assert "image_relevant" in result.structured_output["properties"]

    @pytest.mark.asyncio
    async def test_returns_full_prompt_with_entities(self):
        session = AsyncMock()
        config_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.llm_prompt = "Watch the gate"
        mock_config.llm_provider = "google"
        mock_config.llm_model = "gemini-2.0-flash"
        mock_config.reference_images = [
            {"url": "vision/ref/gate_open.jpg", "description": "Gate fully open"},
            {"url": "vision/ref/gate_closed.jpg", "description": "Gate closed"},
        ]

        mock_mapping = MagicMock()
        mock_mapping.entity_id = entity_id
        mock_mapping.roi_hint = {"x": 100, "y": 200, "width": 300, "height": 400}

        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "main_gate"
        mock_entity.is_active = True
        mock_entity.entity_type_id = entity_type_id

        mock_state_def = MagicMock()
        mock_state_def.id = uuid.uuid4()
        mock_state_def.name = "open"
        mock_state_def.definition_type = "cleanliness"
        mock_state_def.criteria = "gate is raised"

        mock_entity_type = MagicMock()
        mock_entity_type.name = "gate"
        mock_entity_type.display_name = "Gate"

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
        ):
            mock_config_repo_cls.return_value.get_by_id = AsyncMock(
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

            result = await get_configuration_prompt(session, config_id)
            assert result is not None
            assert result.llm_provider == "google"
            assert result.llm_model == "gemini-2.0-flash"
            assert "Watch the gate" in result.system_prompt
            assert '"main_gate"' in result.system_prompt
            assert "Gate" in result.system_prompt
            assert "ROI: [100, 200, 300, 400]" in result.system_prompt
            assert '"open"' in result.system_prompt
            assert "main_gate" in result.structured_output["properties"]
            assert result.structured_output["properties"]["main_gate"]["properties"][
                "cleanliness"
            ]["properties"]["state"]["enum"] == ["open"]
            mock_sd_repo_cls.return_value.list_by_entity_type.assert_awaited_once_with(
                entity_type_id, is_active=True
            )

    @pytest.mark.asyncio
    async def test_skips_inactive_entities(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.llm_prompt = ""
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = uuid.uuid4()
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = mock_mapping.entity_id
        mock_entity.name = "inactive_door"
        mock_entity.is_active = False
        mock_entity.entity_type_id = uuid.uuid4()

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
            mock_config_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )

            result = await get_configuration_prompt(session, config_id)
            assert result is not None
            assert "inactive_door" not in result.system_prompt

    @pytest.mark.asyncio
    async def test_skips_entities_with_no_state_defs(self):
        session = AsyncMock()
        config_id = uuid.uuid4()

        mock_config = MagicMock()
        mock_config.id = config_id
        mock_config.llm_prompt = ""
        mock_config.llm_provider = "azure"
        mock_config.llm_model = "gpt-4o"
        mock_config.reference_images = None

        mock_mapping = MagicMock()
        mock_mapping.entity_id = uuid.uuid4()
        mock_mapping.roi_hint = None

        mock_entity = MagicMock()
        mock_entity.id = mock_mapping.entity_id
        mock_entity.name = "no_states_entity"
        mock_entity.is_active = True
        mock_entity.entity_type_id = uuid.uuid4()

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
            ),
        ):
            mock_config_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_config
            )
            mock_mapping_repo_cls.return_value.list_by_camera = AsyncMock(
                return_value=[mock_mapping]
            )
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(
                return_value=mock_entity
            )
            mock_sd_repo_cls.return_value.list_by_entity_type = AsyncMock(
                return_value=[]
            )

            result = await get_configuration_prompt(session, config_id)
            assert result is not None
            assert "no_states_entity" not in result.system_prompt
            assert result.entities_with_states == []


async def _sync_to_thread(func, *args, **kwargs):
    """Mock for asyncio.to_thread that calls the function synchronously."""
    return func(*args, **kwargs)
