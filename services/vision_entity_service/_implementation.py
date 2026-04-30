from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
from db.pal_repository import (
    VisionEntityRepository,
    VisionEntityStateDefinitionRepository,
    VisionEntityTypeRepository,
)
from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.data_classes.vision_entity_state_definition import (
    VisionEntityStateDefinitionData,
)
from db.pal_repository.data_classes.vision_entity_type import VisionEntityTypeData
from utils.log import logger


def _build_entity_type_response(data: VisionEntityTypeData) -> EntityTypeResponse:
    return EntityTypeResponse(
        id=data.id,
        account_id=data.account_id,
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        icon=data.icon,
        is_active=data.is_active,
        created_at=data.created_at,
        updated_at=data.updated_at,
    )


async def create_entity_type(
    session: AsyncSession,
    account_id: uuid.UUID,
    request: CreateEntityTypeRequest,
) -> EntityTypeResponse:
    repo = VisionEntityTypeRepository(session)

    existing = await repo.get_by_account_and_name(account_id, request.name)
    if existing:
        raise ValueError(
            f"Entity type with name '{request.name}' already exists for this account"
        )

    record = VisionEntityTypeData(
        id=uuid.uuid4(),
        account_id=account_id,
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        icon=request.icon,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    await repo.create(record)
    logger.info(
        "[Vision Entity] Created entity type",
        extra={"entity_type_id": str(record.id), "account_id": str(account_id)},
    )
    return _build_entity_type_response(record)


async def get_entity_type(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
) -> EntityTypeResponse:
    repo = VisionEntityTypeRepository(session)

    data = await repo.get_by_id(entity_type_id)
    if not data or data.account_id != account_id:
        raise ValueError(f"Entity type {entity_type_id} not found")

    return _build_entity_type_response(data)


async def list_entity_types(
    session: AsyncSession,
    account_id: uuid.UUID,
    is_active: bool | None = None,
) -> ListEntityTypesResponse:
    repo = VisionEntityTypeRepository(session)

    entity_types = await repo.get_by_account(account_id, is_active=is_active)

    items = [_build_entity_type_response(et) for et in entity_types]
    return ListEntityTypesResponse(items=items, total=len(items))


async def update_entity_type(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
    request: UpdateEntityTypeRequest,
) -> EntityTypeResponse:
    repo = VisionEntityTypeRepository(session)

    data = await repo.get_by_id(entity_type_id)
    if not data or data.account_id != account_id:
        raise ValueError(f"Entity type {entity_type_id} not found")

    updates: dict[str, object] = {}
    provided = request.model_fields_set
    if "name" in provided and request.name is not None:
        existing = await repo.get_by_account_and_name(account_id, request.name)
        if existing and existing.id != entity_type_id:
            raise ValueError(
                f"Entity type with name '{request.name}' already exists for this account"
            )
        updates["name"] = request.name
    if "display_name" in provided:
        updates["display_name"] = request.display_name
    if "description" in provided:
        updates["description"] = request.description
    if "icon" in provided:
        updates["icon"] = request.icon
    if "is_active" in provided:
        updates["is_active"] = request.is_active

    if not updates:
        return _build_entity_type_response(data)

    updated = await repo.update(entity_type_id, **updates)
    if not updated:
        raise ValueError(f"Entity type {entity_type_id} not found")

    logger.info(
        "[Vision Entity] Updated entity type",
        extra={"entity_type_id": str(entity_type_id)},
    )
    return _build_entity_type_response(updated)


async def delete_entity_type(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
) -> bool:
    repo = VisionEntityTypeRepository(session)

    data = await repo.get_by_id(entity_type_id)
    if not data or data.account_id != account_id:
        raise ValueError(f"Entity type {entity_type_id} not found")

    deleted = await repo.delete(entity_type_id)
    if deleted:
        logger.info(
            "[Vision Entity] Deleted entity type",
            extra={"entity_type_id": str(entity_type_id)},
        )
    return deleted


# ---------------------------------------------------------------------------
# State Definition CRUD
# ---------------------------------------------------------------------------


def _build_state_definition_response(
    data: VisionEntityStateDefinitionData,
) -> StateDefinitionResponse:
    return StateDefinitionResponse(
        id=data.id,
        entity_type_id=data.entity_type_id,
        name=data.name,
        display_name=data.display_name,
        color=data.color,
        sort_order=data.sort_order,
        is_default=data.is_default,
        created_at=data.created_at,
    )


async def _verify_entity_type_ownership(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
) -> None:
    et_repo = VisionEntityTypeRepository(session)
    entity_type = await et_repo.get_by_id(entity_type_id)
    if not entity_type or entity_type.account_id != account_id:
        raise ValueError(f"Entity type {entity_type_id} not found")


async def create_state_definition(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
    request: CreateStateDefinitionRequest,
) -> StateDefinitionResponse:
    await _verify_entity_type_ownership(session, account_id, entity_type_id)

    repo = VisionEntityStateDefinitionRepository(session)

    existing = await repo.get_by_entity_type_and_name(entity_type_id, request.name)
    if existing:
        raise ValueError(
            f"State definition with name '{request.name}' already exists for this entity type"
        )

    if request.is_default:
        await repo.clear_default_for_entity_type(entity_type_id)

    record = VisionEntityStateDefinitionData(
        id=uuid.uuid4(),
        entity_type_id=entity_type_id,
        name=request.name,
        display_name=request.display_name,
        color=request.color,
        sort_order=request.sort_order,
        is_default=request.is_default,
        created_at=datetime.now(timezone.utc),
    )

    await repo.create(record)
    logger.info(
        "[Vision Entity] Created state definition",
        extra={
            "state_definition_id": str(record.id),
            "entity_type_id": str(entity_type_id),
        },
    )
    return _build_state_definition_response(record)


async def list_state_definitions(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
) -> ListStateDefinitionsResponse:
    await _verify_entity_type_ownership(session, account_id, entity_type_id)

    repo = VisionEntityStateDefinitionRepository(session)
    definitions = await repo.list_by_entity_type(entity_type_id)

    items = [_build_state_definition_response(d) for d in definitions]
    return ListStateDefinitionsResponse(items=items, total=len(items))


async def update_state_definition(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
    request: UpdateStateDefinitionRequest,
) -> StateDefinitionResponse:
    await _verify_entity_type_ownership(session, account_id, entity_type_id)

    repo = VisionEntityStateDefinitionRepository(session)

    data = await repo.get_by_id(state_definition_id)
    if not data or data.entity_type_id != entity_type_id:
        raise ValueError(f"State definition {state_definition_id} not found")

    updates: dict[str, object] = {}
    provided = request.model_fields_set
    if "name" in provided and request.name is not None:
        existing = await repo.get_by_entity_type_and_name(entity_type_id, request.name)
        if existing and existing.id != state_definition_id:
            raise ValueError(
                f"State definition with name '{request.name}' already exists for this entity type"
            )
        updates["name"] = request.name
    if "display_name" in provided:
        updates["display_name"] = request.display_name
    if "color" in provided:
        updates["color"] = request.color
    if "sort_order" in provided:
        updates["sort_order"] = request.sort_order
    if "is_default" in provided:
        updates["is_default"] = request.is_default

    if not updates:
        return _build_state_definition_response(data)

    if updates.get("is_default") is True:
        await repo.clear_default_for_entity_type(entity_type_id)

    updated = await repo.update(state_definition_id, **updates)
    if not updated:
        raise ValueError(f"State definition {state_definition_id} not found")

    logger.info(
        "[Vision Entity] Updated state definition",
        extra={"state_definition_id": str(state_definition_id)},
    )
    return _build_state_definition_response(updated)


async def delete_state_definition(
    session: AsyncSession,
    account_id: uuid.UUID,
    entity_type_id: uuid.UUID,
    state_definition_id: uuid.UUID,
) -> bool:
    await _verify_entity_type_ownership(session, account_id, entity_type_id)

    repo = VisionEntityStateDefinitionRepository(session)

    data = await repo.get_by_id(state_definition_id)
    if not data or data.entity_type_id != entity_type_id:
        raise ValueError(f"State definition {state_definition_id} not found")

    deleted = await repo.delete_if_unused(state_definition_id)
    if not deleted:
        raise ValueError(
            "Cannot delete state definition: entities are currently using this state"
        )

    if deleted:
        logger.info(
            "[Vision Entity] Deleted state definition",
            extra={"state_definition_id": str(state_definition_id)},
        )
    return deleted


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------


def _build_entity_response(data: VisionEntityData) -> EntityResponse:
    return EntityResponse(
        id=data.id,
        project_id=data.project_id,
        entity_type_id=data.entity_type_id,
        name=data.name,
        current_state_id=data.current_state_id,
        current_state_since=data.current_state_since,
        entity_metadata=data.entity_metadata,
        is_active=data.is_active,
        created_at=data.created_at,
        updated_at=data.updated_at,
    )


async def create_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    request: CreateEntityRequest,
) -> EntityResponse:
    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)

    existing = await entity_repo.get_by_project_type_and_name(
        project_id, request.entity_type_id, request.name
    )
    if existing:
        raise ValueError(
            f"Entity with name '{request.name}' already exists for this type in this project"
        )

    default_states = await sd_repo.list_by_entity_type(request.entity_type_id)
    default_state = next((s for s in default_states if s.is_default), None)

    now = datetime.now(timezone.utc)
    record = VisionEntityData(
        id=uuid.uuid4(),
        project_id=project_id,
        entity_type_id=request.entity_type_id,
        name=request.name,
        current_state_id=default_state.id if default_state else None,
        current_state_since=now if default_state else None,
        entity_metadata=request.entity_metadata,
        is_active=True,
        created_at=now,
    )

    await entity_repo.create(record)
    logger.info(
        "[Vision Entity] Created entity",
        extra={"entity_id": str(record.id), "project_id": str(project_id)},
    )
    return _build_entity_response(record)


