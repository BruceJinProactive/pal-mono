from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository import (
    VisionEntityTypeRepository,
    VisionRuleEventRepository,
    VisionRuleRepository,
    VisionStateChangeEventRepository,
)
from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.data_classes.vision_rule import VisionRuleData
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.vision_state_metadata import get_current_states_metadata
from utils.log import logger

_DURATION_QUANTUM = Decimal("0.0001")
_ZERO_DURATION = Decimal("0.0")


@dataclass(frozen=True)
class RuleWorkflow:
    entity_type_name: str
    previous_state: str
    trigger_state: str
    state_definition_type: str | None
    handler: Callable[
        [
            VisionRuleEventRepository,
            VisionStateChangeEventRepository,
            VisionEntityData,
            VisionStateChangeEventData,
            str,
            str | None,
            VisionRuleData,
            RuleWorkflow,
        ],
        Awaitable[None],
    ]


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    raw_value = value.strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"

    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _duration_minutes(started_at: datetime | None, ended_at: datetime) -> Decimal:
    if started_at is None:
        return _ZERO_DURATION

    start = _as_utc(started_at)
    end = _as_utc(ended_at)
    delta = end - start
    total_microseconds = (
        delta.days * 24 * 60 * 60 + delta.seconds
    ) * 1_000_000 + delta.microseconds
    if total_microseconds <= 0:
        return _ZERO_DURATION

    minutes = Decimal(total_microseconds) / Decimal(60_000_000)
    return minutes.quantize(_DURATION_QUANTUM)


def _uuid_matches(raw_value: object, expected: uuid.UUID | None) -> bool:
    if expected is None:
        return True
    if isinstance(raw_value, uuid.UUID):
        return raw_value == expected
    if isinstance(raw_value, str):
        try:
            return uuid.UUID(raw_value) == expected
        except ValueError:
            return False
    return False


def _metadata_state_matches(
    current_state: Mapping[str, object],
    previous_state_id: uuid.UUID | None,
    previous_state_name: str,
) -> bool:
    state_id = current_state.get("state_definition_id")
    if not _uuid_matches(state_id, previous_state_id):
        return False

    state_name = current_state.get("state")
    return not isinstance(state_name, str) or state_name == previous_state_name


def _previous_state_started_at_from_entity(
    entity: VisionEntityData,
    definition_type: str | None,
    previous_state_id: uuid.UUID | None,
    previous_state_name: str,
) -> datetime | None:
    if definition_type is not None:
        current_states = get_current_states_metadata(entity.entity_metadata)
        current_state = current_states.get(definition_type)
        if isinstance(current_state, Mapping) and _metadata_state_matches(
            current_state,
            previous_state_id,
            previous_state_name,
        ):
            return _parse_datetime(current_state.get("current_state_since"))

    if previous_state_id is not None and entity.current_state_id != previous_state_id:
        return None
    return entity.current_state_since


async def _previous_state_duration(
    state_event_repo: VisionStateChangeEventRepository,
    entity: VisionEntityData,
    state_change_event: VisionStateChangeEventData,
    workflow: RuleWorkflow,
    definition_type: str | None,
) -> Decimal:
    started_at = _previous_state_started_at_from_entity(
        entity=entity,
        definition_type=definition_type,
        previous_state_id=state_change_event.previous_state_id,
        previous_state_name=workflow.previous_state,
    )

    if started_at is None and state_change_event.previous_state_id is not None:
        previous_event = await state_event_repo.get_latest_by_entity_state_before(
            entity_id=state_change_event.entity_id,
            state_id=state_change_event.previous_state_id,
            before=state_change_event.observed_at,
            definition_type=definition_type,
        )
        if previous_event is not None:
            started_at = previous_event.observed_at

    return _duration_minutes(started_at, state_change_event.observed_at)


async def _handle_state_transition_rule(
    rule_event_repo: VisionRuleEventRepository,
    state_event_repo: VisionStateChangeEventRepository,
    entity: VisionEntityData,
    state_change_event: VisionStateChangeEventData,
    state_name: str,
    previous_state_name: str | None,
    rule: VisionRuleData,
    workflow: RuleWorkflow,
) -> None:
    if (
        previous_state_name != workflow.previous_state
        or state_name != workflow.trigger_state
    ):
        return

    event_metadata = state_change_event.event_metadata or {}
    event_definition_type = event_metadata.get("definition_type")
    definition_type = (
        event_definition_type
        if isinstance(event_definition_type, str)
        else workflow.state_definition_type
    )
    duration = await _previous_state_duration(
        state_event_repo=state_event_repo,
        entity=entity,
        state_change_event=state_change_event,
        workflow=workflow,
        definition_type=definition_type,
    )

    await rule_event_repo.create(
        VisionRuleEventData(
            id=uuid.uuid4(),
            rule_id=rule.id,
            entity_id=entity.id,
            state_change_event_id=state_change_event.id,
            severity=rule.severity,
            duration=duration,
            triggered_at=state_change_event.observed_at,
        )
    )
    logger.info(
        "[Vision RuleWorkflow] State transition rule triggered",
        extra={
            "rule_id": str(rule.id),
            "rule_type": rule.type,
            "entity_id": str(entity.id),
            "state_change_event_id": str(state_change_event.id),
            "previous_state_name": previous_state_name,
            "state_name": state_name,
            "duration": str(duration),
        },
    )


