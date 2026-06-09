"""Tests for vision_rule_service CRUD operations."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_rule import (
    CreateVisionRuleRequest,
    UpdateVisionRuleRequest,
)
from db.pal_repository.data_classes.vision_rule import VisionRuleData

MODULE = "services.vision_rule_service._implementation"

ACCOUNT_NAME = "test-account"
ACCOUNT_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


def _mock_account() -> Any:
    mock = MagicMock()
    mock.id = ACCOUNT_ID
    return mock


def _make_rule_data(**overrides: object) -> VisionRuleData:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": PROJECT_ID,
        "name": "Table must be clean",
        "type": "table_cleanness",
        "severity": "high",
        "is_active": True,
        "rule_metadata": {},
        "label": [],
        "description": None,
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(overrides)
    return VisionRuleData(**defaults)  # type: ignore[arg-type]


class TestCreateVisionRule:

    @pytest.mark.asyncio
    async def test_creates_rule(self) -> None:
        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Table must be clean",
            type="table_cleanness",
            severity="high",
            label=["cleanliness"],
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_project_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import create_vision_rule

            result = await create_vision_rule(session, request, ACCOUNT_NAME)

            assert result.name == "Table must be clean"
            assert result.type == "table_cleanness"
            assert result.label == ["cleanliness"]
            repo.create.assert_awaited_once()
            created_record = repo.create.call_args.args[0]
            assert created_record.label == ["cleanliness"]

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Test",
            type="table_cleanness",
            severity="high",
        )

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_rule_service._implementation import create_vision_rule

            with pytest.raises(ValueError, match="not found"):
                await create_vision_rule(session, request, "bad-account")

    @pytest.mark.asyncio
    async def test_raises_when_project_not_owned(self) -> None:
        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Test",
            type="table_cleanness",
            severity="high",
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_project_belongs_to_account.return_value = False
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import create_vision_rule

            with pytest.raises(ValueError, match="does not belong"):
                await create_vision_rule(session, request, ACCOUNT_NAME)


class TestGetVisionRule:

    @pytest.mark.asyncio
    async def test_returns_rule(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, label=["front-of-house"])

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import get_vision_rule

            result = await get_vision_rule(session, rule_id, ACCOUNT_NAME)

            assert result.id == rule_id
            assert result.label == ["front-of-house"]

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self) -> None:
        session = AsyncMock()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import get_vision_rule

            with pytest.raises(ValueError, match="not found"):
                await get_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)


class TestListVisionRules:

    @pytest.mark.asyncio
    async def test_returns_rules(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, label=["cleanliness", "priority"])
        unlabeled_rule_id = uuid.uuid4()
        unlabeled_rule_data = _make_rule_data(id=unlabeled_rule_id, label=[])

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = [rule_data, unlabeled_rule_data]
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import list_vision_rules

            result = await list_vision_rules(session, ACCOUNT_NAME)

            assert result.total == 2
            assert result.items[0].label == ["cleanliness", "priority"]
            assert result.items_by_label["cleanliness"][0].id == rule_id
            assert result.items_by_label["priority"][0].id == rule_id
            assert result.items_by_label["no-labeld"][0].id == unlabeled_rule_id

    @pytest.mark.asyncio
    async def test_groups_labels_once_per_rule(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, label=["priority", "priority", " "])

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = [rule_data]
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import list_vision_rules

            result = await list_vision_rules(session, ACCOUNT_NAME)

            assert list(result.items_by_label.keys()) == ["priority"]
            assert [rule.id for rule in result.items_by_label["priority"]] == [rule_id]

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_rule_service._implementation import list_vision_rules

            with pytest.raises(ValueError, match="not found"):
                await list_vision_rules(session, "bad-account")


class TestUpdateVisionRule:

    @pytest.mark.asyncio
    async def test_updates_rule(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id)
        updated_data = _make_rule_data(id=rule_id, name="Updated name")
        request = UpdateVisionRuleRequest(name="Updated name")

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            repo.update.return_value = updated_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            result = await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

            assert result.name == "Updated name"
            repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_op_when_no_fields(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id)
        request = UpdateVisionRuleRequest()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            result = await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

            assert result.id == rule_id
            repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self) -> None:
        session = AsyncMock()
        request = UpdateVisionRuleRequest(name="Updated")

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            with pytest.raises(ValueError, match="not found"):
                await update_vision_rule(session, uuid.uuid4(), request, ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_replaces_metadata(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, rule_metadata={"existing": "value"})
        updated_data = _make_rule_data(id=rule_id, rule_metadata={"new": "field"})
        request = UpdateVisionRuleRequest(rule_metadata={"new": "field"})

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            repo.update.return_value = updated_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

            call_kwargs = repo.update.call_args[1]
            assert call_kwargs["rule_metadata"] == {"new": "field"}

    @pytest.mark.asyncio
    async def test_replaces_labels(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, label=["old"])
        updated_data = _make_rule_data(id=rule_id, label=["new", "priority"])
        request = UpdateVisionRuleRequest(label=["new", "priority"])

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            repo.update.return_value = updated_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            result = await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

            assert result.label == ["new", "priority"]
            call_kwargs = repo.update.call_args[1]
            assert call_kwargs["label"] == ["new", "priority"]

    @pytest.mark.asyncio
    async def test_clears_labels(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()
        rule_data = _make_rule_data(id=rule_id, label=["old"])
        updated_data = _make_rule_data(id=rule_id, label=[])
        request = UpdateVisionRuleRequest(label=[])

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = rule_data
            repo.update.return_value = updated_data
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import update_vision_rule

            result = await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

            assert result.label == []
            call_kwargs = repo.update.call_args[1]
            assert call_kwargs["label"] == []


class TestDeleteVisionRule:

    @pytest.mark.asyncio
    async def test_deletes_rule(self) -> None:
        session = AsyncMock()
        rule_id = uuid.uuid4()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = True
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import delete_vision_rule

            await delete_vision_rule(session, rule_id, ACCOUNT_NAME)
            repo.delete_for_account.assert_awaited_once_with(rule_id, ACCOUNT_ID)

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self) -> None:
        session = AsyncMock()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = False
            mock_repo_cls.return_value = repo

            from services.vision_rule_service._implementation import delete_vision_rule

            with pytest.raises(ValueError, match="not found"):
                await delete_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)
