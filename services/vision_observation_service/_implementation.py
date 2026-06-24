from __future__ import annotations

import ast
import asyncio
import base64
import uuid
from collections.abc import Mapping
from dataclasses import is_dataclass, replace
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_observation import (
    EntityObservation,
    GenerateObservationResponse,
)
from db.pal_repository import (
    VisionCameraConfigurationRepository,
    VisionCameraEntityRepository,
    VisionEntityRepository,
    VisionEntityStateDefinitionRepository,
    VisionEntityTypeRepository,
    VisionRuleRepository,
    VisionStateChangeEventRepository,
)
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.asset_service._constants import AWS_REGION
from services.asset_service._utils import AWS_ASSET_BUCKET_NAME, init_s3
from services.monitoring_service._providers import (
    MonitoringLLMConfig,
    MonitoringLLMProvider,
    create_monitoring_llm_provider,
)
from services.vision_observation_service._roi_overlay import (
    draw_roi_labels_on_image_bytes as _draw_roi_labels_on_image_bytes,
)
from services.vision_observation_service._roi_overlay import (
    roi_hint_value as _roi_hint_value,
)
from services.vision_observation_service._smoothing import (
    EventGenerationConfig,
    SmoothingDecision,
    SmoothingObservation,
    is_smoothing_enabled,
    parse_event_generation_config,
    single_frame_event_generation_config,
)
from services.vision_observation_service._smoothing_cache import (
    acquire_smoothing_cache_buffer,
)
from services.vision_observation_service._workflow import (
    RULE_TYPE_WORKFLOWS,
    handle_state_change_rules,
)
from services.vision_state_metadata import (
    LEGACY_CURRENT_STATE_TYPE,
    current_state_id_from_metadata,
    current_state_metadata_key,
    current_state_observed_at_from_metadata,
    get_current_states_metadata,
    set_current_state_metadata,
)
from utils.log import logger
from utils.vision_capture_time import parse_utc_capture_time_from_path

_MAX_LLM_IMAGE_DIMENSION = 4096
_MIN_LLM_IMAGE_DIMENSION = 10
_MIN_LLM_IMAGE_BYTES = 100


async def _fetch_s3_bytes(s3_client: Any, key: str) -> bytes:
    response = await asyncio.to_thread(
        s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=key
    )
    return await asyncio.to_thread(response["Body"].read)


def _normalize_image_bytes_for_llm(image_bytes: bytes, image_label: str) -> bytes:
    if not image_bytes:
        raise ValueError(f"{image_label} bytes are empty (0 bytes)")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            pil_image = ImageOps.exif_transpose(image)
            width, height = pil_image.size
            if width < _MIN_LLM_IMAGE_DIMENSION or height < _MIN_LLM_IMAGE_DIMENSION:
                raise ValueError(
                    f"{image_label} is too small for LLM processing "
                    f"({width}x{height})"
                )

            if width > _MAX_LLM_IMAGE_DIMENSION or height > _MAX_LLM_IMAGE_DIMENSION:
                logger.warning(
                    "[Vision Observation] Image too large, resizing before LLM",
                    extra={
                        "image_label": image_label,
                        "width": width,
                        "height": height,
                        "max_dimension": _MAX_LLM_IMAGE_DIMENSION,
                    },
                )
                pil_image.thumbnail(
                    (_MAX_LLM_IMAGE_DIMENSION, _MAX_LLM_IMAGE_DIMENSION),
                    Image.Resampling.LANCZOS,
                )

            image_mode = getattr(pil_image, "mode", "RGB")
            if isinstance(image_mode, str) and image_mode != "RGB":
                pil_image = pil_image.convert("RGB")

            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=85)
            normalized_bytes = buffer.getvalue()

        if len(normalized_bytes) < _MIN_LLM_IMAGE_BYTES:
            raise ValueError(
                f"{image_label} produced a suspiciously small JPEG "
                f"({len(normalized_bytes)} bytes)"
            )

        Image.open(BytesIO(normalized_bytes)).verify()
        return normalized_bytes
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"{image_label} is not a valid processable image") from e


def _build_state_observation_schema(state_names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "Briefly explain the visible cues used for this state."
                ),
            },
            "state": {
                "type": "string",
                "enum": state_names,
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["reason", "state", "confidence"],
        "additionalProperties": False,
    }


