"""Tests for db.pal_repository.FAQRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only FAQData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.faq import FAQData
from db.pal_repository.faq import FAQRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> FAQRepository:
    return FAQRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.account_id = uuid.uuid4()
    row.question = "What are your hours?"
    row.answer = "9am to 5pm"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.project_id = None
    row.updated_at = None
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(sample_id)
        assert isinstance(data, FAQData)
        assert data.id == sample_id
        assert data.question == "What are your hours?"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByAccountId:

    @pytest.mark.asyncio
    async def test_returns_list_with_project(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_account_id(uuid.uuid4(), project_id=uuid.uuid4())
        assert len(results) == 1
        assert results[0].question == "What are your hours?"

    @pytest.mark.asyncio
    async def test_returns_list_without_project(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_account_id(uuid.uuid4())
        assert len(results) == 1
        statement = mock_session.execute.call_args.args[0]
        assert "faq.project_id IS NULL" in str(statement)

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_account_id(uuid.uuid4())


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)

        def populate_on_refresh(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.account_id = sample_orm_row.account_id
            row.question = sample_orm_row.question
            row.answer = sample_orm_row.answer
            row.created_at = sample_orm_row.created_at
            row.project_id = sample_orm_row.project_id
            row.updated_at = sample_orm_row.updated_at

        mock_session.refresh = AsyncMock(side_effect=populate_on_refresh)

        record = FAQData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            question="What are your hours?",
            answer="9am to 5pm",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        data = await repo.create(record)
        assert isinstance(data, FAQData)
        assert data.question == "What are your hours?"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        record = FAQData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            question="Q",
            answer="A",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(record)
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        data = await repo.update(uuid.uuid4(), question="New question?")
        assert data is not None
        assert sample_orm_row.question == "New question?"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.update(uuid.uuid4(), question="New?")
        assert result is None

    @pytest.mark.asyncio
    async def test_sets_field_to_none(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        data = await repo.update(uuid.uuid4(), project_id=None)
        assert data is not None
        assert sample_orm_row.project_id is None

    @pytest.mark.asyncio
    async def test_rejects_disallowed_field(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Cannot update field: id"):
            await repo.update(uuid.uuid4(), id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.update(uuid.uuid4(), answer="New answer")
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)
        assert await repo.delete(uuid.uuid4()) is True
        mock_session.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, repo: FAQRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.delete(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: FAQRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.delete(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(self, repo: FAQRepository, mock_session: AsyncMock) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = FAQData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            question="What are your hours?",
            answer="9am to 5pm",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.question = "New?"  # type: ignore[misc]
