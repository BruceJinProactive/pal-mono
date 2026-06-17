from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import datetime, timezone
from typing import Any

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
from services.vision_observation_service._workflow import handle_state_change_rules
from services.vision_state_metadata import (
    LEGACY_CURRENT_STATE_TYPE,
    current_state_id_from_metadata,
    current_state_metadata_key,
    get_current_states_metadata,
    set_current_state_metadata,
)
from utils.log import logger
from utils.vision_capture_time import parse_utc_capture_time_from_path


async def _fetch_s3_bytes(s3_client: Any, key: str) -> bytes:
    response = await asyncio.to_thread(
        s3_client.get_object, Bucket=AWS_ASSET_BUCKET_NAME, Key=key
    )
    return await asyncio.to_thread(response["Body"].read)


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
                group_properties[definition_type] = {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": group_info["state_names"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                    },
                    "required": ["state", "confidence"],
                    "additionalProperties": False,
                }

            properties[entity_name] = {
                "type": "object",
                "properties": group_properties,
                "required": list(group_properties.keys()),
                "additionalProperties": False,
            }
            continue

        state_names = entity_info["state_names"]
        properties[entity_name] = {
            "type": "object",
            "properties": {
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
            "required": ["state", "confidence"],
            "additionalProperties": False,
        }

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


def _format_roi_hint(roi_hint: dict[str, object] | None) -> str | None:
    if not roi_hint:
        return None

    x_val = roi_hint.get("x")
    y_val = roi_hint.get("y")
    w_val = roi_hint.get("width") or roi_hint.get("w")
    h_val = roi_hint.get("height") or roi_hint.get("h")

    if x_val is None or y_val is None or w_val is None or h_val is None:
        return None

    x = int(float(str(x_val)))
    y = int(float(str(y_val)))
    w = int(float(str(w_val)))
    h = int(float(str(h_val)))

    return f"[{x}, {y}, {w}, {h}]"


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
        "- For entities with ROI coordinates, focus on the specific area defined "
        "by the normalized coordinates [x, y, width, height] (scale 0-1000). "
        "Investigate this region only",
    ]

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

    s3_client = init_s3(AWS_REGION)

    reference_images: list[dict[str, Any]] = []
    if config.reference_images:
        for ref_img in config.reference_images:
            if not isinstance(ref_img, dict) or not ref_img.get("url"):
                continue
            try:
                img_bytes = await _fetch_s3_bytes(s3_client, ref_img["url"])
                reference_images.append(
                    {
                        "description": ref_img.get("description", "Reference image"),
                        "base64_data": base64.b64encode(img_bytes).decode("utf-8"),
                    }
                )
            except Exception as e:
                logger.warning(
                    f"[Vision Observation] Failed to load reference image: {e}"
                )

    if image_bytes is not None:
        if len(image_bytes) == 0:
            raise ValueError("Provided image bytes are empty (0 bytes)")
        camera_image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    elif image_url:
        camera_image_raw = await _fetch_s3_bytes(s3_client, image_url)
        camera_image_base64 = base64.b64encode(camera_image_raw).decode("utf-8")
    else:
        raise ValueError("Either image_url or image file must be provided")

    provider_enum = MonitoringLLMProvider(config.llm_provider)
    llm_config = MonitoringLLMConfig(
        provider=provider_enum,
        model=config.llm_model,
    )
    llm_provider = await asyncio.to_thread(create_monitoring_llm_provider, llm_config)

    logger.info(
        "[Vision Observation] Generating observation",
        extra={
            "camera_id": str(camera_id),
            "config_id": str(camera_config_id),
            "provider": config.llm_provider,
            "model": config.llm_model,
            "entity_count": len(entities_with_states),
        },
    )

    llm_result = await asyncio.to_thread(
        llm_provider.analyze_image,
        system_prompt,
        config.llm_prompt,
        reference_images,
        camera_image_base64,
        response_format,
    )

    raw_response = llm_result["result"]
    token_usage = llm_result.get("token_usage", {})
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
            current_states = get_current_states_metadata(fresh_entity.entity_metadata)
            previous_state_id = current_state_id_from_metadata(
                current_states, definition_type
            )
            if (
                previous_state_id is None
                and fresh_entity.current_state_id is not None
                and lookup_info["state_id_to_definition_type"].get(
                    fresh_entity.current_state_id
                )
                == definition_type
            ):
                previous_state_id = fresh_entity.current_state_id

            state_changed = obs.state_id != previous_state_id
            metadata_missing = definition_type not in current_states
            if not state_changed and not metadata_missing:
                continue

            current_state_since = (
                observed_at
                if state_changed
                else fresh_entity.current_state_since or observed_at
            )
            entity_metadata = set_current_state_metadata(
                fresh_entity.entity_metadata,
                definition_type,
                obs.state_id,
                obs.state,
                current_state_since,
                observed_at,
                obs.confidence,
            )
            updates: dict[str, object] = {"entity_metadata": entity_metadata}
            if len(lookup_info["state_name_to_id_by_type"]) == 1:
                updates["current_state_id"] = obs.state_id
                updates["current_state_since"] = current_state_since
            await entity_repo.update(
                obs.entity_id,
                **updates,
            )
            if not state_changed:
                continue
            state_change_event = VisionStateChangeEventData(
                id=uuid.uuid4(),
                entity_id=obs.entity_id,
                new_state_id=obs.state_id,
                observed_at=observed_at,
                event_metadata={"definition_type": definition_type},
                camera_config_id=camera_config_id,
                previous_state_id=previous_state_id,
                confidence=obs.confidence,
                frame_s3_key=image_url,
            )
            await event_repo.create(state_change_event)
            previous_state_name = None
            if previous_state_id is not None:
                previous_state_name = lookup_info["state_id_to_name"].get(
                    previous_state_id
                )
            await handle_state_change_rules(
                session=session,
                entity=fresh_entity,
                state_change_event=state_change_event,
                state_name=obs.state,
                previous_state_name=previous_state_name,
                entity_type_name=lookup_info["entity_type_name"],
            )

    token_usage["observed"] = True
    token_usage["image_relevant"] = image_relevant

    return GenerateObservationResponse(
        camera_id=camera_id,
        observed_at=observed_at,
        entity_observations=entity_observations,
        raw_llm_response=raw_response,
        token_usage=token_usage,
    )
