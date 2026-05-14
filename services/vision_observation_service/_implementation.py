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
from utils.log import logger


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

    return (
        f"Focus on the specific area defined by the normalized coordinates "
        f"[{x}, {y}, {w}, {h}] (scale 0-1000). Investigate this region only."
    )


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
        "based on what you see in the image.",
        "",
        "Rules:",
        "- Only use the allowed states listed for each entity",
        "- If you cannot clearly determine the state, pick the most likely one "
        "and reflect that in your confidence score",
        "- Confidence should be 0.0-1.0 where 1.0 means absolute certainty",
        "- If an entity is not visible in the frame at all, use confidence 0.0 "
        "and pick the most reasonable default state",
        "- Set image_relevant to false if the camera image is completely "
        "irrelevant to the reference images or the monitored environment "
        "(e.g. a broken feed, black screen, unrelated scene). "
        "Otherwise set image_relevant to true",
    ]

    if user_prompt:
        lines.append("")
        lines.append("Context:")
        lines.append(user_prompt)

    lines.append("")
    lines.append("Entities to Observe:")
    lines.append(
        "Each entity below is an item you need to observe in the image. "
        "For each one, you must select exactly one state from its list of "
        "possible states."
    )
    for entity_info in entities_with_states:
        type_name = entity_info["type_name"]
        type_info = entity_type_definitions.get(type_name, {})
        display = type_info.get("display_name", type_name)
        lines.append("")
        lines.append(f'- "{entity_info["name"]}" (a {display})')
        if entity_info.get("roi_hint_text"):
            lines.append(f"  - Location hint: {entity_info['roi_hint_text']}")
        lines.append("  - Possible states (pick one):")
        state_criteria = type_info.get("state_criteria", {})
        for state_name in entity_info["state_names"]:
            criteria = state_criteria.get(state_name)
            if criteria:
                lines.append(f'    - "{state_name}": {criteria}')
            else:
                lines.append(f'    - "{state_name}"')

    lines.append("")
    lines.append("Respond ONLY with valid JSON matching the provided schema.")

    return "\n".join(lines)


def _extract_camera_name_from_s3_key(image_url: str) -> str | None:
    parts = image_url.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "cameras":
        return parts[1]
    return None


async def generate_observation(
    session: AsyncSession,
    camera_id: uuid.UUID,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
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

        state_defs = await sd_repo.list_by_entity_type(entity.entity_type_id)
        if not state_defs:
            continue

        entity_type = await type_repo.get_by_id(entity.entity_type_id)
        type_name = entity_type.name if entity_type else "unknown"
        type_display = entity_type.display_name if entity_type else type_name

        if type_name not in entity_type_definitions:
            entity_type_definitions[type_name] = {
                "display_name": type_display,
                "state_names": [sd.name for sd in state_defs],
                "state_criteria": {
                    sd.name: sd.criteria for sd in state_defs if sd.criteria
                },
            }

        roi_hint_text = _format_roi_hint(mapping.roi_hint)

        entities_with_states.append(
            {
                "name": entity.name,
                "type_name": type_name,
                "state_names": [sd.name for sd in state_defs],
                "roi_hint_text": roi_hint_text,
            }
        )
        entity_lookup[entity.name] = {
            "entity_id": entity.id,
            "current_state_id": entity.current_state_id,
            "state_name_to_id": {sd.name: sd.id for sd in state_defs},
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
    observed_at = datetime.now(timezone.utc)

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
        state_name = observation.get("state", "unknown")
        state_id = info["state_name_to_id"].get(state_name)

        entity_observations.append(
            EntityObservation(
                entity_id=info["entity_id"],
                entity_name=entity_name,
                camera_id=camera_id,
                state=state_name,
                state_id=state_id,
                confidence=observation.get("confidence", 0.0),
            )
        )

    if image_relevant:
        event_repo = VisionStateChangeEventRepository(session)
        for obs in entity_observations:
            if obs.state_id is None:
                continue
            info = entity_lookup[obs.entity_name]
            if obs.state_id == info["current_state_id"]:
                continue
            await entity_repo.update(
                obs.entity_id,
                current_state_id=obs.state_id,
                current_state_since=observed_at,
            )
            await event_repo.create(
                VisionStateChangeEventData(
                    id=uuid.uuid4(),
                    entity_id=obs.entity_id,
                    new_state_id=obs.state_id,
                    observed_at=observed_at,
                    camera_config_id=camera_config_id,
                    previous_state_id=info["current_state_id"],
                    confidence=obs.confidence,
                    frame_s3_key=image_url,
                )
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