def _build_entity_state_schema(
    entities_with_states: list[dict[str, Any]],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}

    for entity_info in entities_with_states:
        entity_name = entity_info["name"]
        state_definition_groups = entity_info.get("state_definition_groups", {})

        if state_definition_groups:
            group_properties: dict[str, Any] = {}
            for definition_type, group_info in state_definition_groups.items():
                group_properties[definition_type] = _build_state_observation_schema(
                    group_info["state_names"]
                )

            properties[entity_name] = {
                "type": "object",
                "properties": group_properties,
                "required": list(group_properties.keys()),
                "additionalProperties": False,
            }
            continue

        state_names = entity_info["state_names"]
        properties[entity_name] = _build_state_observation_schema(state_names)

    properties["image_relevant"] = {
        "type": "boolean",
    }

    required_keys = list(properties.keys())

    return {
        "type": "object",
        "properties": properties,
        "required": required_keys,
        "additionalProperties": False,
    }


def _state_definition_type(state_def: Any) -> str | None:
    definition_type = getattr(state_def, "definition_type", None)
    if isinstance(definition_type, str) and definition_type.strip():
        return definition_type.strip()
    return None


def _state_definition_group_key(state_def: Any) -> str:
    return current_state_metadata_key(_state_definition_type(state_def))


def _state_definition_criteria(state_def: Any) -> str | None:
    criteria = getattr(state_def, "criteria", None)
    if isinstance(criteria, str) and criteria.strip():
        return criteria.strip()
    return None


def _build_state_definition_groups(
    state_defs: list[Any],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for state_def in state_defs:
        definition_type = _state_definition_group_key(state_def)
        group = groups.setdefault(
            definition_type,
            {
                "state_names": [],
                "state_criteria": {},
            },
        )
        state_name = state_def.name
        group["state_names"].append(state_name)
        criteria = _state_definition_criteria(state_def)
        if criteria:
            group["state_criteria"][state_name] = criteria
    return groups


def _is_legacy_observation(observation: dict[str, Any]) -> bool:
    definition_type = observation.get("definition_type")
    return (
        observation.get("legacy") is True
        or observation.get("is_legacy") is True
        or observation.get("format") == "legacy"
        or definition_type == LEGACY_CURRENT_STATE_TYPE
    )


def _is_unprocessable_image_error(error: Exception) -> bool:
    message = str(error).lower()
    return "unable to process input image" in message


def _gemini_refusal_reason(error: Exception) -> str:
    message = str(error)
    payload_start = message.find("{")
    if payload_start >= 0:
        try:
            payload = ast.literal_eval(message[payload_start:])
        except (SyntaxError, ValueError):
            payload = None
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                reason = error_payload.get("message")
                if isinstance(reason, str) and reason.strip():
                    return reason.strip()
    return message


def _format_roi_hint(roi_hint: dict[str, object] | None) -> str | None:
    if not roi_hint:
        return None

    x = _roi_hint_value(roi_hint, "x")
    y = _roi_hint_value(roi_hint, "y")
    w = _roi_hint_value(roi_hint, "width")
    h = _roi_hint_value(roi_hint, "height")
    if x is None or y is None or w is None or h is None:
        return None

    values = (x, y, w, h)
    if all(0 <= value <= 1 for value in values):
        values = tuple(value * 1000 for value in values)

    x_text, y_text, w_text, h_text = (int(value) for value in values)
    return f"[{x_text}, {y_text}, {w_text}, {h_text}]"


def _entities_include_state(
    entities_with_states: list[dict[str, Any]], state_name: str
) -> bool:
    for entity_info in entities_with_states:
        if state_name in entity_info.get("state_names", []):
            return True
        for group_info in entity_info.get("state_definition_groups", {}).values():
            if state_name in group_info.get("state_names", []):
                return True
    return False


def _build_system_prompt(
    user_prompt: str,
    entity_type_definitions: dict[str, dict[str, Any]],
    entities_with_states: list[dict[str, Any]],
) -> str:
    lines: list[str] = [
        "You are a visual monitoring assistant analyzing a camera frame "
        "to determine the current state of entities in the monitored environment.",
        "",
        "For each entity, select exactly ONE state from its allowed states "
        "for each state definition type based on what you see in the image.",
        "",
        "Rules:",
        "- Only use active state definitions listed for each entity",
        "- Judge each state definition type independently",
        "- If you cannot clearly determine a state, pick the most likely one "
        "for that type and reflect that in your confidence score",
        "- Confidence should be 0.0-1.0 where 1.0 means absolute certainty",
        "- If an entity is not visible in the frame at all, use confidence 0.0 "
        "and pick the most reasonable default state",
        "- Set image_relevant to false if the camera image is completely "
        "irrelevant to the reference images or the monitored environment "
        "(e.g. a broken feed, black screen, unrelated scene). "
        "Otherwise set image_relevant to true",
        "- For every entity and state definition type, write reason first: "
        "a concise image-grounded explanation for the selected state",
        "- ROI coordinates are normalized [x, y, width, height] (scale 0-1000); "
        "the same ROI may also be drawn as a labeled box on the image",
        "- Box colors are visual aids only; identify entities by the box label text, "
        "not by color semantics",
        "- Use ROI coordinates and labels as entity identity anchors, not hard "
        "segmentation masks. Consider people or objects just outside the box "
        "when posture, contact, gaze, or scene context ties them to that entity",
        "- For table-like entities, reason by seating, body orientation, gaze, "
        "hands, chairs, table contact, and nearby context rather than proximity "
        "alone",
    ]

    if _entities_include_state(entities_with_states, "dishes-present"):
        lines.append(
            "- The dishes-present state means active dining or dirty/used "
            "tableware on the relevant table; do not count clean preset "
            "tableware, decorations, signage, or unrelated objects"
        )

    if user_prompt:
        lines.append("")
        lines.append("Context:")
        lines.append(user_prompt)

    lines.append("")
    lines.append("Entities to Observe:")

    entities_by_type: dict[str, list[dict[str, Any]]] = {}
    for entity_info in entities_with_states:
        type_name = entity_info["type_name"]
        if type_name not in entities_by_type:
            entities_by_type[type_name] = []
        entities_by_type[type_name].append(entity_info)

    for type_name, entities in entities_by_type.items():
        type_info = entity_type_definitions.get(type_name, {})
        display = type_info.get("display_name", type_name)
        state_definition_groups = type_info.get("state_definition_groups", {})
        state_criteria = type_info.get("state_criteria", {})
        state_names = type_info.get("state_names", [])

        lines.append("")
        lines.append(display)

        if state_definition_groups:
            lines.append("  State definition types (pick one state in each type):")
            for definition_type, group_info in state_definition_groups.items():
                states_parts: list[str] = []
                for state_name in group_info["state_names"]:
                    criteria = group_info["state_criteria"].get(state_name)
                    if criteria:
                        states_parts.append(f'"{state_name}" ({criteria})')
                    else:
                        states_parts.append(f'"{state_name}"')
                lines.append(f"  - {definition_type}: {' | '.join(states_parts)}")
        else:
            states_parts = []
            for state_name in state_names:
                criteria = state_criteria.get(state_name)
                if criteria:
                    states_parts.append(f'"{state_name}" ({criteria})')
                else:
                    states_parts.append(f'"{state_name}"')
            lines.append(f"  States (pick one): {' | '.join(states_parts)}")

        for entity_info in entities:
            roi_text = _format_roi_hint(entity_info.get("roi_hint"))
            if roi_text:
                lines.append(f'  - "{entity_info["name"]}" — ROI: {roi_text}')
            else:
                lines.append(f'  - "{entity_info["name"]}"')

    lines.append("")
    lines.append("Respond ONLY with valid JSON matching the provided schema.")

    return "\n".join(lines)


def _extract_camera_name_from_s3_key(image_url: str) -> str | None:
    parts = image_url.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "cameras":
        return parts[1]
    return None


def _parse_metadata_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _parse_metadata_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            if value.tzinfo
            else value.replace(tzinfo=timezone.utc)
        )
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return (
            parsed.astimezone(timezone.utc)
            if parsed.tzinfo
            else parsed.replace(tzinfo=timezone.utc)
        )
    return None


