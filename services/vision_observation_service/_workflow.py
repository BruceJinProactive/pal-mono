from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository import (
    VisionEntityTypeRepository,
    VisionRuleEventRepository,
    VisionRuleRepository,
)
from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.data_classes.vision_rule import VisionRuleData
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from utils.log import logger


@dataclass(frozen=True)
class RuleWorkflow:
    entity_type_name: str
    previous_state: str
    trigger_state: str
    state_definition_type: str | None
    handler: Callable[
        [
            VisionRuleEventRepository,
            VisionEntityData,
            VisionStateChangeEventData,
            str,
            str | None,
            VisionRuleData,
            RuleWorkflow,
        ],
        Awaitable[None],
    ]


async def _handle_table_cleanness_rule(
    rule_event_repo: VisionRuleEventRepository,
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

    await rule_event_repo.create(
        VisionRuleEventData(
            id=uuid.uuid4(),
            rule_id=rule.id,
            entity_id=entity.id,
            state_change_event_id=state_change_event.id,
            severity=rule.severity,
            triggered_at=state_change_event.observed_at,
        )
    )
    logger.info(
        "[Vision RuleWorkflow] Table cleanness rule triggered",
        extra={
            "rule_id": str(rule.id),
            "entity_id": str(entity.id),
            "state_change_event_id": str(state_change_event.id),
            "state_name": state_name,
        },
    )


RULE_TYPE_WORKFLOWS: dict[str, RuleWorkflow] = {
    "table_cleanness": RuleWorkflow(
        entity_type_name="table",
        previous_state="dirty",
        trigger_state="clean",
        state_definition_type="cleanliness",
        handler=_handle_table_cleanness_rule,
    )
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
            entity,
            state_change_event,
            state_name,
            previous_state_name,
            rule,
            workflow,
        )
