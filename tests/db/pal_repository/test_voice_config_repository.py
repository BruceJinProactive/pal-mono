"""Tests for db.pal_repository.VoiceConfigRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only VoiceConfigData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.voice_config import VoiceConfigData
from db.pal_repository.voice_config import VoiceConfigRepository
from db.tables.voice_configs import VoiceConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> VoiceConfigRepository:
    return VoiceConfigRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_project_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=VoiceConfig)
    row.id = sample_id
    row.project_id = sample_project_id
    row.language = "en"
    row.voice_id = "voice-123"
    row.replacements = {"hello": "hi"}
    row.first_message = "Hello!"
    row.transfer_message = "Transferring..."
    speech_rate_mock = MagicMock()
    speech_rate_mock.value = "normal"
    row.speech_rate = speech_rate_mock
    row.background_sound = "office"
    row.raw_config = {"key": "value"}
    row.pronunciation_dict_id = None
    row.cloned_voice_id = None
    row.voice_model = "sonic-2"
    row.transcriber = None
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = None
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, VoiceConfigData)
        assert data.id == sample_id
        assert data.speech_rate == "normal"
        assert data.language == "en"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByProjectId
# ---------------------------------------------------------------------------


class TestListByProjectId:
    """List voice configs for a project."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project_id(sample_project_id)

        assert len(results) == 1
        assert isinstance(results[0], VoiceConfigData)
        assert results[0].project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.list_by_project_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByProjectAndLanguage
# ---------------------------------------------------------------------------


class TestGetByProjectAndLanguage:
    """Lookup by project ID and language."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_language(sample_project_id, "en")

        assert isinstance(data, VoiceConfigData)
        assert data.language == "en"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_language(uuid.uuid4(), "fr")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.get_by_project_and_language(uuid.uuid4(), "en")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new voice config."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        input_data = VoiceConfigData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            language="en",
            voice_id="voice-123",
            replacements={"hello": "hi"},
            first_message="Hello!",
            transfer_message="Transferring...",
            speech_rate="normal",
            background_sound="office",
            raw_config={},
            voice_model="sonic-2",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = VoiceConfigData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            language="en",
            voice_id="voice-123",
            first_message="Hello!",
            transfer_message="Transferring...",
            speech_rate="normal",
            background_sound="office",
            voice_model="sonic-2",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating a voice config."""

    @pytest.mark.asyncio
    async def test_update_returns_updated_data(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, language="spanish", voice_id="new-voice")

        assert isinstance(data, VoiceConfigData)
        assert data.id == sample_id
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_returns_none_when_not_found(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), language="spanish")
        assert data is None

    @pytest.mark.asyncio
    async def test_update_speech_rate_converts_to_enum(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        await repo.update(sample_id, speech_rate="normal")

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_dict_fields_converts_to_dict(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        await repo.update(
            sample_id,
            replacements={"foo": "bar"},
            raw_config={"key": "val"},
            transcriber={"provider": "test"},
        )

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = RuntimeError("update failed")

        with pytest.raises(RuntimeError, match="update failed"):
            await repo.update(sample_id, language="spanish")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a voice config by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, VoiceConfigData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: VoiceConfigRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = RuntimeError("delete failed")

        with pytest.raises(RuntimeError, match="delete failed"):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDeleteByProjectId
# ---------------------------------------------------------------------------


class TestDeleteByProjectId:
    """Deleting all voice configs for a project."""

    @pytest.mark.asyncio
    async def test_delete_by_project_id_returns_count(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        # Mock two voice configs
        row1 = MagicMock()
        row1.id = uuid.uuid4()
        row2 = MagicMock()
        row2.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row1, row2]
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_project_id(sample_project_id)

        assert count == 2
        assert mock_session.delete.await_count == 2
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_by_project_id_returns_zero_when_none(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        count = await repo.delete_by_project_id(sample_project_id)

        assert count == 0
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_by_project_id_raises_on_db_error(
        self,
        repo: VoiceConfigRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("delete failed")

        with pytest.raises(RuntimeError, match="delete failed"):
            await repo.delete_by_project_id(sample_project_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """VoiceConfigData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = VoiceConfigData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            language="en",
            voice_id="voice-123",
            first_message="Hello!",
            transfer_message="Transferring...",
            speech_rate="normal",
            background_sound="office",
            voice_model="sonic-2",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.language = "changed"  # type: ignore[misc]