def _current_state_for_definition(
    entity_metadata: dict[str, object],
    definition_type: str,
) -> Mapping[str, object] | None:
    current_state = get_current_states_metadata(entity_metadata).get(definition_type)
    return current_state if isinstance(current_state, Mapping) else None


def _metadata_state_matches_decision(
    current_state: Mapping[str, object],
    decision: SmoothingDecision,
) -> bool:
    return (
        _parse_metadata_uuid(current_state.get("state_definition_id"))
        == decision.state_id
        and _parse_metadata_datetime(current_state.get("observed_at"))
        == decision.center_observed_at
    )


def _entity_for_recovered_workflow(
    entity: Any,
    entity_metadata: dict[str, object],
    definition_type: str,
    current_state: Mapping[str, object],
) -> Any:
    previous_state_id = _parse_metadata_uuid(
        current_state.get("previous_state_definition_id")
    )
    previous_state_name = current_state.get("previous_state")
    previous_state_since = _parse_metadata_datetime(
        current_state.get("previous_state_since")
    )
    if previous_state_id is None or not isinstance(previous_state_name, str):
        return entity

    previous_metadata = set_current_state_metadata(
        entity_metadata,
        definition_type,
        previous_state_id,
        previous_state_name,
        previous_state_since or datetime.now(timezone.utc),
        previous_state_since or datetime.now(timezone.utc),
        None,
    )
    if is_dataclass(entity) and not isinstance(entity, type):
        return replace(
            entity,
            entity_metadata=previous_metadata,
            current_state_id=previous_state_id,
            current_state_since=previous_state_since,
        )

    return entity


