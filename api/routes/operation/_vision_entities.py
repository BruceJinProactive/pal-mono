"""Vision Entity API Routes Implementation."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_entity import (
    CreateEntityRequest,
    CreateEntityTypeRequest,
    CreateStateDefinitionRequest,
    EntityResponse,
    EntityTypeResponse,
    ListEntitiesResponse,
    ListEntityTypesResponse,
    ListStateDefinitionsResponse,
    StateDefinitionResponse,
    UpdateEntityRequest,
    UpdateEntityStateRequest,
    UpdateEntityTypeRequest,
    UpdateStateDefinitionRequest,
)
from services import account_service, vision_entity_service
from utils.log import logger
from utils.otel import traced


async def _resolve_account_id(session: AsyncSession, account_name: str) -> uuid.UUID:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )
    return account.id


@traced("vision_entity.create_entity_type")
async def create_entity_type(
    session: AsyncSession,
    account_name: str,
    request: CreateEntityTypeRequest,
) -> EntityTypeResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.create_entity_type(
            session=session,
            account_id=account_id,
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
            "[Vision Entity] Failed to create entity type",
            exc_info=True,
            extra={"account_name": account_name, "entity_type_name": request.name},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create entity type",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.get_entity_type")
async def get_entity_type(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
) -> EntityTypeResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.get_entity_type(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to get entity type",
            exc_info=True,
            extra={
                "account_name": account_name,
                "entity_type_id": str(entity_type_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get entity type",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.list_entity_types")
async def list_entity_types(
    session: AsyncSession,
    account_name: str,
    is_active: bool | None = None,
) -> ListEntityTypesResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.list_entity_types(
            session=session,
            account_id=account_id,
            is_active=is_active,
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to list entity types",
            exc_info=True,
            extra={"account_name": account_name},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list entity types",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.update_entity_type")
async def update_entity_type(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
    request: UpdateEntityTypeRequest,
) -> EntityTypeResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.update_entity_type(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
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
            "[Vision Entity] Failed to update entity type",
            exc_info=True,
            extra={
                "account_name": account_name,
                "entity_type_id": str(entity_type_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update entity type",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.delete_entity_type")
async def delete_entity_type(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
) -> None:
    account_id = await _resolve_account_id(session, account_name)
    try:
        await vision_entity_service.delete_entity_type(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to delete entity type",
            exc_info=True,
            extra={
                "account_name": account_name,
                "entity_type_id": str(entity_type_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete entity type",
            headers={"Content-Type": "application/json"},
        )


# ---------------------------------------------------------------------------
# State Definition handlers
# ---------------------------------------------------------------------------


@traced("vision_entity.create_state_definition")
async def create_state_definition(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
    request: CreateStateDefinitionRequest,
) -> StateDefinitionResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.create_state_definition(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
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
            "[Vision Entity] Failed to create state definition",
            exc_info=True,
            extra={
                "account_name": account_name,
                "entity_type_id": str(entity_type_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create state definition",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.list_state_definitions")
async def list_state_definitions(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
) -> ListStateDefinitionsResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.list_state_definitions(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to list state definitions",
            exc_info=True,
            extra={
                "account_name": account_name,
                "entity_type_id": str(entity_type_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list state definitions",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.update_state_definition")
async def update_state_definition(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
    request: UpdateStateDefinitionRequest,
) -> StateDefinitionResponse:
    account_id = await _resolve_account_id(session, account_name)
    try:
        return await vision_entity_service.update_state_definition(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
            state_definition_id=state_definition_id,
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
            "[Vision Entity] Failed to update state definition",
            exc_info=True,
            extra={
                "account_name": account_name,
                "state_definition_id": str(state_definition_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update state definition",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.delete_state_definition")
async def delete_state_definition(
    session: AsyncSession,
    account_name: str,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
) -> None:
    account_id = await _resolve_account_id(session, account_name)
    try:
        await vision_entity_service.delete_state_definition(
            session=session,
            account_id=account_id,
            entity_type_id=entity_type_id,
            state_definition_id=state_definition_id,
        )
    except ValueError as e:
        detail = str(e)
        if "Cannot delete" in detail:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
                headers={"Content-Type": "application/json"},
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to delete state definition",
            exc_info=True,
            extra={
                "account_name": account_name,
                "state_definition_id": str(state_definition_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete state definition",
            headers={"Content-Type": "application/json"},
        )


# ---------------------------------------------------------------------------
# Entity handlers
# ---------------------------------------------------------------------------


@traced("vision_entity.create_entity")
async def create_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateEntityRequest,
) -> EntityResponse:
    try:
        return await vision_entity_service.create_entity(
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
            "[Vision Entity] Failed to create entity",
            exc_info=True,
            extra={"project_id": str(project_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create entity",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.get_entity")
async def get_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> EntityResponse:
    try:
        return await vision_entity_service.get_entity(
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
            "[Vision Entity] Failed to get entity",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get entity",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.list_entities")
async def list_entities(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_type_id: uuid.UUID | None = None,
    current_state_id: uuid.UUID | None = None,
) -> ListEntitiesResponse:
    try:
        return await vision_entity_service.list_entities(
            session=session,
            project_id=project_id,
            entity_type_id=entity_type_id,
            current_state_id=current_state_id,
        )
    except Exception:
        logger.error(
            "[Vision Entity] Failed to list entities",
            exc_info=True,
            extra={"project_id": str(project_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list entities",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.update_entity")
async def update_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityRequest,
) -> EntityResponse:
    try:
        return await vision_entity_service.update_entity(
            session=session,
            project_id=project_id,
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
            "[Vision Entity] Failed to update entity",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update entity",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.update_entity_state")
async def update_entity_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityStateRequest,
) -> EntityResponse:
    try:
        return await vision_entity_service.update_entity_state(
            session=session,
            project_id=project_id,
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
            "[Vision Entity] Failed to update entity state",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update entity state",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.delete_entity_state")
async def delete_entity_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    definition_type: str,
) -> None:
    try:
        await vision_entity_service.delete_entity_state(
            session=session,
            project_id=project_id,
            entity_id=entity_id,
            definition_type=definition_type,
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
            "[Vision Entity] Failed to delete entity state",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
                "definition_type": definition_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete entity state",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_entity.delete_entity")
async def delete_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> None:
    try:
        await vision_entity_service.delete_entity(
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
            "[Vision Entity] Failed to delete entity",
            exc_info=True,
            extra={
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete entity",
            headers={"Content-Type": "application/json"},
        )