RULE_TYPE_WORKFLOWS: dict[str, RuleWorkflow] = {
    "table_cleanness": RuleWorkflow(
        entity_type_name="table",
        previous_state="dirty",
        trigger_state="clean",
        state_definition_type="cleanliness",
        handler=_handle_state_transition_rule,
    ),
    "table_occupied": RuleWorkflow(
        entity_type_name="table",
        previous_state="empty",
        trigger_state="occupied",
        state_definition_type="occupation",
        handler=_handle_state_transition_rule,
    ),
    "table_touch": RuleWorkflow(
        entity_type_name="table",
        previous_state="no_table_touch",
        trigger_state="table_touch",
        state_definition_type="touch",
        handler=_handle_state_transition_rule,
    ),
    "glove_usage": RuleWorkflow(
        entity_type_name="staff",
        previous_state="with_gloves",
        trigger_state="without_gloves",
        state_definition_type="glove_usage",
        handler=_handle_state_transition_rule,
    ),
    "food_container_on_ground": RuleWorkflow(
        entity_type_name="container",
        previous_state="not_on_ground",
        trigger_state="container_on_ground",
        state_definition_type="location",
        handler=_handle_state_transition_rule,
    ),
    "manager_in_room": RuleWorkflow(
        entity_type_name="manager_office",
        previous_state="no_person",
        trigger_state="person_present",
        state_definition_type="presence",
        handler=_handle_state_transition_rule,
    ),
    "staff_at_front_desk": RuleWorkflow(
        entity_type_name="front_desk",
        previous_state="no_people",
        trigger_state="people_present",
        state_definition_type="presence",
        handler=_handle_state_transition_rule,
    ),
    "guest_visiting_menu_board": RuleWorkflow(
        entity_type_name="menu_board",
        previous_state="no_people",
        trigger_state="people_present",
        state_definition_type="presence",
        handler=_handle_state_transition_rule,
    ),
    "empty_tray": RuleWorkflow(
        entity_type_name="food_tray",
        previous_state="not_empty",
        trigger_state="empty",
        state_definition_type=None,
        handler=_handle_state_transition_rule,
    ),
}


async def _resolve_entity_type_name(
    session: AsyncSession,
    entity: VisionEntityData,
    entity_type_name: str | None,
) -> str | None:
    if entity_type_name is not None:
        return entity_type_name

    type_repo = VisionEntityTypeRepository(session)
    entity_type = await type_repo.get_by_id(entity.entity_type_id)
    if not entity_type:
        return None
    return entity_type.name


async def handle_state_change_rules(
    session: AsyncSession,
    entity: VisionEntityData,
    state_change_event: VisionStateChangeEventData,
    state_name: str,
    previous_state_name: str | None = None,
    entity_type_name: str | None = None,
) -> None:
    event_metadata = state_change_event.event_metadata or {}
    if event_metadata.get("is_test") is True:
        return

    resolved_entity_type_name = await _resolve_entity_type_name(
        session=session,
        entity=entity,
        entity_type_name=entity_type_name,
    )
    if resolved_entity_type_name is None:
        return

    rule_repo = VisionRuleRepository(session)
    rule_event_repo = VisionRuleEventRepository(session)
    state_event_repo = VisionStateChangeEventRepository(session)
    rules = await rule_repo.list_by_project(entity.project_id, is_active=True)

    for rule in rules:
        workflow = RULE_TYPE_WORKFLOWS.get(rule.type)
        if workflow is None:
            continue

        if resolved_entity_type_name != workflow.entity_type_name:
            continue

        event_definition_type = event_metadata.get("definition_type")
        if (
            workflow.state_definition_type is not None
            and isinstance(event_definition_type, str)
            and event_definition_type != workflow.state_definition_type
        ):
            continue

        await workflow.handler(
            rule_event_repo,
            state_event_repo,
            entity,
            state_change_event,
            state_name,
            previous_state_name,
            rule,
            workflow,
        )
