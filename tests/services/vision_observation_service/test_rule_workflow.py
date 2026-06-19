"""Tests for vision observation rule workflow."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.pal_repository.data_classes.vision_rule import VisionRuleData
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.vision_observation_service._workflow import handle_state_change_rules

MODULE = "services.vision_observation_service._workflow"


def _make_entity(
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> VisionEntityData:
    return VisionEntityData(
        id=entity_id or uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        entity_type_id=uuid.uuid4(),
        name="Table 1",
        is_active=True,
        entity_metadata={},
        created_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
    )


def _make_rule(
    project_id: uuid.UUID,
    rule_type: str = "table_cleanness",
) -> VisionRuleData:
    return VisionRuleData(
        id=uuid.uuid4(),
        project_id=project_id,
        name="Dirty table",
        type=rule_type,
        severity="high",
        is_active=True,
        rule_metadata={},
    )


def _make_state_change(
    entity_id: uuid.UUID,
    new_state_id: uuid.UUID | None = None,
) -> VisionStateChangeEventData:
    return VisionStateChangeEventData(
        id=uuid.uuid4(),
        entity_id=entity_id,
        new_state_id=new_state_id or uuid.uuid4(),
        observed_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        camera_config_id=uuid.uuid4(),
        previous_state_id=uuid.uuid4(),
        confidence=0.91,
        frame_s3_key="cameras/table/frame.jpg",
    )


def _set_current_state_since(
    entity: VisionEntityData,
    definition_type: str,
    state_id: uuid.UUID,
    state_name: str,
    since: datetime,
) -> None:
    object.__setattr__(entity, "current_state_id", state_id)
    object.__setattr__(entity, "current_state_since", since)
    object.__setattr__(
        entity,
        "entity_metadata",
        {
            "current_states": {
                definition_type: {
                    "state_definition_id": str(state_id),
                    "state": state_name,
                    "current_state_since": since.isoformat(),
                    "observed_at": since.isoformat(),
                }
            }
        },
    )


def _duration_metadata(
    previous_state_name: str,
    state_name: str,
    started_at: datetime,
    ended_at: datetime,
    start_event_id: uuid.UUID,
    end_event_id: uuid.UUID,
) -> dict[str, str]:
    return {
        "duration_state": previous_state_name,
        "proof_state": previous_state_name,
        "trigger_state": state_name,
        "duration_start_state_change_event_id": str(start_event_id),
        "duration_end_state_change_event_id": str(end_event_id),
        "duration_started_at": started_at.isoformat(),
        "duration_ended_at": ended_at.isoformat(),
    }


class TestHandleStateChangeRules:

    @pytest.mark.asyncio
    async def test_table_cleanness_dirty_to_clean_creates_rule_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)
        assert state_change.previous_state_id is not None
        started_at = state_change.observed_at - timedelta(minutes=12, seconds=30)
        previous_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity.id,
            new_state_id=state_change.previous_state_id,
            observed_at=started_at,
            event_metadata={"definition_type": "cleanliness"},
        )
        _set_current_state_since(
            entity=entity,
            definition_type="cleanliness",
            state_id=state_change.previous_state_id,
            state_name="dirty",
            since=started_at,
        )
        event: object | None = None

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as state_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()
            state_repo_cls.return_value.get_latest_by_entity_state_before = AsyncMock(
                return_value=previous_event
            )

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="table",
            )

            rule_repo_cls.return_value.list_by_project.assert_awaited_once_with(
                entity.project_id,
                is_active=True,
            )
            event_repo_cls.return_value.create.assert_awaited_once()
            event = event_repo_cls.return_value.create.call_args.args[0]

        assert isinstance(event, VisionRuleEventData)
        assert event.rule_id == rule.id
        assert event.entity_id == entity.id
        assert event.state_change_event_id == state_change.id
        assert event.severity == rule.severity
        assert event.triggered_at == state_change.observed_at
        assert event.duration == Decimal("12.5000")
        assert event.event_metadata == _duration_metadata(
            "dirty",
            "clean",
            started_at,
            state_change.observed_at,
            previous_event.id,
            state_change.id,
        )

    @pytest.mark.asyncio
    async def test_duration_falls_back_to_previous_state_change_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)
        assert state_change.previous_state_id is not None
        previous_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity.id,
            new_state_id=state_change.previous_state_id,
            observed_at=state_change.observed_at - timedelta(minutes=7, seconds=30),
            event_metadata={"definition_type": "cleanliness"},
        )
        event: object | None = None

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as state_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()
            state_repo_cls.return_value.get_latest_by_entity_state_before = AsyncMock(
                return_value=previous_event
            )

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="table",
            )

            state_repo_cls.return_value.get_latest_by_entity_state_before.assert_awaited_once_with(
                entity_id=entity.id,
                state_id=state_change.previous_state_id,
                before=state_change.observed_at,
                definition_type="cleanliness",
            )
            event_repo_cls.return_value.create.assert_awaited_once()
            event = event_repo_cls.return_value.create.call_args.args[0]

        assert isinstance(event, VisionRuleEventData)
        assert event.duration == Decimal("7.5000")
        assert event.event_metadata == _duration_metadata(
            "dirty",
            "clean",
            previous_event.observed_at,
            state_change.observed_at,
            previous_event.id,
            state_change.id,
        )

    @pytest.mark.parametrize(
        (
            "rule_type",
            "entity_type_name",
            "previous_state_name",
            "state_name",
            "definition_type",
        ),
        [
            (
                "table_occupied",
                "table",
                "occupied",
                "empty",
                "occupation",
            ),
            (
                "table_touch",
                "table",
                "table_touch",
                "no_table_touch",
                "touch",
            ),
            (
                "glove_usage",
                "staff",
                "without_gloves",
                "with_gloves",
                "glove_usage",
            ),
            (
                "food_container_on_ground",
                "container",
                "container_on_ground",
                "not_on_ground",
                "location",
            ),
            (
                "manager_in_room",
                "manager_office",
                "person_present",
                "no_person",
                "presence",
            ),
            (
                "staff_at_front_desk",
                "front_desk",
                "people_present",
                "no_people",
                "presence",
            ),
            (
                "guest_visiting_menu_board",
                "menu_board",
                "people_present",
                "no_people",
                "presence",
            ),
            (
                "empty_tray",
                "food_tray",
                "empty",
                "not_empty",
                "fullness",
            ),
            (
                "people_queued_up",
                "queue",
                "people_present",
                "no_people",
                "presence",
            ),
            (
                "floor_cleanness",
                "floor",
                "dirty",
                "clean",
                "cleanliness",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_state_transition_workflows_create_rule_event(
        self,
        rule_type: str,
        entity_type_name: str,
        previous_state_name: str,
        state_name: str,
        definition_type: str,
    ) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id, rule_type=rule_type)
        state_change = _make_state_change(entity_id=entity.id)
        assert state_change.previous_state_id is not None
        started_at = state_change.observed_at - timedelta(minutes=5)
        previous_event = VisionStateChangeEventData(
            id=uuid.uuid4(),
            entity_id=entity.id,
            new_state_id=state_change.previous_state_id,
            observed_at=started_at,
            event_metadata={"definition_type": definition_type},
        )
        _set_current_state_since(
            entity=entity,
            definition_type=definition_type,
            state_id=state_change.previous_state_id,
            state_name=previous_state_name,
            since=started_at,
        )
        object.__setattr__(
            state_change, "event_metadata", {"definition_type": definition_type}
        )
        event: object | None = None

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as state_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()
            state_repo_cls.return_value.get_latest_by_entity_state_before = AsyncMock(
                return_value=previous_event
            )

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                state_name,
                previous_state_name=previous_state_name,
                entity_type_name=entity_type_name,
            )

            rule_repo_cls.return_value.list_by_project.assert_awaited_once_with(
                entity.project_id,
                is_active=True,
            )
            event_repo_cls.return_value.create.assert_awaited_once()
            event = event_repo_cls.return_value.create.call_args.args[0]

        assert isinstance(event, VisionRuleEventData)
        assert event.rule_id == rule.id
        assert event.entity_id == entity.id
        assert event.state_change_event_id == state_change.id
        assert event.severity == rule.severity
        assert event.triggered_at == state_change.observed_at
        assert event.duration == Decimal("5.0000")
        assert event.event_metadata == _duration_metadata(
            previous_state_name,
            state_name,
            started_at,
            state_change.observed_at,
            previous_event.id,
            state_change.id,
        )

    @pytest.mark.asyncio
    async def test_clean_without_dirty_previous_state_does_not_create_rule_event(
        self,
    ) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="clean",
                entity_type_name="table",
            )

            event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_table_cleanness_rule_is_ignored(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id, rule_type="other_rule")
        state_change = _make_state_change(entity_id=entity.id)

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="table",
            )

            event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_table_entity_type_does_not_create_rule_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="counter",
            )

            rule_repo_cls.return_value.list_by_project.assert_awaited_once_with(
                entity.project_id,
                is_active=True,
            )
            event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mismatched_definition_type_does_not_create_rule_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)
        object.__setattr__(
            state_change, "event_metadata", {"definition_type": "occupation"}
        )

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="table",
            )

            event_repo_cls.return_value.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_null_event_metadata_is_treated_as_not_test(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)
        assert state_change.previous_state_id is not None
        _set_current_state_since(
            entity=entity,
            definition_type="cleanliness",
            state_id=state_change.previous_state_id,
            state_name="dirty",
            since=state_change.observed_at - timedelta(minutes=3),
        )
        object.__setattr__(state_change, "event_metadata", None)

        with (
            patch(f"{MODULE}.VisionRuleRepository") as rule_repo_cls,
            patch(f"{MODULE}.VisionRuleEventRepository") as event_repo_cls,
        ):
            rule_repo_cls.return_value.list_by_project = AsyncMock(return_value=[rule])
            event_repo_cls.return_value.create = AsyncMock()

            await handle_state_change_rules(
                session,
                entity,
                state_change,
                "clean",
                previous_state_name="dirty",
                entity_type_name="table",
            )

            event_repo_cls.return_value.create.assert_awaited_once()
