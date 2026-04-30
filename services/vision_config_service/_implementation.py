from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_camera_configuration import (
    AssignEntityRequest,
    CameraConfigResponse,
    CameraEntityResponse,
    CreateCameraConfigRequest,
    ListCameraConfigsResponse,
    ListCameraEntitiesResponse,
    UpdateCameraConfigRequest,
    UpdateCameraEntityRequest,
)
from db.pal_repository import (
    VisionCameraConfigurationRepository,
    VisionCameraEntityRepository,
    VisionEntityRepository,
)
from db.pal_repository.data_classes.vision_camera_configuration import (
    VisionCameraConfigurationData,
)
from db.pal_repository.data_classes.vision_camera_entity import VisionCameraEntityData
from utils.log import logger


def _build_response(data: VisionCameraConfigurationData) -> CameraConfigResponse:
    return CameraConfigResponse(
        id=data.id,
        signal_source_id=data.signal_source_id,
        project_id=data.project_id,
        name=data.name,
        llm_prompt=data.llm_prompt,
        llm_provider=data.llm_provider,
        llm_model=data.llm_model,
        processing_interval_seconds=data.processing_interval_seconds,
        reference_images=data.reference_images,
        enabled=data.enabled,
        created_at=data.created_at,
        updated_at=data.updated_at,
    )


async def create_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateCameraConfigRequest,
) -> CameraConfigResponse:
    repo = VisionCameraConfigurationRepository(session)

    existing = await repo.get_by_signal_source(request.signal_source_id)
    if existing:
        raise ValueError(
            f"Camera configuration already exists for signal source {request.signal_source_id}"
        )

    record = VisionCameraConfigurationData(
        id=uuid.uuid4(),
        signal_source_id=request.signal_source_id,
        project_id=project_id,
        name=request.name,
        llm_prompt=request.llm_prompt,
        llm_provider=request.llm_provider,
        llm_model=request.llm_model,
        processing_interval_seconds=request.processing_interval_seconds,
        reference_images=request.reference_images,
        enabled=request.enabled,
        created_at=datetime.now(timezone.utc),
    )

    await repo.create(record)
    logger.info(
        "[Vision Config] Created camera config",
        extra={"config_id": str(record.id), "project_id": str(project_id)},
    )
    return _build_response(record)


async def get_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> CameraConfigResponse:
    repo = VisionCameraConfigurationRepository(session)

    data = await repo.get_by_id(config_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    return _build_response(data)


async def get_camera_config_by_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID,
) -> CameraConfigResponse:
    repo = VisionCameraConfigurationRepository(session)

    data = await repo.get_by_signal_source(signal_source_id)
    if not data or data.project_id != project_id:
        raise ValueError(
            f"Camera configuration for signal source {signal_source_id} not found"
        )

    return _build_response(data)