async def _recover_applied_smoothing_decision(
    *,
    session: AsyncSession,
    event_repo: VisionStateChangeEventRepository,
    entity: Any,
    entity_metadata: dict[str, object],
    entity_id: uuid.UUID,
    decision: SmoothingDecision,
    definition_type: str,
    lookup_info: dict[str, Any],
) -> None:
    if (
        decision.state_id is None
        or decision.state is None
        or decision.confidence is None
    ):
        return

    current_state = _current_state_for_definition(entity_metadata, definition_type)
    if current_state is None or not _metadata_state_matches_decision(
        current_state,
        decision,
    ):
        return

    state_change_event = await event_repo.get_by_entity_state_observed_at(
        entity_id=entity_id,
        state_id=decision.state_id,
        observed_at=decision.center_observed_at,
        definition_type=definition_type,
    )
    if state_change_event is None:
        state_change_event = VisionStateChangeEventData(
            id=_parse_metadata_uuid(current_state.get("state_change_event_id"))
            or uuid.uuid4(),
            entity_id=entity_id,
            new_state_id=decision.state_id,
            observed_at=decision.center_observed_at,
            event_metadata={
                "definition_type": definition_type,
                "smoothing": decision.metadata,
            },
            camera_config_id=decision.center_camera_config_id,
            previous_state_id=_parse_metadata_uuid(
                current_state.get("previous_state_definition_id")
            ),
            confidence=decision.confidence,
            frame_s3_key=decision.center_frame_s3_key,
        )
        await event_repo.create(state_change_event)

    previous_state_name = current_state.get("previous_state")
    await handle_state_change_rules(
        session=session,
        entity=_entity_for_recovered_workflow(
            entity,
            entity_metadata,
            definition_type,
            current_state,
        ),
        state_change_event=state_change_event,
        state_name=decision.state,
        previous_state_name=(
            previous_state_name if isinstance(previous_state_name, str) else None
        ),
        entity_type_name=lookup_info["entity_type_name"],
    )


def _select_event_generation_config(
    rules: list[Any],
    entity_type_name: str,
    definition_type: str,
) -> EventGenerationConfig:
    selected = single_frame_event_generation_config()

    for rule in rules:
        workflow = RULE_TYPE_WORKFLOWS.get(rule.type)
        if workflow is None:
            continue
        if workflow.entity_type_name != entity_type_name:
            continue
        if (
            workflow.state_definition_type is not None
            and workflow.state_definition_type != definition_type
        ):
            continue

        event_generation = rule.rule_metadata.get("event_generation")
        config = parse_event_generation_config(event_generation)
        if not is_smoothing_enabled(config):
            continue
        if (
            not is_smoothing_enabled(selected)
            or config.window_frames > selected.window_frames
        ):
            selected = config

    return selected


async def _apply_state_decision(
    session: AsyncSession,
    entity_repo: VisionEntityRepository,
    event_repo: VisionStateChangeEventRepository,
    entity: Any,
    entity_metadata: dict[str, object],
    entity_id: uuid.UUID,
    camera_config_id: uuid.UUID,
    state_id: uuid.UUID,
    state_name: str,
    confidence: float,
    observed_at: datetime,
    frame_s3_key: str | None,
    definition_type: str,
    lookup_info: dict[str, Any],
    event_metadata: dict[str, Any],
    include_recovery_metadata: bool = False,
) -> tuple[Any, dict[str, object]]:
    current_states = get_current_states_metadata(entity_metadata)
    previous_state_id = current_state_id_from_metadata(current_states, definition_type)
    if (
        previous_state_id is None
        and entity.current_state_id is not None
        and lookup_info["state_id_to_definition_type"].get(entity.current_state_id)
        == definition_type
    ):
        previous_state_id = entity.current_state_id

    state_changed = state_id != previous_state_id
    metadata_missing = definition_type not in current_states
    if not state_changed and not metadata_missing:
        return entity, entity_metadata

    previous_state_name = None
    if previous_state_id is not None:
        previous_state_name = lookup_info["state_id_to_name"].get(previous_state_id)
    previous_state_since = None
    previous_current_state = current_states.get(definition_type)
    if isinstance(previous_current_state, Mapping):
        previous_state_since = _parse_metadata_datetime(
            previous_current_state.get("current_state_since")
        )

    current_state_since = (
        observed_at if state_changed else entity.current_state_since or observed_at
    )
    state_change_event = None
    if state_changed:
        state_change_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity_id,
            new_state_id=state_id,
            observed_at=observed_at,
            event_metadata=event_metadata,
            camera_config_id=camera_config_id,
            previous_state_id=previous_state_id,
            confidence=confidence,
            frame_s3_key=frame_s3_key,
        )
    updated_metadata = set_current_state_metadata(
        entity_metadata,
        definition_type,
        state_id,
        state_name,
        current_state_since,
        observed_at,
        confidence,
        state_change_event_id=(
            state_change_event.id
            if state_change_event and include_recovery_metadata
            else None
        ),
        previous_state_id=(
            previous_state_id if state_changed and include_recovery_metadata else None
        ),
        previous_state_name=(
            previous_state_name if state_changed and include_recovery_metadata else None
        ),
        previous_state_since=(
            previous_state_since
            if state_changed and include_recovery_metadata
            else None
        ),
    )
    updates: dict[str, object] = {"entity_metadata": updated_metadata}
    if len(lookup_info["state_name_to_id_by_type"]) == 1:
        updates["current_state_id"] = state_id
        updates["current_state_since"] = current_state_since

    entity_before_update = entity
    updated_entity = await entity_repo.update(entity_id, **updates)
    if updated_entity is not None:
        entity = updated_entity

    if not state_changed:
        return entity, updated_metadata

    assert state_change_event is not None
    await event_repo.create(state_change_event)
    await handle_state_change_rules(
        session=session,
        entity=entity_before_update,
        state_change_event=state_change_event,
        state_name=state_name,
        previous_state_name=previous_state_name,
        entity_type_name=lookup_info["entity_type_name"],
    )
    return entity, updated_metadata


