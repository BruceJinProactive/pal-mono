"""Tests for vision observation rule workflow."""

import uuid
from datetime import datetime, timezone
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


class TestHandleStateChangeRules:

    @pytest.mark.asyncio
    async def test_table_cleanness_dirty_to_clean_creates_rule_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id)
        state_change = _make_state_change(entity_id=entity.id)
        event: object | None = None

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
        assert event.event_metadata == {}

    @pytest.mark.asyncio
    async def test_table_occupied_empty_to_occupied_creates_rule_event(self) -> None:
        session = AsyncMock()
        entity = _make_entity()
        rule = _make_rule(project_id=entity.project_id, rule_type="table_occupied")
        state_change = _make_state_change(entity_id=entity.id)
        object.__setattr__(
            state_change, "event_metadata", {"definition_type": "occupation"}
        )
        event: object | None = None

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
                "occupied",
                previous_state_name="empty",
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
        assert event.event_metadata == {}

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
