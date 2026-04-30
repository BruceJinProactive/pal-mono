"""Vision Camera Configuration API Routes Implementation."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
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
from services import vision_config_service
from utils.log import logger
from utils.otel import traced


@traced("vision_config.create_camera_config")
async def create_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateCameraConfigRequest,
) -> CameraConfigResponse:
    try:
        return await vision_config_service.create_camera_config(
            session=session,
            project_id=project_id,
            request=request,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to create camera config",
            exc_info=True,
            extra={"project_id": str(project_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create camera configuration",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.get_camera_config")
async def get_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> CameraConfigResponse:
    try:
        return await vision_config_service.get_camera_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to get camera config",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get camera configuration",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.get_camera_config_by_source")
async def get_camera_config_by_source(
    session: AsyncSession,
    project_id: uuid.UUID,
    signal_source_id: uuid.UUID,
) -> CameraConfigResponse:
    try:
        return await vision_config_service.get_camera_config_by_source(
            session=session,
            project_id=project_id,
            signal_source_id=signal_source_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to get camera config by source",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "signal_source_id": str(signal_source_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get camera configuration",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.list_camera_configs")
async def list_camera_configs(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> ListCameraConfigsResponse:
    try:
        return await vision_config_service.list_camera_configs(
            session=session,
            project_id=project_id,
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to list camera configs",
            exc_info=True,
            extra={"project_id": str(project_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list camera configurations",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.update_camera_config")
async def update_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: UpdateCameraConfigRequest,
) -> CameraConfigResponse:
    try:
        return await vision_config_service.update_camera_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
                headers={"Content-Type": "application/json"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to update camera config",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update camera configuration",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.delete_camera_config")
async def delete_camera_config(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> None:
    try:
        await vision_config_service.delete_camera_config(
            session=session,
            project_id=project_id,
            config_id=config_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to delete camera config",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete camera configuration",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.assign_entity_to_camera")
async def assign_entity_to_camera(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    request: AssignEntityRequest,
) -> CameraEntityResponse:
    try:
        return await vision_config_service.assign_entity_to_camera(
            session=session,
            project_id=project_id,
            config_id=config_id,
            request=request,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
                headers={"Content-Type": "application/json"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to assign entity to camera",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign entity to camera",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.unassign_entity_from_camera")
async def unassign_entity_from_camera(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> None:
    try:
        await vision_config_service.unassign_entity_from_camera(
            session=session,
            project_id=project_id,
            config_id=config_id,
            entity_id=entity_id,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
                headers={"Content-Type": "application/json"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to unassign entity from camera",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unassign entity from camera",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.list_camera_entities")
async def list_camera_entities(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
) -> ListCameraEntitiesResponse:
    try:
        return await vision_config_service.list_camera_entities(
            session=session,
            project_id=project_id,
            config_id=config_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to list camera entities",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list camera entities",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.list_cameras_for_entity")
async def list_cameras_for_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> ListCameraEntitiesResponse:
    try:
        return await vision_config_service.list_cameras_for_entity(
            session=session,
            project_id=project_id,
            entity_id=entity_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to list cameras for entity",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list cameras for entity",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_config.update_camera_entity")
async def update_camera_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    config_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateCameraEntityRequest,
) -> CameraEntityResponse:
    try:
        return await vision_config_service.update_camera_entity(
            session=session,
            project_id=project_id,
            config_id=config_id,
            entity_id=entity_id,
            request=request,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
                headers={"Content-Type": "application/json"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Config] Failed to update camera-entity mapping",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "config_id": str(config_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update camera-entity mapping",
            headers={"Content-Type": "application/json"},
        )
