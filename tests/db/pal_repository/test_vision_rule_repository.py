"""Tests for db.pal_repository.VisionRuleRepository."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.vision_rule import VisionRuleData
from db.pal_repository.vision_rule import VisionRuleRepository
from db.tables.vision_rules import VisionRule


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VisionRuleRepository:
    return VisionRuleRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID, sample_project_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=VisionRule)
    row.id = sample_id
    row.project_id = sample_project_id
    row.name = "Table must be clean"
    row.description = "Check table cleanness"
    row.type = MagicMock()
    row.type.value = "table_cleanness"
    row.severity = "high"
    row.is_active = True
    row.rule_metadata = {"threshold": 0.8}
    row.created_at = None
    row.updated_at = None
    return row


@pytest.fixture
def sample_data(sample_id: uuid.UUID, sample_project_id: uuid.UUID) -> VisionRuleData:
    return VisionRuleData(
        id=sample_id,
        project_id=sample_project_id,
        name="Table must be clean",
        type="table_cleanness",
        severity="high",
        is_active=True,
        rule_metadata={"threshold": 0.8},
        description="Check table cleanness",
    )


class TestCreate:

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_data: VisionRuleData,
    ) -> None:
        await repo.create(sample_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_data: VisionRuleData,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        with pytest.raises(Exception):
            await repo.create(sample_data)
        mock_session.rollback.assert_awaited_once()


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VisionRuleData)
        assert data.id == sample_id
        assert data.name == "Table must be clean"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestGetByIdForAccount:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id_for_account(sample_id, uuid.uuid4())

        assert isinstance(data, VisionRuleData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id_for_account(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        data = await repo.get_by_id_for_account(uuid.uuid4(), uuid.uuid4())
        assert data is None
        mock_session.rollback.assert_awaited_once()


class TestListByAccount:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4())

        assert len(results) == 1
        assert isinstance(results[0], VisionRuleData)

    @pytest.mark.asyncio
    async def test_filters_by_project_id(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4(), project_id=uuid.uuid4())
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filters_by_is_active(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4(), is_active=True)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        results = await repo.list_by_account(uuid.uuid4())
        assert results == []
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_execute_result = MagicMock()
        mock_get_result = MagicMock()
        mock_get_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.side_effect = [mock_execute_result, mock_get_result]

        result = await repo.update(sample_id, name="Updated name")

        assert result is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("update failed")

        with pytest.raises(Exception):
            await repo.update(sample_id, name="Updated")
        mock_session.rollback.assert_awaited_once()


class TestDeleteForAccount:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        result = await repo.delete_for_account(sample_id, uuid.uuid4())

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await repo.delete_for_account(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete_for_account(sample_id, uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestVerifyProjectBelongsToAccount:

    @pytest.mark.asyncio
    async def test_returns_true_when_owned(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project_id
        mock_session.execute.return_value = mock_result

        result = await repo.verify_project_belongs_to_account(
            sample_project_id, uuid.uuid4()
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_owned(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.verify_project_belongs_to_account(
            uuid.uuid4(), uuid.uuid4()
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_db_error(
        self,
        repo: VisionRuleRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = Exception("connection error")

        result = await repo.verify_project_belongs_to_account(
            uuid.uuid4(), uuid.uuid4()
        )
        assert result is False
        mock_session.rollback.assert_awaited_once()
