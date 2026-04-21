"""Tests for db.pal_repository.IntegrationRepository."""

import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.integration import IntegrationData
from db.pal_repository.integration import IntegrationRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> IntegrationRepository:
    return IntegrationRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID, sample_account_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.account_id = sample_account_id
    row.provider = MagicMock(value="toast")
    row.integration_type = MagicMock(value="pos")
    row.auth_type = MagicMock(value="api_key")
    row.secret_key = "sk_test_123"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.business_id = "biz_456"
    row.raw_config = {"endpoint": "https://api.example.com"}
    row.access_token = "tok_abc"
    row.refresh_token = "ref_xyz"
    row.client_id = "cid_001"
    row.client_secret = "cs_secret"
    row.api_key = "ak_key"
    row.updated_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
    row.expires_at = None
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: IntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(sample_account_id, sample_id)
        assert isinstance(data, IntegrationData)
        assert data.id == sample_id
        assert data.provider == "toast"
        assert data.integration_type == "pos"
        assert data.auth_type == "api_key"
        assert data.secret_key == "sk_test_123"
        assert data.business_id == "biz_456"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4(), uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4(), uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestGetByAccountId:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: IntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_account_id(sample_account_id)
        assert len(results) == 1
        assert results[0].account_id == sample_account_id

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_account_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_account_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestGetByProjectAndType:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: IntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_project_and_type(uuid.uuid4(), uuid.uuid4(), "pos")
        assert isinstance(data, IntegrationData)
        assert data.integration_type == "pos"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_project_and_type(uuid.uuid4(), uuid.uuid4(), "pos")
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_duplicate(
        self,
        repo: IntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        dup_row = MagicMock()
        dup_row.id = uuid.uuid4()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row, dup_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Multiple integrations"):
            await repo.get_by_project_and_type(uuid.uuid4(), uuid.uuid4(), "pos")

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_project_and_type(uuid.uuid4(), uuid.uuid4(), "pos")
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: IntegrationRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = IntegrationData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            provider="toast",
            integration_type="pos",
            auth_type="api_key",
            secret_key="sk_test",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.provider = "square"  # type: ignore[misc]

    def test_raw_config_frozen(self) -> None:
        data = IntegrationData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            provider="toast",
            integration_type="pos",
            auth_type="api_key",
            secret_key="sk_test",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            raw_config={"key": "value"},
        )
        assert isinstance(data.raw_config, MappingProxyType)
        with pytest.raises(TypeError):
            data.raw_config["key"] = "changed"  # type: ignore[index]

    def test_secrets_hidden_from_repr(self) -> None:
        data = IntegrationData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            provider="toast",
            integration_type="pos",
            auth_type="api_key",
            secret_key="super_secret_key",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            access_token="access_tok",
            refresh_token="refresh_tok",
            client_secret="client_sec",
            api_key="hidden_apikey_val",
        )
        r = repr(data)
        assert "super_secret_key" not in r
        assert "access_tok" not in r
        assert "refresh_tok" not in r
        assert "client_sec" not in r
        assert "hidden_apikey_val" not in r
        # Non-secret fields should still appear
        assert "toast" in r