async def list_camera_configs(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> ListCameraConfigsResponse:
    repo = VisionCameraConfigurationRepository(session)

    configs = await repo.list_by_project(project_id)

    items = [_build_response(c) for c in configs]
    return ListCameraConfigsResponse(items=items, total=len(items))


async def update_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: UpdateCameraConfigRequest,
) -> CameraConfigResponse:
    repo = VisionCameraConfigurationRepository(session)

    data = await repo.get_by_id(config_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    updates: dict[str, object] = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.llm_prompt is not None:
        updates["llm_prompt"] = request.llm_prompt
    if request.llm_provider is not None:
        updates["llm_provider"] = request.llm_provider
    if request.llm_model is not None:
        updates["llm_model"] = request.llm_model
    if request.processing_interval_seconds is not None:
        updates["processing_interval_seconds"] = request.processing_interval_seconds
    if request.reference_images is not None:
        updates["reference_images"] = request.reference_images
    if request.enabled is not None:
        updates["enabled"] = request.enabled

    if not updates:
        return _build_response(data)

    updated = await repo.update(config_id, **updates)
    if not updated:
        raise ValueError(f"Camera configuration {config_id} not found")

    logger.info(
        "[Vision Config] Updated camera config",
        extra={"config_id": str(config_id)},
    )
    return _build_response(updated)


async def delete_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> bool:
    repo = VisionCameraConfigurationRepository(session)

    data = await repo.get_by_id(config_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    deleted = await repo.delete(config_id)
    if deleted:
        logger.info(
            "[Vision Config] Deleted camera config",
            extra={"config_id": str(config_id)},
        )
    return deleted


def _build_camera_entity_response(
    data: VisionCameraEntityData,
) -> CameraEntityResponse:
    return CameraEntityResponse(
        id=data.id,
        camera_config_id=data.camera_config_id,
        entity_id=data.entity_id,
        roi_hint=data.roi_hint,
        created_at=data.created_at,
    )


async def assign_entity_to_camera(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: AssignEntityRequest,
) -> CameraEntityResponse:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    entity_repo = VisionEntityRepository(session)
    entity = await entity_repo.get_by_id(request.entity_id)
    if not entity or entity.project_id != project_id:
        raise ValueError(f"Entity {request.entity_id} not found")

    mapping_repo = VisionCameraEntityRepository(session)
    existing = await mapping_repo.get_by_camera_and_entity(config_id, request.entity_id)
    if existing:
        raise ValueError(
            f"Entity {request.entity_id} is already assigned to camera {config_id}"
        )

    record = VisionCameraEntityData(
        id=uuid.uuid4(),
        camera_config_id=config_id,
        entity_id=request.entity_id,
        roi_hint=request.roi_hint,
        created_at=datetime.now(timezone.utc),
    )

    await mapping_repo.create(record)
    logger.info(
        "[Vision Config] Assigned entity to camera",
        extra={
            "config_id": str(config_id),
            "entity_id": str(request.entity_id),
        },
    )
    return _build_camera_entity_response(record)


async def unassign_entity_from_camera(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> bool:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    mapping_repo = VisionCameraEntityRepository(session)
    existing = await mapping_repo.get_by_camera_and_entity(config_id, entity_id)
    if not existing:
        raise ValueError(f"Entity {entity_id} is not assigned to camera {config_id}")

    deleted = await mapping_repo.delete(existing.id)
    if deleted:
        logger.info(
            "[Vision Config] Unassigned entity from camera",
            extra={"config_id": str(config_id), "entity_id": str(entity_id)},
        )
    return deleted


async def list_camera_entities(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> ListCameraEntitiesResponse:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    mapping_repo = VisionCameraEntityRepository(session)
    mappings = await mapping_repo.list_by_camera(config_id)

    items = [_build_camera_entity_response(m) for m in mappings]
    return ListCameraEntitiesResponse(items=items, total=len(items))


async def list_cameras_for_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> ListCameraEntitiesResponse:
    entity_repo = VisionEntityRepository(session)
    entity = await entity_repo.get_by_id(entity_id)
    if not entity or entity.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    mapping_repo = VisionCameraEntityRepository(session)
    mappings = await mapping_repo.list_by_entity(entity_id)

    items = [_build_camera_entity_response(m) for m in mappings]
    return ListCameraEntitiesResponse(items=items, total=len(items))


async def update_camera_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateCameraEntityRequest,
) -> CameraEntityResponse:
    config_repo = VisionCameraConfigurationRepository(session)
    config = await config_repo.get_by_id(config_id)
    if not config or config.project_id != project_id:
        raise ValueError(f"Camera configuration {config_id} not found")

    mapping_repo = VisionCameraEntityRepository(session)
    existing = await mapping_repo.get_by_camera_and_entity(config_id, entity_id)
    if not existing:
        raise ValueError(f"Entity {entity_id} is not assigned to camera {config_id}")

    updated = await mapping_repo.update(existing.id, roi_hint=request.roi_hint)
    if not updated:
        raise ValueError(f"Entity {entity_id} is not assigned to camera {config_id}")

    logger.info(
        "[Vision Config] Updated camera-entity mapping",
        extra={"config_id": str(config_id), "entity_id": str(entity_id)},
    )
    return _build_camera_entity_response(updated)
