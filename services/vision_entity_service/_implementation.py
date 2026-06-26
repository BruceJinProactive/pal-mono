from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_entity import (
    CreateEntityRequest,
    CreateEntityTypeRequest,
    CreateStateDefinitionRequest,
    EntityCurrentStateResponse,
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
    VisionCameraEntityRepository,
    VisionEntityRepository,
    VisionEntityStateDefinitionRepository,
    VisionEntityTypeRepository,
    VisionStateChangeEventRepository,
)
from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.data_classes.vision_entity_state_definition import (
    VisionEntityStateDefinitionData,
)
from db.pal_repository.data_classes.vision_entity_type import VisionEntityTypeData
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.vision_observation_service._workflow import handle_state_change_rules
from services.vision_state_metadata import (
    clear_current_state_metadata,
    current_state_id_from_metadata,
    current_state_metadata_key,
    get_current_states_metadata,
    set_current_state_metadata,
)
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

    entity_repo = VisionEntityRepository(session)
    mapping_repo = VisionCameraEntityRepository(session)
    entities = await entity_repo.list_by_entity_type(entity_type_id)
    for entity in entities:
        await mapping_repo.delete_by_entity(entity.id)
        await entity_repo.delete(entity.id)
    if entities:
        logger.info(
            "[Vision Entity] Deleted entities for entity type",
            extra={"entity_type_id": str(entity_type_id), "count": len(entities)},
        )

    state_repo = VisionEntityStateDefinitionRepository(session)
    removed_states = await state_repo.delete_by_entity_type(entity_type_id)
    if removed_states > 0:
        logger.info(
            "[Vision Entity] Deleted state definitions for entity type",
            extra={"entity_type_id": str(entity_type_id), "count": removed_states},
        )

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
        definition_type=data.definition_type,
        sort_order=data.sort_order,
        is_default=data.is_default,
        is_active=data.is_active,
        criteria=data.criteria,
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
        await repo.clear_default_for_entity_type(
            entity_type_id, request.definition_type
        )

    record = VisionEntityStateDefinitionData(
        id=uuid.uuid4(),
        entity_type_id=entity_type_id,
        name=request.name,
        display_name=request.display_name,
        color=request.color,
        definition_type=request.definition_type,
        sort_order=request.sort_order,
        is_default=request.is_default,
        is_active=request.is_active,
        criteria=request.criteria,
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
    if "definition_type" in provided:
        updates["definition_type"] = request.definition_type
    if "sort_order" in provided:
        updates["sort_order"] = request.sort_order
    if "is_default" in provided:
        updates["is_default"] = request.is_default
    if "is_active" in provided:
        updates["is_active"] = request.is_active
    if "criteria" in provided:
        updates["criteria"] = request.criteria

    if not updates:
        return _build_state_definition_response(data)

    resulting_definition_type = (
        request.definition_type
        if request.definition_type is not None
        else data.definition_type
    )
    resulting_is_default = (
        request.is_default if request.is_default is not None else data.is_default
    )
    if resulting_is_default and (
        updates.get("is_default") is True or "definition_type" in updates
    ):
        await repo.clear_default_for_entity_type(
            entity_type_id,
            resulting_definition_type,
            except_state_definition_id=state_definition_id,
        )

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


def _metadata_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _metadata_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _build_current_state_response(
    current_state: object,
) -> EntityCurrentStateResponse | None:
    if not isinstance(current_state, Mapping):
        return None

    state_definition_id = _metadata_uuid(current_state.get("state_definition_id"))
    if state_definition_id is None:
        return None

    raw_state = current_state.get("state")
    return EntityCurrentStateResponse(
        state_definition_id=state_definition_id,
        state=raw_state if isinstance(raw_state, str) else None,
        current_state_since=_metadata_datetime(
            current_state.get("current_state_since")
        ),
        observed_at=_metadata_datetime(current_state.get("observed_at")),
    )


def _build_current_states_response(
    entity_metadata: dict[str, object],
) -> dict[str, EntityCurrentStateResponse]:
    current_states = get_current_states_metadata(entity_metadata)
    response: dict[str, EntityCurrentStateResponse] = {}
    for definition_type, current_state in current_states.items():
        current_state_response = _build_current_state_response(current_state)
        if current_state_response is not None:
            response[definition_type] = current_state_response
    return response


def _first_current_state_metadata(
    current_states: dict[str, object],
) -> tuple[uuid.UUID | None, datetime | None]:
    for definition_type, current_state in current_states.items():
        state_definition_id = current_state_id_from_metadata(
            current_states, definition_type
        )
        if state_definition_id is None:
            continue

        current_state_since = None
        if isinstance(current_state, Mapping):
            current_state_since = _metadata_datetime(
                current_state.get("current_state_since")
            )

        return state_definition_id, current_state_since

    return None, None


def _build_entity_response(data: VisionEntityData) -> EntityResponse:
    return EntityResponse(
        id=data.id,
        project_id=data.project_id,
        entity_type_id=data.entity_type_id,
        name=data.name,
        current_state_id=data.current_state_id,
        current_state_since=data.current_state_since,
        current_states=_build_current_states_response(data.entity_metadata),
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

    default_states = await sd_repo.list_by_entity_type(
        request.entity_type_id, is_active=True
    )
    default_states_by_type: dict[str, VisionEntityStateDefinitionData] = {}
    for state_def in default_states:
        if not state_def.is_default:
            continue
        definition_type = current_state_metadata_key(state_def.definition_type)
        default_states_by_type.setdefault(definition_type, state_def)
    legacy_default_state = next(iter(default_states_by_type.values()), None)

    now = datetime.now(timezone.utc)
    entity_metadata = dict(request.entity_metadata)
    for definition_type, default_state in default_states_by_type.items():
        entity_metadata = set_current_state_metadata(
            entity_metadata,
            definition_type,
            default_state.id,
            default_state.name,
            now,
            now,
        )
    record = VisionEntityData(
        id=uuid.uuid4(),
        project_id=project_id,
        entity_type_id=request.entity_type_id,
        name=request.name,
        current_state_id=legacy_default_state.id if legacy_default_state else None,
        current_state_since=now if legacy_default_state else None,
        entity_metadata=entity_metadata,
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
    if (
        not state_def
        or state_def.entity_type_id != data.entity_type_id
        or not state_def.is_active
    ):
        raise ValueError(
            f"State definition {request.state_definition_id} not found or does not belong to this entity type"
        )

    now = datetime.now(timezone.utc)
    definition_type = current_state_metadata_key(state_def.definition_type)
    entity_metadata = dict(data.entity_metadata)
    current_states = get_current_states_metadata(entity_metadata)
    previous_state_id = current_state_id_from_metadata(current_states, definition_type)
    previous_state_def = None
    if previous_state_id is not None:
        previous_state_def = await sd_repo.get_by_id(previous_state_id)
    elif data.current_state_id is not None:
        legacy_previous_state_def = await sd_repo.get_by_id(data.current_state_id)
        if (
            legacy_previous_state_def
            and current_state_metadata_key(legacy_previous_state_def.definition_type)
            == definition_type
        ):
            previous_state_id = data.current_state_id
            previous_state_def = legacy_previous_state_def

    if request.state_definition_id == previous_state_id:
        return _build_entity_response(data)

    entity_metadata = set_current_state_metadata(
        entity_metadata,
        definition_type,
        request.state_definition_id,
        state_def.name,
        now,
        now,
    )

    updated = await entity_repo.update(
        entity_id,
        current_state_id=request.state_definition_id,
        current_state_since=now,
        entity_metadata=entity_metadata,
    )
    if not updated:
        raise ValueError(f"Entity {entity_id} not found")

    event_repo = VisionStateChangeEventRepository(session)
    state_change_event = VisionStateChangeEventData(
        id=uuid.uuid4(),
        entity_id=entity_id,
        new_state_id=request.state_definition_id,
        observed_at=now,
        event_metadata={"definition_type": definition_type},
        previous_state_id=previous_state_id,
    )
    await event_repo.create(state_change_event)
    await handle_state_change_rules(
        session=session,
        entity=data,
        state_change_event=state_change_event,
        state_name=state_def.name,
        previous_state_name=previous_state_def.name if previous_state_def else None,
    )

    logger.info(
        "[Vision Entity] Updated entity state",
        extra={
            "entity_id": str(entity_id),
            "state_definition_id": str(request.state_definition_id),
        },
    )
    return _build_entity_response(updated)


async def delete_entity_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    definition_type: str,
) -> EntityResponse:
    entity_repo = VisionEntityRepository(session)
    sd_repo = VisionEntityStateDefinitionRepository(session)

    data = await entity_repo.get_by_id(entity_id)
    if not data or data.project_id != project_id:
        raise ValueError(f"Entity {entity_id} not found")

    normalized_definition_type = current_state_metadata_key(definition_type)
    entity_metadata = dict(data.entity_metadata)
    current_states = get_current_states_metadata(entity_metadata)
    has_current_state_metadata = normalized_definition_type in current_states
    previous_state_id = current_state_id_from_metadata(
        current_states, normalized_definition_type
    )

    if previous_state_id is None and data.current_state_id is not None:
        legacy_previous_state_def = await sd_repo.get_by_id(data.current_state_id)
        if (
            legacy_previous_state_def
            and current_state_metadata_key(legacy_previous_state_def.definition_type)
            == normalized_definition_type
        ):
            previous_state_id = data.current_state_id

    if previous_state_id is None and not has_current_state_metadata:
        return _build_entity_response(data)

    entity_metadata = clear_current_state_metadata(
        entity_metadata,
        normalized_definition_type,
    )
    remaining_current_states = get_current_states_metadata(entity_metadata)
    current_state_id = data.current_state_id
    current_state_since = data.current_state_since

    if previous_state_id is not None and current_state_id == previous_state_id:
        current_state_id, current_state_since = _first_current_state_metadata(
            remaining_current_states
        )

    updated = await entity_repo.update(
        entity_id,
        current_state_id=current_state_id,
        current_state_since=current_state_since,
        entity_metadata=entity_metadata,
    )
    if not updated:
        raise ValueError(f"Entity {entity_id} not found")

    logger.info(
        "[Vision Entity] Deleted entity state",
        extra={
            "entity_id": str(entity_id),
            "definition_type": normalized_definition_type,
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

    mapping_repo = VisionCameraEntityRepository(session)
    removed_count = await mapping_repo.delete_by_entity(entity_id)
    if removed_count > 0:
        logger.info(
            "[Vision Entity] Deleted camera-entity mappings for entity",
            extra={"entity_id": str(entity_id), "count": removed_count},
        )

    deleted = await repo.delete(entity_id)
    if deleted:
        logger.info(
            "[Vision Entity] Deleted entity",
            extra={"entity_id": str(entity_id)},
        )
    return deleted