class ConfigurationPromptResult:
    def __init__(
        self,
        llm_provider: str,
        llm_model: str,
        system_prompt: str,
        structured_output: dict[str, Any],
        entities_with_states: list[dict[str, Any]],
    ) -> None:
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.system_prompt = system_prompt
        self.structured_output = structured_output
        self.entities_with_states = entities_with_states


async def get_configuration_prompt(
    session: AsyncSession,
    config_id: uuid.UUID,
) -> ConfigurationPromptResult | None:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_id(config_id)

    if not config:
        return None

    mapping_repo = VisionCameraEntityRepository(session)
    mappings = await mapping_repo.list_by_camera(config.id)
    if not mappings:
        prompt = _build_system_prompt(
            user_prompt=config.llm_prompt,
            entity_type_definitions={},
            entities_with_states=[],
        )
        return ConfigurationPromptResult(
            llm_provider=config.llm_provider,
            llm_model=config.llm_model,
            system_prompt=prompt,
            structured_output=_build_entity_state_schema([]),
            entities_with_states=[],
        )

    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)
    type_repo = VisionEntityTypeRepository(session)

    entity_type_definitions: dict[str, dict[str, Any]] = {}
    entities_with_states: list[dict[str, Any]] = []

    for mapping in mappings:
        entity = await entity_repo.get_by_id(mapping.entity_id)
        if not entity or not entity.is_active:
            continue

        state_defs = await sd_repo.list_by_entity_type(
            entity.entity_type_id, is_active=True
        )
        if not state_defs:
            continue
        state_definition_groups = _build_state_definition_groups(state_defs)

        entity_type = await type_repo.get_by_id(entity.entity_type_id)
        type_name = entity_type.name if entity_type else "unknown"
        type_display = entity_type.display_name if entity_type else type_name

        if type_name not in entity_type_definitions:
            entity_type_definitions[type_name] = {
                "display_name": type_display,
                "state_definition_groups": state_definition_groups,
                "state_names": [sd.name for sd in state_defs],
                "state_criteria": {
                    sd.name: sd.criteria for sd in state_defs if sd.criteria
                },
            }

        entities_with_states.append(
            {
                "name": entity.name,
                "type_name": type_name,
                "state_definition_groups": state_definition_groups,
                "state_names": [sd.name for sd in state_defs],
                "roi_hint": mapping.roi_hint,
            }
        )

    prompt = _build_system_prompt(
        user_prompt=config.llm_prompt,
        entity_type_definitions=entity_type_definitions,
        entities_with_states=entities_with_states,
    )
    return ConfigurationPromptResult(
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        system_prompt=prompt,
        structured_output=_build_entity_state_schema(entities_with_states),
        entities_with_states=entities_with_states,
    )