async def get_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> EntityResponse:
    repo = VisionEntityRepository(session)

    data = await repo.get_by_id(entity_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    return _build_entity_response(data)


async def list_entities(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_type_id: uuid.UUID | None = None,
    current_state_id: uuid.UUID | None = None,
) -> ListEntitiesResponse:
    repo = VisionEntityRepository(session)

    entities = await repo.list_by_project(
        project_id,
        entity_type_id=entity_type_id,
        current_state_id=current_state_id,
    )

    items = [_build_entity_response(e) for e in entities]
    return ListEntitiesResponse(items=items, total=len(items))


async def update_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityRequest,
) -> EntityResponse:
    repo = VisionEntityRepository(session)

    data = await repo.get_by_id(entity_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    updates: dict[str, object] = {}
    if request.name is not None:
        existing = await repo.get_by_project_type_and_name(
            project_id, data.entity_type_id, request.name
        )
        if existing and existing.id != entity_id:
            raise ValueError(
                f"Entity with name '{request.name}' already exists for this type in this project"
            )
        updates["name"] = request.name
    if request.entity_metadata is not None:
        updates["entity_metadata"] = request.entity_metadata
    if request.is_active is not None:
        updates["is_active"] = request.is_active

    if not updates:
        return _build_entity_response(data)

    updated = await repo.update(entity_id, **updates)
    if not updated:
        raise ValueError(f"Entity {entity_id} not found")

    logger.info(
        "[Vision Entity] Updated entity",
        extra={"entity_id": str(entity_id)},
    )
    return _build_entity_response(updated)


async def update_entity_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: UpdateEntityStateRequest,
) -> EntityResponse:
    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)

    data = await entity_repo.get_by_id(entity_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    state_def = await sd_repo.get_by_id(request.state_definition_id)
    if not state_def or state_def.entity_type_id != data.entity_type_id:
        raise ValueError(
            f"State definition {request.state_definition_id} not found or does not belong to this entity type"
        )

    updated = await entity_repo.update(
        entity_id,
        current_state_id=request.state_definition_id,
        current_state_since=datetime.now(timezone.utc),
    )
    if not updated:
        raise ValueError(f"Entity {entity_id} not found")

    logger.info(
        "[Vision Entity] Updated entity state",
        extra={
            "entity_id": str(entity_id),
            "state_definition_id": str(request.state_definition_id),
        },
    )
    return _build_entity_response(updated)


async def delete_entity(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> bool:
    repo = VisionEntityRepository(session)

    data = await repo.get_by_id(entity_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    deleted = await repo.delete(entity_id)
    if deleted:
        logger.info(
            "[Vision Entity] Deleted entity",
            extra={"entity_id": str(entity_id)},
        )
    return deleted