async def generate_observation(
    session: AsyncSession,
    camera_id: uuid.UUID,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
    is_test: bool = False,
    observed_at: datetime | None = None,
) -> GenerateObservationResponse | None:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_signal_source(camera_id)

    if not config and image_url:
        camera_name = _extract_camera_name_from_s3_key(image_url)
        if camera_name:
            config = await config_repo.get_by_name(camera_name)

    if not config:
        logger.info(
            "[Vision Observation] No camera configuration found, skipping",
            extra={"camera_id": str(camera_id)},
        )
        return None

    if not config.enabled:
        logger.info(
            "[Vision Observation] Camera configuration is disabled, skipping",
            extra={"camera_id": str(camera_id)},
        )
        return None

    camera_config_id = config.id

    mapping_repo = VisionCameraEntityRepository(session)
    mappings = await mapping_repo.list_by_camera(camera_config_id)
    if not mappings:
        logger.info(
            "[Vision Observation] No entities assigned, skipping",
            extra={"camera_id": str(camera_id), "config_id": str(camera_config_id)},
        )
        return None

    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)
    type_repo = VisionEntityTypeRepository(session)

    entity_type_definitions: dict[str, dict[str, Any]] = {}
    entities_with_states: list[dict[str, Any]] = []
    entity_lookup: dict[str, dict[str, Any]] = {}

    for mapping in mappings:
        entity = await entity_repo.get_by_id(mapping.entity_id)
        if not entity or not entity.is_active:
            continue

        state_defs = await sd_repo.list_by_entity_type(
            entity.entity_type_id, is_active=True
        )
        if not state_defs:
            continue
        state_definition_groups = _build_state_definition_groups(state_defs)
        state_name_to_id_by_type = {
            definition_type: {
                state_def.name: state_def.id
                for state_def in state_defs
                if _state_definition_group_key(state_def) == definition_type
            }
            for definition_type in state_definition_groups
        }

        entity_type = await type_repo.get_by_id(entity.entity_type_id)
        type_name = entity_type.name if entity_type else "unknown"
        type_display = entity_type.display_name if entity_type else type_name

        if type_name not in entity_type_definitions:
            entity_type_definitions[type_name] = {
                "display_name": type_display,
                "state_definition_groups": state_definition_groups,
                "state_names": [sd.name for sd in state_defs],
                "state_criteria": {
                    sd.name: sd.criteria for sd in state_defs if sd.criteria
                },
            }

        entities_with_states.append(
            {
                "name": entity.name,
                "type_name": type_name,
                "state_definition_groups": state_definition_groups,
                "state_names": [sd.name for sd in state_defs],
                "roi_hint": mapping.roi_hint,
            }
        )
        entity_lookup[entity.name] = {
            "entity_id": entity.id,
            "current_state_id": entity.current_state_id,
            "entity_type_name": type_name,
            "state_name_to_id_by_type": state_name_to_id_by_type,
            "state_name_to_id": {sd.name: sd.id for sd in state_defs},
            "state_id_to_name": {sd.id: sd.name for sd in state_defs},
            "state_id_to_definition_type": {
                sd.id: _state_definition_type(sd) for sd in state_defs
            },
        }

    if not entities_with_states:
        logger.info(
            "[Vision Observation] No active entities with state definitions, skipping",
            extra={"camera_id": str(camera_id), "config_id": str(camera_config_id)},
        )
        return None

    response_schema = _build_entity_state_schema(entities_with_states)

    system_prompt = _build_system_prompt(
        user_prompt=config.llm_prompt,
        entity_type_definitions=entity_type_definitions,
        entities_with_states=entities_with_states,
    )

    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_state_observation",
            "strict": True,
            "schema": response_schema,
        },
    }

    llm_prompt = config.llm_prompt
    llm_provider_name = config.llm_provider
    llm_model = config.llm_model
    reference_image_configs = list(config.reference_images or [])

    await session.rollback()
    logger.info(
        "[Vision Observation] Released read transaction before image and LLM work",
        extra={"camera_id": str(camera_id), "config_id": str(camera_config_id)},
    )

    s3_client = init_s3(AWS_REGION)

    reference_images: list[dict[str, Any]] = []
    if reference_image_configs:
        for ref_img in reference_image_configs:
            if not isinstance(ref_img, dict) or not ref_img.get("url"):
                continue
            try:
                img_bytes = await _fetch_s3_bytes(s3_client, ref_img["url"])
                normalized_img_bytes = await asyncio.to_thread(
                    _normalize_image_bytes_for_llm,
                    img_bytes,
                    f"reference image {ref_img['url']}",
                )
                reference_images.append(
                    {
                        "description": ref_img.get("description", "Reference image"),
                        "base64_data": base64.b64encode(normalized_img_bytes).decode(
                            "utf-8"
                        ),
                    }
                )
            except Exception as e:
                logger.warning(
                    f"[Vision Observation] Failed to load reference image: {e}"
                )

    if image_bytes is not None:
        if len(image_bytes) == 0:
            raise ValueError("Provided image bytes are empty (0 bytes)")
        camera_image_bytes = await asyncio.to_thread(
            _normalize_image_bytes_for_llm,
            image_bytes,
            "uploaded camera image",
        )
        camera_image_bytes = await asyncio.to_thread(
            _draw_roi_labels_on_image_bytes,
            camera_image_bytes,
            entities_with_states,
            "uploaded camera image",
        )
        camera_image_base64 = base64.b64encode(camera_image_bytes).decode("utf-8")
    elif image_url:
        camera_image_raw = await _fetch_s3_bytes(s3_client, image_url)
        camera_image_bytes = await asyncio.to_thread(
            _normalize_image_bytes_for_llm,
            camera_image_raw,
            f"camera image {image_url}",
        )
        camera_image_bytes = await asyncio.to_thread(
            _draw_roi_labels_on_image_bytes,
            camera_image_bytes,
            entities_with_states,
            f"camera image {image_url}",
        )
        camera_image_base64 = base64.b64encode(camera_image_bytes).decode("utf-8")
    else:
        raise ValueError("Either image_url or image file must be provided")

    provider_enum = MonitoringLLMProvider(llm_provider_name)
    llm_config = MonitoringLLMConfig(
        provider=provider_enum,
        model=llm_model,
        temperature=None,
    )
    llm_provider = await asyncio.to_thread(create_monitoring_llm_provider, llm_config)
    parsed_observed_at = parse_utc_capture_time_from_path(image_url)
    if observed_at is None and parsed_observed_at is None and image_url:
        logger.warning(
            "[Vision Observation] Image filename does not include UTC capture "
            "timestamp; falling back to processing time",
            extra={
                "camera_id": str(camera_id),
                "config_id": str(camera_config_id),
                "image_url": image_url,
                "expected_format": "snapshots/YYYY-MM-DD/YYYY-MM-DD_HH-MM-SS.jpg",
            },
        )
    observed_at = observed_at or parsed_observed_at or datetime.now(timezone.utc)

    logger.info(
        "[Vision Observation] Generating observation",
        extra={
            "camera_id": str(camera_id),
            "config_id": str(camera_config_id),
            "provider": llm_provider_name,
            "model": llm_model,
            "entity_count": len(entities_with_states),
        },
    )

    try:
        llm_result = await asyncio.to_thread(
            llm_provider.analyze_image,
            system_prompt,
            llm_prompt,
            reference_images,
            camera_image_base64,
            response_format,
        )
    except Exception as e:
        if _is_unprocessable_image_error(e):
            gemini_refusal_reason = _gemini_refusal_reason(e)
            logger.warning(
                "[Vision Observation] LLM could not process image, skipping observation",
                extra={
                    "camera_id": str(camera_id),
                    "config_id": str(camera_config_id),
                    "provider": llm_provider_name,
                    "model": llm_model,
                    "image_url": image_url,
                    "error": str(e),
                    "gemini_refusal_reason": gemini_refusal_reason,
                },
            )
            return GenerateObservationResponse(
                camera_id=camera_id,
                observed_at=observed_at,
                entity_observations=[],
                raw_llm_response={
                    "error": str(e),
                    "gemini_refusal_reason": gemini_refusal_reason,
                    "skip_reason": "unprocessable_image",
                },
                token_usage={
                    "observed": False,
                    "image_relevant": False,
                    "skip_reason": "unprocessable_image",
                },
            )
        raise

    raw_response = llm_result["result"]
    token_usage = llm_result.get("token_usage", {})

    image_relevant = raw_response.get("image_relevant", True)
    if not image_relevant:
        logger.warning(
            "[Vision Observation] Image flagged as irrelevant by LLM, "
            "skipping state updates",
            extra={
                "camera_id": str(camera_id),
                "config_id": str(camera_config_id),
            },
        )

    entity_observations: list[EntityObservation] = []
    for entity_name, observation in raw_response.items():
        if entity_name == "image_relevant":
            continue
        if entity_name not in entity_lookup:
            continue
        if not isinstance(observation, dict):
            continue

        info = entity_lookup[entity_name]
        typed_observations: list[tuple[str | None, dict[str, Any]]] = []
        if _is_legacy_observation(observation):
            typed_observations.append((None, observation))
        else:
            for definition_type, typed_observation in observation.items():
                if definition_type not in info[
                    "state_name_to_id_by_type"
                ] or not isinstance(typed_observation, dict):
                    continue
                typed_observations.append((definition_type, typed_observation))

        for definition_type, typed_observation in typed_observations:
            state_name = typed_observation.get("state", "unknown")
            if definition_type is None:
                state_id = info["state_name_to_id"].get(state_name)
            else:
                state_id = info["state_name_to_id_by_type"][definition_type].get(
                    state_name
                )

            entity_observations.append(
                EntityObservation(
                    entity_id=info["entity_id"],
                    entity_name=entity_name,
                    camera_id=camera_id,
                    definition_type=definition_type,
                    state=state_name,
                    state_id=state_id,
                    confidence=typed_observation.get("confidence", 0.0),
                )
            )

    if image_relevant and not is_test:
        event_repo = VisionStateChangeEventRepository(session)
        active_rules_by_project: dict[uuid.UUID, list[Any]] = {}
        event_generation_configs: dict[
            tuple[uuid.UUID, str, str],
            EventGenerationConfig,
        ] = {}
        for obs in entity_observations:
            if obs.state_id is None:
                continue
            lookup_info = entity_lookup[obs.entity_name]
            session.expire_all()
            fresh_entity = await entity_repo.get_by_id(obs.entity_id)
            if not fresh_entity:
                continue

            definition_type = current_state_metadata_key(
                obs.definition_type,
                obs.state_id,
                lookup_info["state_id_to_definition_type"],
            )
            config_cache_key = (
                fresh_entity.project_id,
                lookup_info["entity_type_name"],
                definition_type,
            )
            event_generation_config = event_generation_configs.get(config_cache_key)
            if event_generation_config is None:
                active_rules = active_rules_by_project.get(fresh_entity.project_id)
                if active_rules is None:
                    rule_repo = VisionRuleRepository(session)
                    active_rules = await rule_repo.list_by_project(
                        fresh_entity.project_id,
                        is_active=True,
                    )
                    active_rules_by_project[fresh_entity.project_id] = active_rules
                event_generation_config = _select_event_generation_config(
                    active_rules,
                    lookup_info["entity_type_name"],
                    definition_type,
                )
                event_generation_configs[config_cache_key] = event_generation_config

            if not is_smoothing_enabled(event_generation_config):
                await _apply_state_decision(
                    session=session,
                    entity_repo=entity_repo,
                    event_repo=event_repo,
                    entity=fresh_entity,
                    entity_metadata=fresh_entity.entity_metadata,
                    entity_id=obs.entity_id,
                    camera_config_id=camera_config_id,
                    state_id=obs.state_id,
                    state_name=obs.state,
                    confidence=obs.confidence,
                    observed_at=observed_at,
                    frame_s3_key=image_url,
                    definition_type=definition_type,
                    lookup_info=lookup_info,
                    event_metadata={"definition_type": definition_type},
                )
                continue

            smoothing_buffer = await acquire_smoothing_cache_buffer(
                obs.entity_id,
                camera_config_id,
                definition_type,
                SmoothingObservation(
                    observed_at=observed_at,
                    state_id=obs.state_id,
                    state=obs.state,
                    confidence=obs.confidence,
                    frame_s3_key=image_url,
                    camera_config_id=camera_config_id,
                ),
                event_generation_config,
            )
            if smoothing_buffer is None:
                continue

            try:
                decisions = smoothing_buffer.collect_ready_decisions(
                    datetime.now(timezone.utc),
                )
                entity_for_decisions = fresh_entity
                entity_metadata = fresh_entity.entity_metadata
                for decision in decisions:
                    smoothing_buffer.mark_finalized(decision.center_observed_at)
                    current_observed_at = current_state_observed_at_from_metadata(
                        get_current_states_metadata(entity_metadata),
                        definition_type,
                    )
                    if (
                        current_observed_at is not None
                        and decision.center_observed_at <= current_observed_at
                    ):
                        if decision.center_observed_at == current_observed_at:
                            await _recover_applied_smoothing_decision(
                                session=session,
                                event_repo=event_repo,
                                entity=entity_for_decisions,
                                entity_metadata=entity_metadata,
                                entity_id=obs.entity_id,
                                decision=decision,
                                definition_type=definition_type,
                                lookup_info=lookup_info,
                            )
                        continue
                    if (
                        decision.state_id is None
                        or decision.state is None
                        or decision.confidence is None
                    ):
                        continue
                    entity_for_decisions, entity_metadata = await _apply_state_decision(
                        session=session,
                        entity_repo=entity_repo,
                        event_repo=event_repo,
                        entity=entity_for_decisions,
                        entity_metadata=entity_metadata,
                        entity_id=obs.entity_id,
                        camera_config_id=decision.center_camera_config_id,
                        state_id=decision.state_id,
                        state_name=decision.state,
                        confidence=decision.confidence,
                        observed_at=decision.center_observed_at,
                        frame_s3_key=decision.center_frame_s3_key,
                        definition_type=definition_type,
                        lookup_info=lookup_info,
                        event_metadata={
                            "definition_type": definition_type,
                            "smoothing": decision.metadata,
                        },
                        include_recovery_metadata=True,
                    )
                try:
                    await smoothing_buffer.save()
                except (OSError, RedisError, TypeError, ValueError):
                    logger.warning(
                        "[Vision Observation] Failed to persist smoothing cache buffer",
                        extra={
                            "entity_id": str(obs.entity_id),
                            "definition_type": definition_type,
                        },
                        exc_info=True,
                    )
            finally:
                await smoothing_buffer.release()

    token_usage["observed"] = True
    token_usage["image_relevant"] = image_relevant

    return GenerateObservationResponse(
        camera_id=camera_id,
        observed_at=observed_at,
        entity_observations=entity_observations,
        raw_llm_response=raw_response,
        token_usage=token_usage,
    )
